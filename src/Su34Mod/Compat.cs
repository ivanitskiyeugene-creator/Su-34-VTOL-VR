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
    /// Runs the flight model pass once per aircraft the player climbs into.
    ///
    /// It has to happen at runtime rather than only in the prefab, because the
    /// game rebuilds the vehicle (and its Rigidbody mass) every time a mission
    /// starts or a loadout changes. See FlightModel.cs for the numbers.
    /// </summary>
    public class Su34FlightTuning : MonoBehaviour
    {
        public static Su34Config Config;

        private GameObject _vehicle;
        private bool _applied;
        private float _nextTry;

        public static float CurrentMass { get; private set; }

        private void Update()
        {
            if (Config == null) Config = Su34Config.Load();

            var go = Compat.PlayerVehicleObject();
            if (go == null)
            {
                _applied = false;
                _vehicle = null;
                return;
            }
            if (!Compat.IsSu34(go)) return;

            if (go != _vehicle)
            {
                // new spawn: the game creates a fresh vehicle object each time
                _vehicle = go;
                _applied = false;
                _nextTry = 0f;
            }

            if (_applied || Time.unscaledTime < _nextTry) return;
            _nextTry = Time.unscaledTime + 1f;

            try
            {
                FlightModel.Apply(go, Config);
                ApplyFlightAssistScale(go);
                _applied = true;

                var rb = go.GetComponent<Rigidbody>();
                CurrentMass = rb != null ? rb.mass : 0f;
                Su34Log.Info("flight model applied, current mass " + CurrentMass.ToString("0") + " kg");
            }
            catch (Exception e)
            {
                Su34Log.Warn("flight tuning skipped: " + e);
                _applied = true;
            }
        }

        private void ApplyFlightAssistScale(GameObject go)
        {
            if (Mathf.Approximately(Config.PitchAuthority, 1f) &&
                Mathf.Approximately(Config.RollAuthority, 1f) &&
                Mathf.Approximately(Config.YawAuthority, 1f)) return;

            foreach (var mb in go.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (mb == null || mb.GetType().Name != "FlightAssist") continue;
                ScalePid(mb, "pitchPID", Config.PitchAuthority);
                ScalePid(mb, "rollPID", Config.RollAuthority);
                ScalePid(mb, "yawPID", Config.YawAuthority);
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
    }
}
