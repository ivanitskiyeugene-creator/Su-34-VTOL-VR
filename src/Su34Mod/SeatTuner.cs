using System;
using System.IO;
using UnityEngine;

namespace Su34Mod
{
    /// <summary>
    /// Nudges the two crew seats at runtime.
    ///
    /// The builder places the donor's seat rigs on anchors measured from the
    /// Su-34 mesh and wraps each rig in a marker object. Where the player's head
    /// ends up, however, depends on how the donor rig is built, and that cannot
    /// be seen from here. So instead of guessing once and shipping a wrong seat,
    /// the offsets live in su34.cfg and are applied every time the aircraft
    /// spawns:
    ///
    ///     seatpilotx = 0.00
    ///     seatpiloty = 0.00
    ///     seatpilotz = 0.00
    ///     seatwsox   = 0.00
    ///     seatwsoy   = 0.00
    ///     seatwsoz   = 0.00
    ///
    /// Positive x = right, positive y = up, positive z = forward (nose).
    /// Change, restart the mission; no rebuild needed.
    /// </summary>
    public class Su34SeatTuner : MonoBehaviour
    {
        public static Vector3 PilotOffset;
        public static Vector3 WsoOffset;

        // Must match Su34BundleBuilder.SeatMarkerPilot / SeatMarkerWso.
        private static readonly string[] MarkerNames = { "Su34_SeatPilot", "Su34_SeatWso" };

        private GameObject _vehicle;
        private bool _applied;
        private float _nextTry;

        private void Update()
        {
            var go = Compat.PlayerVehicleObject();
            if (go == null)
            {
                _applied = false;
                _vehicle = null;
                return;
            }
            if (go != _vehicle)
            {
                _vehicle = go;
                _applied = false;
                _nextTry = 0f;
            }
            if (_applied || Time.unscaledTime < _nextTry) return;
            _nextTry = Time.unscaledTime + 1f;

            if (!Compat.IsSu34(go)) return;

            try
            {
                Load();
                Apply(go);
                _applied = true;
            }
            catch (Exception e)
            {
                Su34Log.Warn("seat tuning skipped: " + e.Message);
                _applied = true;
            }
        }

        private static void Apply(GameObject vehicle)
        {
            if (PilotOffset == Vector3.zero && WsoOffset == Vector3.zero) return;

            Vector3[] offsets = { PilotOffset, WsoOffset };
            int found = 0;
            Transform[] all = vehicle.GetComponentsInChildren<Transform>(true);
            for (int i = 0; i < MarkerNames.Length; i++)
            {
                if (offsets[i] == Vector3.zero) continue;
                foreach (Transform t in all)
                {
                    if (t.name != MarkerNames[i]) continue;
                    t.localPosition += offsets[i];
                    found++;
                    Su34Log.Info("seat " + MarkerNames[i] + " moved by " + offsets[i]);
                    break;
                }
            }
            if (found == 0)
                Su34Log.Warn("seat offsets set in su34.cfg but no seat markers found on this vehicle");
        }

        private static void Load()
        {
            PilotOffset = Vector3.zero;
            WsoOffset = Vector3.zero;

            string path = Path.Combine(Main.ModFolder, "su34.cfg");
            if (!File.Exists(path)) return;

            foreach (string raw in File.ReadAllLines(path))
            {
                string line = raw.Split('#')[0].Trim();
                if (line.Length == 0 || line.IndexOf('=') < 0) continue;
                string[] parts = line.Split(new[] { '=' }, 2);
                string key = parts[0].Trim().ToLowerInvariant();
                float v;
                if (!float.TryParse(parts[1].Trim(), System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out v)) continue;

                switch (key)
                {
                    case "seatpilotx": PilotOffset.x = v; break;
                    case "seatpiloty": PilotOffset.y = v; break;
                    case "seatpilotz": PilotOffset.z = v; break;
                    case "seatwsox": WsoOffset.x = v; break;
                    case "seatwsoy": WsoOffset.y = v; break;
                    case "seatwsoz": WsoOffset.z = v; break;
                }
            }
        }
    }
}
