// -----------------------------------------------------------------------------
//  Su-34 for VTOL VR - materials and texture import settings
//
//  The donated model ships one 4096x4096 PBR set (base colour, normal,
//  metallic-roughness) plus three small materials that are not painted at all:
//  canopy/instrument glass, the HUD combiner and the landing light lenses.
//
//  Two things have to be forced here, because Unity's defaults are wrong for
//  this asset:
//    * the default importer caps textures at 2048 and imports everything as an
//      sRGB colour map - so the 4K authoring is silently thrown away and the
//      normal map produces wrong lighting;
//    * the OBJ importer has no idea about transparent or emissive materials, so
//      every part comes in opaque and unlit.
// -----------------------------------------------------------------------------
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Su34.EditorTools
{
    public static class Su34Materials
    {
        public const string ModelsDir = "Assets/Su34/Models";
        public const string TexturesDir = ModelsDir + "/textures";
        public const string MaterialsDir = "Assets/Su34/Materials";

        public const string BaseColorFile = "donor_basecolor.png";
        public const string NormalFile = "donor_normal.png";
        public const string RoughnessFile = "donor_roughness.png";
        public const string MetalSmoothFile = "donor_metalsmooth.png";

        // Files the material pass needs that the MTL does not mention, so the
        // model sync knows to copy them too.
        public static readonly string[] ExtraTextures = { MetalSmoothFile };

        // 4096 is what the source art is authored at. Drop it to 2048 if you
        // need the VRAM back: at 2048 one texel covers ~8.6 mm of airframe
        // instead of ~4.3 mm (the whole jet shares a single UV atlas).
        public const int TextureSize = 4096;

        public static Material Airframe { get; private set; }
        public static Material Glass { get; private set; }
        public static Material Hud { get; private set; }
        public static Material Lights { get; private set; }

        /// <summary>
        /// Sets the import settings Unity should have used in the first place.
        /// Safe to call on every build: it only reimports when something changed.
        /// </summary>
        public static void FixTextureSettings(List<string> report)
        {
            FixOne(TexturesDir + "/" + BaseColorFile, TextureKind.Color, report);
            FixOne(TexturesDir + "/" + NormalFile, TextureKind.Normal, report);
            FixOne(TexturesDir + "/" + RoughnessFile, TextureKind.Linear, report);
            FixOne(TexturesDir + "/" + MetalSmoothFile, TextureKind.Linear, report);
        }

        private enum TextureKind { Color, Normal, Linear }

        private static void FixOne(string path, TextureKind kind, List<string> report)
        {
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null)
            {
                if (report != null) report.Add("texture missing: " + path);
                return;
            }

            bool changed = false;
            if (importer.maxTextureSize != TextureSize) { importer.maxTextureSize = TextureSize; changed = true; }
            if (!importer.mipmapEnabled) { importer.mipmapEnabled = true; changed = true; }
            if (importer.anisoLevel < 4) { importer.anisoLevel = 4; changed = true; }

            TextureImporterType wantType = kind == TextureKind.Normal
                ? TextureImporterType.NormalMap
                : TextureImporterType.Default;
            if (importer.textureType != wantType) { importer.textureType = wantType; changed = true; }

            bool wantSrgb = kind == TextureKind.Color;
            if (importer.sRGBTexture != wantSrgb) { importer.sRGBTexture = wantSrgb; changed = true; }

            if (importer.textureCompression != TextureImporterCompression.Compressed)
            {
                importer.textureCompression = TextureImporterCompression.Compressed;
                changed = true;
            }

            if (changed)
            {
                importer.SaveAndReimport();
                if (report != null) report.Add("texture settings fixed: " + Path.GetFileName(path) +
                                               " (" + wantType + ", sRGB " + wantSrgb + ", " + TextureSize + ")");
            }
        }

        /// <summary>
        /// Builds the four materials and attaches them to the imported model.
        /// Renderers are matched by object name, not by the material Unity's OBJ
        /// importer made up.
        /// </summary>
        public static void Apply(GameObject visual, List<string> report)
        {
            FixTextureSettings(report);
            EnsureFolder(MaterialsDir);

            var baseColor = AssetDatabase.LoadAssetAtPath<Texture2D>(TexturesDir + "/" + BaseColorFile);
            var normal = AssetDatabase.LoadAssetAtPath<Texture2D>(TexturesDir + "/" + NormalFile);

            Airframe = BuildAirframe(baseColor, normal, report);
            Glass = BuildGlass();
            Hud = BuildHud();
            Lights = BuildLights();

            int glass = 0, hud = 0, lamps = 0, hull = 0;
            foreach (var r in visual.GetComponentsInChildren<Renderer>(true))
            {
                string n = r.gameObject.name.ToLowerInvariant();

                if (n.Contains("instrglass") || n.Contains("canopy") || n.Contains("glass"))
                {
                    r.sharedMaterial = Glass;
                    // a transparent shell must not throw a shadow
                    r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                    r.receiveShadows = false;
                    glass++;
                }
                else if (n.Contains("hud"))
                {
                    r.sharedMaterial = Hud;
                    r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                    hud++;
                }
                else if (n.Contains("light"))
                {
                    r.sharedMaterial = Lights;
                    lamps++;
                }
                else
                {
                    r.sharedMaterial = Airframe;
                    hull++;
                }
            }

            report.Add("materials: airframe " + hull + " renderers, glass " + glass +
                       ", hud " + hud + ", lights " + lamps);
            Debug.Log("[Su-34] materials applied: airframe " + hull + ", glass " + glass +
                      ", hud " + hud + ", lights " + lamps);
        }

        // ------------------------------------------------------------- materials
        private static Material BuildAirframe(Texture2D baseColor, Texture2D normal, List<string> report)
        {
            var m = EnsureMaterial("Su34_Airframe");
            m.shader = Shader.Find("Standard");
            m.color = Color.white;
            if (baseColor != null) m.mainTexture = baseColor; else report.Add("WARNING: base colour texture not imported");
            var metalSmooth = AssetDatabase.LoadAssetAtPath<Texture2D>(TexturesDir + "/" + MetalSmoothFile);
            if (metalSmooth != null)
            {
                // R = metallic, A = smoothness (packed by tools/pack_pbr.py)
                m.SetTexture("_MetallicGlossMap", metalSmooth);
                m.EnableKeyword("_METALLICGLOSSMAP");
                m.SetFloat("_SmoothnessTextureChannel", 0f); // smoothness lives in the map's alpha
                m.SetFloat("_Metallic", 1f);                 // all in the map
                m.SetFloat("_Glossiness", 1f);
            }
            else
            {
                // no packed map: fall back to the averages of the donated maps
                m.SetFloat("_Metallic", 0.17f);
                m.SetFloat("_Glossiness", 0.45f);
                report.Add("WARNING: " + MetalSmoothFile + " missing - using flat metallic/gloss values");
            }

            if (normal != null)
            {
                m.SetTexture("_BumpMap", normal);
                m.SetFloat("_BumpScale", 1.0f);
                m.EnableKeyword("_NORMALMAP");
            }
            else
            {
                report.Add("WARNING: normal map not imported");
            }

            // Metallic and roughness come from the packed map above. The
            // greyscale donor_roughness.png is kept only as the source art.
            m.SetFloat("_Mode", 0f);
            m.DisableKeyword("_ALPHABLEND_ON");
            m.renderQueue = -1;
            m.enableInstancing = true;
            EditorUtility.SetDirty(m);
            return m;
        }

        private static Material BuildGlass()
        {
            var m = EnsureMaterial("Su34_Glass");
            m.shader = Shader.Find("Standard");
            m.color = new Color(0.62f, 0.72f, 0.78f, 0.30f);
            m.SetFloat("_Metallic", 0.0f);
            m.SetFloat("_Glossiness", 0.92f);

            m.SetFloat("_Mode", 3f);
            m.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
            m.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
            m.SetInt("_ZWrite", 0);
            m.DisableKeyword("_ALPHATEST_ON");
            m.EnableKeyword("_ALPHABLEND_ON");
            m.DisableKeyword("_ALPHAPREMULTIPLY_ON");
            m.renderQueue = 3000;
            EditorUtility.SetDirty(m);
            return m;
        }

        private static Material BuildHud()
        {
            var m = EnsureMaterial("Su34_HUD");
            m.shader = Shader.Find("Standard");
            m.color = new Color(0.0f, 0.85f, 0.05f, 0.55f);
            m.SetFloat("_Metallic", 0.0f);
            m.SetFloat("_Glossiness", 0.8f);

            m.SetFloat("_Mode", 3f);
            m.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
            m.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
            m.SetInt("_ZWrite", 0);
            m.EnableKeyword("_ALPHABLEND_ON");
            m.renderQueue = 3000;

            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", new Color(0.0f, 0.85f, 0.05f) * 1.5f);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
            EditorUtility.SetDirty(m);
            return m;
        }

        private static Material BuildLights()
        {
            var m = EnsureMaterial("Su34_Lights");
            m.shader = Shader.Find("Standard");
            m.color = Color.white;
            m.SetFloat("_Metallic", 0.0f);
            m.SetFloat("_Glossiness", 0.6f);
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", Color.white * 3.0f);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
            EditorUtility.SetDirty(m);
            return m;
        }

        private static Material EnsureMaterial(string name)
        {
            string path = MaterialsDir + "/" + name + ".mat";
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m == null)
            {
                m = new Material(Shader.Find("Standard"));
                AssetDatabase.CreateAsset(m, path);
            }
            m.name = name;
            return m;
        }

        private static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            string parent = Path.GetDirectoryName(path).Replace('\\', '/');
            string leaf = Path.GetFileName(path);
            if (!AssetDatabase.IsValidFolder(parent)) EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, leaf);
        }
    }
}
