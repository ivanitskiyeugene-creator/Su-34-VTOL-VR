using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using UnityEngine;

namespace Su34Mod
{
    /// <summary>
    /// The Su-34's real numbers, applied on top of the donor airframe.
    ///
    /// A mod aircraft built from a vanilla prefab inherits that prefab's flight
    /// model: mass, engine thrust, g limit and aero coefficients all belong to
    /// the EF-24G / T-55. Swapping the visual model does not change any of it,
    /// so without this pass the "Su-34" would accelerate like an F-18 and turn
    /// like a light fighter.
    ///
    /// The values below are absolute targets, not multipliers, so they stay
    /// correct if the donor changes. Everything is discovered by reflection and
    /// every change is logged with the field name, old and new value - that log
    /// is how the tuning gets verified without a debugger.
    /// </summary>
    public static class FlightModel
    {
        // ------------------------------------------------------------ the numbers
        // Empty weight, kg. Normal take-off 39 000 with fuel and stores, maximum
        // 45 000; the game adds fuel and weapons on top of the empty mass, so the
        // prefab starts from the empty figure.
        public const float EmptyMassKg = 22500f;

        // Two AL-31FM1, each 13 500 kgf in afterburner and 8 250 kgf dry.
        public const float ThrustPerEngineAbN = 13500f * 9.80665f;   // 132 390 N
        public const float ThrustPerEngineDryN = 8250f * 9.80665f;   // 80 905 N
        public const float ThrustAbN = 2f * ThrustPerEngineAbN;       // 264 780 N
        public const float ThrustDryN = 2f * ThrustPerEngineDryN;     // 161 810 N

        // Wing, planform and limits.
        public const float WingAreaM2 = 62.0f;
        public const float WingSpanM = 14.7f;
        public const float LengthM = 23.3f;
        public const float GLimit = 7.0f;

        // Words that identify a field as one of the numbers we own. Matched
        // case-insensitively inside the field name.
        private static readonly string[] ThrustWords = { "thrust" };
        private static readonly string[] DryWords = { "dry", "military", "milthrust", "nonafterburner" };
        private static readonly string[] MassWords = { "mass", "weight" };
        private static readonly string[] WingAreaWords = { "wingarea", "planformarea", "refarea", "surfacearea" };
        private static readonly string[] SpanWords = { "wingspan", "span" };
        private static readonly string[] GLimitWords = { "glimit", "maxg", "gmax", "maxgload" };

        private sealed class Hit
        {
            public Component owner;
            public FieldInfo field;
            public float value;
            public string why;
        }

        // ------------------------------------------------------------------ entry
        public static void Apply(GameObject vehicle, Su34Config cfg)
        {
            if (vehicle == null) return;

            var report = new StringBuilder();
            report.AppendLine("--- Su-34 flight model on " + vehicle.name + " ---");

            ApplyMass(vehicle, cfg, report);
            ApplyThrust(vehicle, cfg, report);
            ApplyAero(vehicle, cfg, report);
            ApplyGLimit(vehicle, cfg, report);

            float t = cfg.ThrustAbN;
            report.AppendLine(string.Format(
                "target: empty {0:0} kg, AB {1:0} N ({2:0} kgf), dry {3:0} N, wing {4:0.0} m2, g +{5:0.0}",
                cfg.EmptyMassKg, t, t / 9.80665f, cfg.ThrustDryN, cfg.WingAreaM2, cfg.GLimit));
            report.AppendLine(string.Format("thrust/weight at normal 39 t: {0:0.000} AB, {1:0.000} dry",
                t / (39000f * 9.80665f), cfg.ThrustDryN / (39000f * 9.80665f)));
            report.AppendLine(string.Format("wing loading at normal 39 t: {0:0} kg/m2", 39000f / cfg.WingAreaM2));

            string text = report.ToString();
            Su34Log.Info("\n" + text);
            DumpToFile(text);
        }

        // ------------------------------------------------------------------- mass
        private static void ApplyMass(GameObject vehicle, Su34Config cfg, StringBuilder report)
        {
            var rb = vehicle.GetComponent<Rigidbody>();
            if (rb == null)
            {
                report.AppendLine("mass: no Rigidbody on the prefab root, left alone");
                return;
            }

            float donor = rb.mass;
            if (cfg.EmptyMassKg <= 0f) return;
            rb.mass = cfg.EmptyMassKg;
            rb.ResetInertiaTensor();
            report.AppendLine(string.Format("mass: {0:0} -> {1:0} kg (Rigidbody)", donor, cfg.EmptyMassKg));
        }

        // ----------------------------------------------------------------- thrust
        private static void ApplyThrust(GameObject vehicle, Su34Config cfg, StringBuilder report)
        {
            var hits = new List<Hit>();
            foreach (var mb in vehicle.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (mb == null) continue;
                foreach (var f in Fields(mb))
                {
                    if (f.FieldType != typeof(float) && f.FieldType != typeof(float[])) continue;
                    string n = f.Name.ToLowerInvariant();
                    if (!ContainsAny(n, ThrustWords)) continue;
                    bool dry = ContainsAny(n, DryWords);
                    float total = Sum(f, mb);
                    if (total <= 0f) continue;
                    hits.Add(new Hit { owner = mb, field = f, value = total, why = dry ? "dry" : "ab" });
                }
            }

            if (hits.Count == 0)
            {
                report.AppendLine("thrust: no field with 'thrust' in the name found - thrust left as the donor's. " +
                                  "Send this log to the mod author.");
                return;
            }

            // Unit detection by magnitude: a jet's total thrust is either tens of
            // thousands of newtons or a few thousand kilograms-force.
            float sumAb = 0f, sumDry = 0f;
            foreach (var h in hits)
            {
                if (h.why == "dry") sumDry += h.value; else sumAb += h.value;
            }

            float scaleAb, scaleDry;
            string unit;
            if (sumAb > 20000f)
            {
                unit = "N";
                scaleAb = cfg.ThrustAbN / Mathf.Max(sumAb, 1f);
                scaleDry = sumDry > 1f ? cfg.ThrustDryN / sumDry : scaleAb;
            }
            else if (sumAb > 2000f)
            {
                unit = "kgf";
                scaleAb = (cfg.ThrustAbN / 9.80665f) / Mathf.Max(sumAb, 1f);
                scaleDry = sumDry > 1f ? (cfg.ThrustDryN / 9.80665f) / sumDry : scaleAb;
            }
            else
            {
                report.AppendLine("thrust: found fields but the values (" + sumAb.ToString("0") +
                                  ") do not look like N or kgf - left alone.");
                return;
            }

            report.AppendLine(string.Format("thrust: donor total {0:0} {1} (dry {2:0}) -> scale {3:0.000} / dry {4:0.000}",
                sumAb, unit, sumDry, scaleAb, scaleDry));

            foreach (var h in hits)
            {
                float scale = h.why == "dry" ? scaleDry : scaleAb;
                float before = Sum(h.field, h.owner);
                Multiply(h.field, h.owner, scale);
                float after = Sum(h.field, h.owner);
                report.AppendLine(string.Format("   {0}.{1}: {2:0} -> {3:0}",
                    h.owner.GetType().Name, h.field.Name, before, after));
            }
        }

        // -------------------------------------------------------------------- aero
        private static void ApplyAero(GameObject vehicle, Su34Config cfg, StringBuilder report)
        {
            var area = FindNumeric(vehicle, WingAreaWords, 10f, 400f);
            var span = FindNumeric(vehicle, SpanWords, 5f, 40f);

            if (area != null)
            {
                float before = area.value;
                area.field.SetValue(area.owner, cfg.WingAreaM2);
                report.AppendLine(string.Format("wing area {0}.{1}: {2:0.0} -> {3:0.0} m2",
                    area.owner.GetType().Name, area.field.Name, before, cfg.WingAreaM2));
            }
            else
            {
                report.AppendLine("wing area: no field in the 10..400 m2 range - aero left as the donor's.");
            }

            if (span != null)
            {
                float before = span.value;
                span.field.SetValue(span.owner, cfg.WingSpanM);
                report.AppendLine(string.Format("wing span {0}.{1}: {2:0.0} -> {3:0.0} m",
                    span.owner.GetType().Name, span.field.Name, before, cfg.WingSpanM));
            }
        }

        // ---------------------------------------------------------------- g limit
        private static void ApplyGLimit(GameObject vehicle, Su34Config cfg, StringBuilder report)
        {
            var hit = FindNumeric(vehicle, GLimitWords, 3f, 15f);
            if (hit == null)
            {
                report.AppendLine("g limit: no field found - the donor's limiter stays in place.");
                return;
            }
            float before = hit.value;
            hit.field.SetValue(hit.owner, cfg.GLimit);
            report.AppendLine(string.Format("g limit {0}.{1}: {2:0.0} -> {3:0.0}",
                hit.owner.GetType().Name, hit.field.Name, before, cfg.GLimit));
        }

        // ---------------------------------------------------------------- helpers
        private static IEnumerable<FieldInfo> Fields(object target)
        {
            FieldInfo[] fields;
            try
            {
                fields = target.GetType().GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            }
            catch
            {
                yield break;
            }
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
                if (f.FieldType == typeof(float))
                {
                    f.SetValue(owner, (float)f.GetValue(owner) * scale);
                    return;
                }
                var arr = (float[])f.GetValue(owner);
                if (arr == null) return;
                for (int i = 0; i < arr.Length; i++) arr[i] *= scale;
            }
            catch { }
        }

        /// <summary>First float field whose value sits in a plausible range.</summary>
        private static Hit FindNumeric(GameObject vehicle, string[] words, float min, float max)
        {
            foreach (var mb in vehicle.GetComponentsInChildren<MonoBehaviour>(true))
            {
                if (mb == null) continue;
                foreach (var f in Fields(mb))
                {
                    if (f.FieldType != typeof(float)) continue;
                    if (!ContainsAny(f.Name.ToLowerInvariant(), words)) continue;
                    float v;
                    try { v = (float)f.GetValue(mb); } catch { continue; }
                    if (v < min || v > max) continue;
                    return new Hit { owner = mb, field = f, value = v };
                }
            }
            return null;
        }

        private static void DumpToFile(string text)
        {
            try
            {
                File.AppendAllText(Path.Combine(Main.ModFolder, "flightmodel.log"), text + "\n");
            }
            catch { /* never let logging break the flight */ }
        }
    }

    /// <summary>
    /// Numbers from su34.cfg with the real aircraft as the default. Editing the
    /// file and restarting is enough - no rebuild, no Unity.
    /// </summary>
    public sealed class Su34Config
    {
        public float EmptyMassKg = FlightModel.EmptyMassKg;
        public float ThrustAbN = FlightModel.ThrustAbN;
        public float ThrustDryN = FlightModel.ThrustDryN;
        public float WingAreaM2 = FlightModel.WingAreaM2;
        public float WingSpanM = FlightModel.WingSpanM;
        public float GLimit = FlightModel.GLimit;

        // Optional multipliers on top, for taste rather than accuracy.
        public float PitchAuthority = 1.0f;
        public float RollAuthority = 1.0f;
        public float YawAuthority = 1.0f;

        public static Su34Config Load()
        {
            var cfg = new Su34Config();
            try
            {
                string path = Path.Combine(Main.ModFolder, "su34.cfg");
                if (!File.Exists(path)) return cfg;
                foreach (var raw in File.ReadAllLines(path))
                {
                    var line = raw.Split('#')[0].Trim();
                    if (line.Length == 0 || line.IndexOf('=') < 0) continue;
                    var parts = line.Split(new[] { '=' }, 2);
                    string key = parts[0].Trim().ToLowerInvariant();
                    float value;
                    if (!float.TryParse(parts[1].Trim(), System.Globalization.NumberStyles.Float,
                            System.Globalization.CultureInfo.InvariantCulture, out value)) continue;

                    switch (key)
                    {
                        case "emptymasskg": cfg.EmptyMassKg = value; break;
                        case "thrustabn": cfg.ThrustAbN = value; break;
                        case "thrustdryn": cfg.ThrustDryN = value; break;
                        case "wingaream2": cfg.WingAreaM2 = value; break;
                        case "wingspanm": cfg.WingSpanM = value; break;
                        case "glimit": cfg.GLimit = value; break;
                        case "pitchauthority": cfg.PitchAuthority = value; break;
                        case "rollauthority": cfg.RollAuthority = value; break;
                        case "yawauthority": cfg.YawAuthority = value; break;

                        // old keys, kept so an existing cfg keeps working
                        case "masskg": cfg.EmptyMassKg = value; break;
                        case "thrustscale":
                            cfg.ThrustAbN = FlightModel.ThrustAbN * value;
                            cfg.ThrustDryN = FlightModel.ThrustDryN * value;
                            break;
                    }
                }
                Su34Log.Info("su34.cfg: empty mass " + cfg.EmptyMassKg + " kg, AB " + cfg.ThrustAbN +
                             " N, dry " + cfg.ThrustDryN + " N, wing " + cfg.WingAreaM2 + " m2, g +" + cfg.GLimit);
            }
            catch (Exception e)
            {
                Su34Log.Warn("could not read su34.cfg: " + e.Message);
            }
            return cfg;
        }
    }
}
