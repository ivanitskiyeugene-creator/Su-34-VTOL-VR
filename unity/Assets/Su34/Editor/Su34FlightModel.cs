// -----------------------------------------------------------------------------
//  Su-34 for VTOL VR - flight model
//
//  The prefab is the EF-24G (or T-55) with a new skin. Its mass, thrust, wing
//  area and g limit are the donor's, so the "Su-34" would fly like a light
//  fighter. This pass overwrites those numbers with the real aircraft's, and
//  writes a dump of everything it found so the tuning can be checked without a
//  debugger.
//
//  The same pass runs at runtime (src/Su34Mod/FlightModel.cs) because the game
//  rebuilds the vehicle on every spawn. Baked values make the very first frames
//  correct; the runtime pass covers loadout changes and a donor whose component
//  names differ from what this editor script recognises.
// -----------------------------------------------------------------------------
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Su34.EditorTools
{
    public static class Su34FlightModel
    {
        // ------------------------------------------------------------ the numbers
        public const float EmptyMassKg = 22500f;
        public const float ThrustAbN = 2f * 13500f * 9.80665f;    // two AL-31FM1 at full AB
        public const float ThrustDryN = 2f * 8250f * 9.80665f;    // dry / military power
        public const float WingAreaM2 = 62.0f;
        public const float WingSpanM = 14.7f;
        public const float GLimit = 7.0f;

        private static readonly string[] ThrustWords = { "thrust" };
        private static readonly string[] DryWords = { "dry", "military", "milthrust", "nonafterburner" };
        private static readonly string[] WingAreaWords = { "wingarea", "planformarea", "refarea", "surfacearea" };
        private static readonly string[] SpanWords = { "wingspan", "span" };
        private static readonly string[] GLimitWords = { "glimit", "maxg", "gmax", "maxgload" };

        public const string DumpFileName = "Su34_flightmodel.txt";

        [MenuItem("VTOL VR/Su-34/3 - Dump flight model to a file", priority = 4)]
        public static void DumpMenu()
        {
            if (!Su34BundleBuilder.CheckFilePublic(Su34BundleBuilder.DonorPrefabPath)) return;
            GameObject root = UnityEditor.PrefabUtility.LoadPrefabContents(Su34BundleBuilder.DonorPrefabPath);
            try
            {
                string path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", DumpFileName));
                File.WriteAllText(path, Dump(root));
                Debug.Log("[Su-34] flight model dump written to " + path);
            }
            finally
            {
                UnityEditor.PrefabUtility.UnloadPrefabContents(root);
            }
        }

        /// <summary>
        /// Applies the real aircraft's numbers to the prefab. Returns the list of
        /// changes (also appended to the build report).
        /// </summary>
        public static void Apply(GameObject root, List<string> report)
        {
            var rb = root.GetComponent<Rigidbody>();
            if (rb != null)
            {
                float donor = rb.mass;
                rb.mass = EmptyMassKg;
                rb.ResetInertiaTensor();
                report.Add(string.Format("flight model: mass {0:0} -> {1:0} kg", donor, EmptyMassKg));
            }
            else
            {
                report.Add("flight model: no Rigidbody on the prefab root (the game adds its own) - " +
                           "mass is applied at runtime instead");
            }

            ApplyThrust(root, report);
            ApplyAero(root, report);
            ApplyGLimit(root, report);

            string dump = Dump(root);
            try
            {
                File.WriteAllText(Path.GetFullPath(Path.Combine(Application.dataPath, "..", DumpFileName)), dump);
                report.Add("flight model dump: " + DumpFileName + " (project root)");
            }
            catch (Exception e)
            {
                report.Add("flight model dump failed: " + e.Message);
            }
        }

        // ----------------------------------------------------------------- thrust
        private static void ApplyThrust(GameObject root, List<string> report)
        {
            float sumAb = 0f, sumDry = 0f;
            var hits = new List<KeyValuePair<Component, FieldInfo>>();
            var dry = new List<bool>();

            foreach (var mb in root.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (mb == null) continue;
                foreach (var f in Fields(mb))
                {
                    if (f.FieldType != typeof(float) && f.FieldType != typeof(float[])) continue;
                    string n = f.Name.ToLowerInvariant();
                    if (!ContainsAny(n, ThrustWords)) continue;
                    float total = Sum(f, mb);
                    if (total <= 0f) continue;
                    bool isDry = ContainsAny(n, DryWords);
                    if (isDry) sumDry += total; else sumAb += total;
                    hits.Add(new KeyValuePair<Component, FieldInfo>(mb, f));
                    dry.Add(isDry);
                }
            }

            if (hits.Count == 0)
            {
                report.Add("flight model: no thrust field found on the donor - thrust stays as delivered " +
                           "(the runtime pass logs its own result)");
                return;
            }

            float scaleAb, scaleDry;
            string unit;
            if (sumAb > 20000f)
            {
                unit = "N";
                scaleAb = ThrustAbN / Mathf.Max(sumAb, 1f);
                scaleDry = sumDry > 1f ? ThrustDryN / sumDry : scaleAb;
            }
            else if (sumAb > 2000f)
            {
                unit = "kgf";
                scaleAb = (ThrustAbN / 9.80665f) / Mathf.Max(sumAb, 1f);
                scaleDry = sumDry > 1f ? (ThrustDryN / 9.80665f) / sumDry : scaleAb;
            }
            else
            {
                report.Add("flight model: thrust fields found but the values are neither N nor kgf " +
                           "(sum " + sumAb.ToString("0") + ") - left alone");
                return;
            }

            for (int i = 0; i < hits.Count; i++)
            {
                Multiply(hits[i].Value, hits[i].Key, dry[i] ? scaleDry : scaleAb);
            }

            report.Add(string.Format(
                "flight model: donor thrust {0:0} {1} (dry {2:0}) -> Su-34 {3:0} N AB / {4:0} N dry " +
                "(scale {5:0.000} / {6:0.000}, {7} fields)",
                sumAb, unit, sumDry, ThrustAbN, ThrustDryN, scaleAb, scaleDry, hits.Count));
        }

        // ------------------------------------------------------------------- aero
        private static void ApplyAero(GameObject root, List<string> report)
        {
            var area = FindNumeric(root, WingAreaWords, 10f, 400f);
            if (area.Key != null)
            {
                float before = (float)area.Value.GetValue(area.Key);
                area.Value.SetValue(area.Key, WingAreaM2);
                report.Add(string.Format("flight model: wing area {0}.{1} {2:0.0} -> {3:0.0} m2",
                    area.Key.GetType().Name, area.Value.Name, before, WingAreaM2));
            }

            var span = FindNumeric(root, SpanWords, 5f, 40f);
            if (span.Key != null)
            {
                float before = (float)span.Value.GetValue(span.Key);
                span.Value.SetValue(span.Key, WingSpanM);
                report.Add(string.Format("flight model: wing span {0}.{1} {2:0.0} -> {3:0.0} m",
                    span.Key.GetType().Name, span.Value.Name, before, WingSpanM));
            }
        }

        private static void ApplyGLimit(GameObject root, List<string> report)
        {
            var hit = FindNumeric(root, GLimitWords, 3f, 15f);
            if (hit.Key == null) return;
            float before = (float)hit.Value.GetValue(hit.Key);
            hit.Value.SetValue(hit.Key, GLimit);
            report.Add(string.Format("flight model: g limit {0}.{1} {2:0.0} -> {3:0.0}",
                hit.Key.GetType().Name, hit.Value.Name, before, GLimit));
        }

        // ------------------------------------------------------------------- dump
        /// <summary>Every candidate number on the donor, so tuning is not guesswork.</summary>
        public static string Dump(GameObject root)
        {
            var sb = new StringBuilder();
            sb.AppendLine("Su-34 flight model dump");
            sb.AppendLine("donor prefab root: " + root.name);
            sb.AppendLine("targets: empty " + EmptyMassKg + " kg, AB " + ThrustAbN.ToString("0") +
                          " N, dry " + ThrustDryN.ToString("0") + " N, wing " + WingAreaM2 +
                          " m2, span " + WingSpanM + " m, g +" + GLimit);
            sb.AppendLine();

            var rb = root.GetComponent<Rigidbody>();
            sb.AppendLine("Rigidbody: " + (rb != null ? "mass " + rb.mass.ToString("0") + " kg" : "none on root"));
            sb.AppendLine();

            string[] words = Merge(ThrustWords, DryWords, WingAreaWords, SpanWords, GLimitWords,
                new[] { "mass", "weight", "lift", "drag", "aoa", "alpha", "cl", "cd" });

            foreach (var mb in root.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (mb == null) continue;
                var lines = new List<string>();
                foreach (var f in Fields(mb))
                {
                    string n = f.Name.ToLowerInvariant();
                    if (!ContainsAny(n, words)) continue;
                    object v;
                    try { v = f.GetValue(mb); } catch { continue; }
                    lines.Add("    " + f.FieldType.Name + " " + f.Name + " = " + Format(v));
                }
                if (lines.Count == 0) continue;
                sb.AppendLine(mb.GetType().Name + "  [" + Su34BundleBuilder.PathOf(root, mb.transform) + "]");
                foreach (string l in lines) sb.AppendLine(l);
                sb.AppendLine();
            }
            return sb.ToString();
        }

        // ---------------------------------------------------------------- helpers
        private static string Format(object v)
        {
            if (v == null) return "null";
            var arr = v as float[];
            if (arr != null)
            {
                var parts = new string[arr.Length];
                for (int i = 0; i < arr.Length; i++) parts[i] = arr[i].ToString("0.###");
                return "[" + string.Join(", ", parts) + "]";
            }
            if (v is float) return ((float)v).ToString("0.###");
            return v.ToString();
        }

        private static string[] Merge(params string[][] sets)
        {
            var list = new List<string>();
            foreach (var s in sets) list.AddRange(s);
            return list.ToArray();
        }

        private static IEnumerable<FieldInfo> Fields(object target)
        {
            FieldInfo[] fields;
            try
            {
                fields = target.GetType().GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            }
            catch { yield break; }
            foreach (var f in fields) yield return f;
        }

        private static bool ContainsAny(string lower, string[] words)
        {
            foreach (var w in words)
                if (lower.IndexOf(w, StringComparison.Ordinal) >= 0) return true;
            return false;
        }

        private static float Sum(FieldInfo f, object owner)
        {
            try
            {
                if (f.FieldType == typeof(float)) return (float)f.GetValue(owner);
                var arr = (float[])f.GetValue(owner);
                if (arr == null) return 0f;
                float s = 0f;
                foreach (float v in arr) s += v;
                return s;
            }
            catch { return 0f; }
        }

        private static void Multiply(FieldInfo f, object owner, float scale)
        {
            try
            {
                if (f.FieldType == typeof(float)) { f.SetValue(owner, (float)f.GetValue(owner) * scale); return; }
                var arr = (float[])f.GetValue(owner);
                if (arr == null) return;
                for (int i = 0; i < arr.Length; i++) arr[i] *= scale;
            }
            catch { }
        }

        private static KeyValuePair<Component, FieldInfo> FindNumeric(
            GameObject root, string[] words, float min, float max)
        {
            foreach (var mb in root.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (mb == null) continue;
                foreach (var f in Fields(mb))
                {
                    if (f.FieldType != typeof(float)) continue;
                    if (!ContainsAny(f.Name.ToLowerInvariant(), words)) continue;
                    float v;
                    try { v = (float)f.GetValue(mb); } catch { continue; }
                    if (v < min || v > max) continue;
                    return new KeyValuePair<Component, FieldInfo>(mb, f);
                }
            }
            return default(KeyValuePair<Component, FieldInfo>);
        }
    }
}
