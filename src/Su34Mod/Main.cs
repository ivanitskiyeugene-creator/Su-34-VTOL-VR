using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using HarmonyLib;
using ModLoader.Framework;
using ModLoader.Framework.Attributes;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Su34Mod
{
    /// <summary>
    /// Entry point for the Su-34 mod. Mirrors the structure of the current
    /// Custom Aircraft Template (CAT, DankuwOs) so it stays compatible with the
    /// Steam Mod Loader (ModLoader.Framework).
    ///
    /// The aircraft asset bundle is produced in Unity 2020.3.x from the model in
    /// this repository (see unity/README.md for the one-time setup).
    /// </summary>
    [ItemId("su34.vtolvr.arena")]
    public class Main : VtolMod
    {
        public const string AircraftName = "Su-34";
        public const string PrefabName = "Su34";     // must match the prefab asset name in the bundle
        public const string BundleFileName = "su34"; // bundle file copied next to the dll

        public static Main instance;
        public static string ModFolder;
        public static string BundlePath;

        private static bool _registered;

        private void Start()
        {
            instance = this;
            ModFolder = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            BundlePath = Path.Combine(ModFolder, BundleFileName);

            // Harmony is global: patches are applied once and every one of them
            // is individually guarded (see Patches.Try), so a game update that
            // renames a method only disables that single feature.
            var harmony = new Harmony("su34.vtolvr.arena");
            Patches.Apply(harmony);

            // Diagnostics overlay (F10) and the flight-model tuning live on
            // their own persistent objects so the mod object stays small.
            var host = new GameObject("Su34Runtime");
            UnityEngine.Object.DontDestroyOnLoad(host);
            host.AddComponent<Su34DiagnosticsHost>();
            host.AddComponent<Su34FlightTuning>();

            Su34Log.Info("mod loaded, bundle path = " + BundlePath);
            VTResources.OnLoadingPlayerVehicles += AircraftAPI.VehicleAdd;
            AircraftAPI.VehicleAdd();
        }

        public override void UnLoad()
        {
            VTResources.OnLoadingPlayerVehicles -= AircraftAPI.VehicleAdd;
            if (_registered)
            {
                AircraftAPI.VehicleRemove();
                _registered = false;
            }
            Su34Log.Info("mod unloaded");
        }

        internal static void MarkRegistered()
        {
            _registered = true;
        }

        private void Update()
        {
            // F10 toggles the debug readout. Handy when the cockpit misbehaves.
            // Compat handles both the legacy and the new Input System.
            if (Compat.KeyPressed("F10"))
            {
                Su34Diagnostics.Toggle();
            }
        }
    }

    /// <summary>Log helper so every line can be grepped in Output.log.</summary>
    internal static class Su34Log
    {
        private const string Tag = "[Su-34] ";

        public static void Info(string message) { Debug.Log(Tag + message); }
        public static void Warn(string message) { Debug.LogWarning(Tag + message); }
        public static void Error(string message) { Debug.LogError(Tag + message); }
        public static void Exception(Exception e, string context)
        {
            Debug.LogError(Tag + context + ": " + e);
        }
    }

    /// <summary>Debug overlay (F10) showing the state the patches depend on.</summary>
    internal static class Su34Diagnostics
    {
        private static bool _visible;
        private static float _nextRefresh;
        private static string _text = "";

        public static void Toggle()
        {
            _visible = !_visible;
            Su34Log.Info("diagnostics " + (_visible ? "on" : "off"));
        }

        public static void Tick()
        {
            if (!_visible || Time.unscaledTime < _nextRefresh) return;
            _nextRefresh = Time.unscaledTime + 0.5f;

            var sb = new StringBuilder();
            sb.AppendLine("SU-34 MOD  (F10 to hide)");
            sb.AppendLine("scene: " + SceneManager.GetActiveScene().name);
            sb.AppendLine("bundle: " + (File.Exists(Main.BundlePath) ? "found" : "MISSING"));
            var pv = AircraftAPI.PlayerVehicle;
            sb.AppendLine("registered: " + (pv != null ? pv.vehicleName : "no"));
            if (PilotSaveManager.currentVehicle != null)
                sb.AppendLine("selected: " + PilotSaveManager.currentVehicle.vehicleName);
            var go = Compat.PlayerVehicleObject();
            sb.AppendLine("vehicle go: " + (go != null ? go.name : "none"));
            if (go != null)
            {
                var rb = go.GetComponent<Rigidbody>();
                sb.AppendLine("mass: " + (rb != null ? rb.mass.ToString("0") : "no rigidbody"));
            }
            _text = sb.ToString();
        }

        public static void Draw()
        {
            if (!_visible || string.IsNullOrEmpty(_text)) return;
            GUI.Label(new Rect(20, 20, 520, 220), _text);
        }
    }

    /// <summary>Draws the diagnostics overlay from a persistent object.</summary>
    public class Su34DiagnosticsHost : MonoBehaviour
    {
        private void Update() { Su34Diagnostics.Tick(); }
        private void OnGUI() { Su34Diagnostics.Draw(); }
    }
}
