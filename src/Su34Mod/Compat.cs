using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEngine;

namespace Su34Mod
{
    /// <summary>
    /// Thin, reflection-based bridges to optional or version-sensitive game
    /// APIs. VTOL VR changes its assemblies between updates, so anything the
    /// mod does not strictly need is invoked reflectively: a rename then shows
    /// up as a single warning in the log instead of a broken mod.
    /// </summary>
    internal static class Compat
    {
        // ------------------------------------------------------------------ VTOLAPI
        /// <summary>
        /// Optional dependency on the "VTOLAPI" workshop mod, which contains the
        /// shader fix-ups every external vehicle needs to look right.
        /// </summary>
        public static void TryFixShaders(GameObject prefab, bool renderers, bool materials, bool particles)
        {
            try
            {
                Type vtapi = FindType("VTOLAPI.VTAPI");
                if (vtapi == null)
                {
                    Su34Log.Warn("VTOLAPI (workshop mod) is not installed - skipping the shader fix. " +
                                 "Subscribe to 'VTOLAPI' on the Mod Loader workshop for correct materials.");
                    return;
                }
                var method = vtapi.GetMethod("FixShaders", BindingFlags.Public | BindingFlags.Static);
                if (method == null)
                {
                    Su34Log.Warn("VTOLAPI.FixShaders changed signature - skipping the shader fix.");
                    return;
                }
                method.Invoke(null, new object[] { prefab, renderers, materials, particles });
                Su34Log.Info("shaders fixed via VTOLAPI");
            }
            catch (Exception e)
            {
                Su34Log.Warn("shader fix failed (non-fatal): " + e.Message);
            }
        }

        // --------------------------------------------------------------- scene state
        /// <summary>The player's active aircraft, found without a compile-time dependency.</summary>
        public static GameObject PlayerVehicleObject()
        {
            // 1) VTOLAPI if the player has it installed
            try
            {
                Type vtapi = FindType("VTOLAPI.VTOLAPI");
                var m = vtapi?.GetMethod("GetPlayersVehicleGameObject", BindingFlags.Public | BindingFlags.Static);
                var go = m?.Invoke(null, null) as GameObject;
                if (go != null) return go;
            }
            catch { /* ignore */ }

            // 2) FlightSceneManager.instance.playerActor
            try
            {
                Type fsm = FindType("FlightSceneManager");
                var instance = fsm?.GetField("instance", BindingFlags.Public | BindingFlags.Static)?.GetValue(null)
                             ?? fsm?.GetProperty("instance", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
                if (instance != null)
                {
                    object actor = GetMember(instance, "playerActor");
                    var actorMb = actor as Component;
                    if (actorMb != null) return actorMb.gameObject;
                    var actorGo = actor as GameObject;
                    if (actorGo != null) return actorGo;
                }
            }
            catch { /* ignore */ }

            // 3) the instantiated prefab, by name
            return GameObject.Find(Main.PrefabName + "(Clone)");
        }

        public static bool IsSu34(GameObject go)
        {
            if (go == null) return false;
            try
            {
                var pv = PilotSaveManager.currentVehicle;
                if (pv != null && pv.vehicleName == Main.AircraftName) return true;
            }
            catch { /* ignore */ }
            return go.name.StartsWith(Main.AircraftName, StringComparison.OrdinalIgnoreCase);
        }

        // ------------------------------------------------------------------ key input
        /// <summary>
        /// The game may run with the legacy Input Manager disabled (new Input
        /// System only), where UnityEngine.Input throws. This returns true on
        /// the frame the key was pressed, whichever backend is active.
        /// </summary>
        public static bool KeyPressed(string keyName)
        {
            try
            {
                var key = (KeyCode)Enum.Parse(typeof(KeyCode), keyName, true);
                if (Input.GetKeyDown(key)) return true;
            }
            catch { /* legacy input disabled */ }

            try
            {
                Type keyboard = FindType("UnityEngine.InputSystem.Keyboard");
                if (keyboard == null) return false;
                object current = keyboard.GetProperty("current", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
                if (current == null) return false;
                object keyControl = keyboard.GetProperty(keyName.ToLowerInvariant() + "Key",
                    BindingFlags.Public | BindingFlags.Instance)?.GetValue(current);
                if (keyControl == null) return false;
                object pressed = keyControl.GetType()
                    .GetProperty("wasPressedThisFrame", BindingFlags.Public | BindingFlags.Instance)
                    ?.GetValue(keyControl);
                return pressed is bool && (bool)pressed;
            }
            catch { return false; }
        }

        // ------------------------------------------------------------------- helpers
        public static Type FindType(string fullName)
        {
            var direct = Type.GetType(fullName);
            if (direct != null) return direct;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type t = null;
                try { t = asm.GetType(fullName, false); } catch { }
                if (t != null) return t;
            }
            return null;
        }

        public static object GetMember(object target, string name)
        {
            if (target == null) return null;
            var t = target.GetType();
            var f = t.GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (f != null) return f.GetValue(target);
            var p = t.GetProperty(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            return p?.GetValue(target);
        }

        public static object GetStaticMember(string typeName, string member)
        {
            Type t = FindType(typeName);
            if (t == null) return null;
            var f = t.GetField(member, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
            if (f != null) return f.GetValue(null);
            var p = t.GetProperty(member, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
            return p?.GetValue(null);
        }
    }

    /// <summary>
    /// Applies the Su-34's real-world numbers on top of the donor airframe the
    /// model was grafted onto, so it flies like a heavy strike fighter instead
    /// of a light one. Everything is optional: if a field is missing on your
    /// game build the step is skipped and logged.
    /// Tune the values in su34.cfg next to the dll.
    /// </summary>
    public class Su34FlightTuning : MonoBehaviour
    {
        private const string CfgFile = "su34.cfg";

        public float MassKg = 26000f;
        public float ThrustScale = 1.10f;
        public float PitchAuthority = 0.95f;
        public float RollAuthority = 0.92f;
        public float YawAuthority = 1.05f;

        private bool _applied;
        private float _nextTry;

        private void Update()
        {
            if (_applied || Time.unscaledTime < _nextTry) return;
            _nextTry = Time.unscaledTime + 1f;

            var go = Compat.PlayerVehicleObject();
            if (go == null || !Compat.IsSu34(go)) return;

            try
            {
                LoadConfig();

                var rb = go.GetComponent<Rigidbody>();
                if (rb != null && MassKg > 0f)
                {
                    float donorMass = Mathf.Max(rb.mass, 1f);
                    rb.mass = MassKg;
                    rb.ResetInertiaTensor();
                    Su34Log.Info("mass set to " + MassKg + " kg (donor: " + donorMass.ToString("0") + " kg)");
                }

                ApplyEngineScale(go);
                ApplyFlightAssistScale(go);

                _applied = true;
                Su34Log.Info("flight tuning applied");
            }
            catch (Exception e)
            {
                Su34Log.Warn("flight tuning skipped: " + e.Message);
                _applied = true;
            }
        }

        private void ApplyEngineScale(GameObject go)
        {
            if (Mathf.Approximately(ThrustScale, 1f)) return;
            foreach (var mb in go.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (mb == null) continue;
                if (mb.GetType().Name.IndexOf("Engine", StringComparison.OrdinalIgnoreCase) < 0) continue;
                ScaleNumericField(mb, new[] { "maxThrust", "maxThrustN", "maxThrustPerEngine", "thrust" }, ThrustScale);
            }
        }

        private void ApplyFlightAssistScale(GameObject go)
        {
            foreach (var mb in go.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (mb == null || mb.GetType().Name != "FlightAssist") continue;
                ScalePid(mb, "pitchPID", PitchAuthority);
                ScalePid(mb, "rollPID", RollAuthority);
                ScalePid(mb, "yawPID", YawAuthority);
            }
        }

        private static void ScalePid(object target, string pidField, float scale)
        {
            if (Mathf.Approximately(scale, 1f)) return;
            var pid = Compat.GetMember(target, pidField);
            if (pid == null) return;
            var kp = pid.GetType().GetField("kp", BindingFlags.Public | BindingFlags.Instance);
            if (kp == null || kp.FieldType != typeof(float)) return;
            kp.SetValue(pid, (float)kp.GetValue(pid) * scale);
        }

        private static void ScaleNumericField(object target, string[] names, float scale)
        {
            foreach (var name in names)
            {
                var f = target.GetType().GetField(name,
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (f == null) continue;
                if (f.FieldType == typeof(float))
                {
                    f.SetValue(target, (float)f.GetValue(target) * scale);
                    return;
                }
                if (f.FieldType == typeof(float[]))
                {
                    var arr = (float[])f.GetValue(target);
                    for (int i = 0; i < arr.Length; i++) arr[i] *= scale;
                    return;
                }
            }
        }

        private void LoadConfig()
        {
            try
            {
                string path = Path.Combine(Main.ModFolder, CfgFile);
                if (!File.Exists(path)) return;
                foreach (var raw in File.ReadAllLines(path))
                {
                    var line = raw.Split('#')[0].Trim();
                    if (line.Length == 0 || !line.Contains("=")) continue;
                    var parts = line.Split(new[] { '=' }, 2);
                    string key = parts[0].Trim().ToLowerInvariant();
                    float value;
                    if (!float.TryParse(parts[1].Trim(), System.Globalization.NumberStyles.Float,
                            System.Globalization.CultureInfo.InvariantCulture, out value)) continue;
                    switch (key)
                    {
                        case "masskg": MassKg = value; break;
                        case "thrustscale": ThrustScale = value; break;
                        case "pitchauthority": PitchAuthority = value; break;
                        case "rollauthority": RollAuthority = value; break;
                        case "yawauthority": YawAuthority = value; break;
                    }
                }
            }
            catch (Exception e)
            {
                Su34Log.Warn("could not read " + CfgFile + ": " + e.Message);
            }
        }
    }
}
