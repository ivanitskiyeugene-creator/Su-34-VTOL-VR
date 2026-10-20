// -----------------------------------------------------------------------------
//  Su-34 for VTOL VR - one-click Unity builder
//
//  What it does:
//    1. loads the F/A-26B prefab from your AssetRipper export of VTOL VR
//       (that prefab already carries the flight model, gear, weapons,
//       cockpit, MFDs and VR interactables),
//    2. renames it "Su34", adds ExternalVehicleInfo and fills in the mod data,
//    3. drops the procedural Su-34 exterior from this repo under the root and
//       hides the donor's exterior renderers (cockpit / MFD / seat stay),
//    4. saves the prefab, tags it for an asset bundle named "su34" and builds
//       the Windows bundle straight into  mod/su34  in this repository.
//
//  Open the menu:  VTOL VR / Su-34 ...
//
//  Unity version: use the exact version VTOL VR runs (2020.3.x - see the
//  ProjectVersion.txt of your AssetRipper export, or player.log line 3).
// -----------------------------------------------------------------------------
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Su34.EditorTools
{
    public static class Su34BundleBuilder
    {
        // ------------------------------------------------------------------ config
        // Change these if your AssetRipper export uses different paths.
        public const string DonorPrefabPath = "Assets/Resources/vehicles/FA-26B.prefab";
        public const string ModelObjPath = "Assets/Su34/Models/su34.obj";
        public const string OutputPrefabPath = "Assets/Su34/Su34.prefab";
        public const string BundleName = "su34";
        public const string PrefabAssetName = "Su34";
        public const string VehicleName = "Su-34";
        public const string VehicleNickname = "Fullback";
        public const string VehicleDescription =
            "Twin-seat, twin-engine supersonic strike fighter. Heavy payload, long range, " +
            "side-by-side cockpit. Built for the VTOL VR Mod Loader.";

        private const string BundleOutputDir = "AssetBundles";

        // Children whose names contain one of these words are part of the
        // cockpit the player actually interacts with, so they stay visible.
        private static string _resolvedDonor;

        // Fallback: if the default path does not exist, search the project for
        // the FA-26B prefab. AssetRipper exports vary slightly between
        // versions, so this removes the most common setup failure.
        private static string DonorPrefab
        {
            get
            {
                if (!string.IsNullOrEmpty(_resolvedDonor)) return _resolvedDonor;
                if (File.Exists(DonorPrefabPath)) { _resolvedDonor = DonorPrefabPath; return _resolvedDonor; }
                foreach (var guid in AssetDatabase.FindAssets("FA-26B t:GameObject"))
                {
                    string path = AssetDatabase.GUIDToAssetPath(guid);
                    if (path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase) &&
                        path.IndexOf("vehicle", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        _resolvedDonor = path;
                        Debug.Log("[Su-34] donor prefab auto-detected: " + path);
                        return _resolvedDonor;
                    }
                }
                _resolvedDonor = DonorPrefabPath;
                return _resolvedDonor;
            }
        }

        private static readonly string[] KeepVisibleKeywords =
        {
            "cockpit", "interior", "seat", "mfd", "hud", "canopy", "stick",
            "throttle", "panel", "switch", "button", "helmet", "pilot", "glove"
        };

        // ------------------------------------------------------------------ menu
        [MenuItem("VTOL VR/Su-34/0 - Check setup", priority = 0)]
        public static void CheckSetup()
        {
            bool ok = true;
            ok &= CheckFile(DonorPrefab, "F/A-26B donor prefab (AssetRipper export of VTOL VR)");
            ok &= CheckFile(ModelObjPath, "Su-34 model (copy assets/model/* into Assets/Su34/Models/)");
            ok &= CheckFolder("Assets/Su34", "output folder");
            Debug.Log(ok
                ? "[Su-34] Setup looks good - run '2 - Build prefab + asset bundle'."
                : "[Su-34] Fix the missing paths above, then run the check again.");
        }

        [MenuItem("VTOL VR/Su-34/1 - Dump donor hierarchy", priority = 1)]
        public static void DumpHierarchy()
        {
            if (!CheckFile(DonorPrefab, "donor prefab")) return;
            GameObject root = PrefabUtility.LoadPrefabContents(DonorPrefab);
            try
            {
                var sb = new StringBuilder();
                sb.AppendLine("Donor hierarchy of " + DonorPrefab);
                foreach (var t in root.GetComponentsInChildren<Transform>(true))
                {
                    var r = t.GetComponent<Renderer>();
                    sb.AppendLine(string.Format("{0}{1}   [{2}]",
                        new string(' ', t.GetSiblingIndex() * 0),
                        GetPath(root.transform, t),
                        r != null ? r.GetType().Name : "no renderer"));
                }
                string outPath = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Su34_donor_hierarchy.txt"));
                File.WriteAllText(outPath, sb.ToString());
                Debug.Log("[Su-34] hierarchy written to " + outPath);
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }
        }

        [MenuItem("VTOL VR/Su-34/2 - Build prefab + asset bundle", priority = 2)]
        public static void Build()
        {
            if (!CheckFile(DonorPrefab, "donor prefab")) return;
            if (!CheckFile(ModelObjPath, "Su-34 model")) return;

            EnsureFolder("Assets/Su34");

            GameObject root = PrefabUtility.LoadPrefabContents(DonorPrefab);
            List<string> report = new List<string>();
            try
            {
                root.name = PrefabAssetName;

                // ------------------------------------------------ vehicle metadata
                var info = root.GetComponent<ExternalVehicleInfo>();
                if (info == null) info = root.AddComponent<ExternalVehicleInfo>();
                SetInfoFields(info, report);

                // ------------------------------------------------------- visual mesh
                AttachModel(root, report);

                // ------------------------------------------- hide donor exterior
                HideDonorExterior(root, report);

                // ------------------------------------------------------- save prefab
                var saved = PrefabUtility.SaveAsPrefabAsset(root, OutputPrefabPath);
                if (saved == null)
                {
                    Debug.LogError("[Su-34] could not save prefab at " + OutputPrefabPath);
                    return;
                }
                Debug.Log("[Su-34] prefab saved: " + OutputPrefabPath);
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
                AssetDatabase.Refresh();
            }

            AssetImporter.GetAtPath(OutputPrefabPath).assetBundleName = BundleName;
            AssetDatabase.SaveAssets();

            // ------------------------------------------------------------ build it
            if (!Directory.Exists(BundleOutputDir)) Directory.CreateDirectory(BundleOutputDir);
            var manifest = BuildPipeline.BuildAssetBundles(
                BundleOutputDir,
                BuildAssetBundleOptions.ChunkBasedCompression | BuildAssetBundleOptions.ForceRebuildAssetBundle,
                BuildTarget.StandaloneWindows64);

            if (manifest == null)
            {
                Debug.LogError("[Su-34] BuildAssetBundles failed - see the console above.");
                return;
            }

            string built = Path.Combine(BundleOutputDir, BundleName);
            if (!File.Exists(built))
            {
                Debug.LogError("[Su-34] bundle file not found: " + built);
                return;
            }

            // ------------------------------------------------- deploy into the repo
            string repoModDir = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "mod"));
            Directory.CreateDirectory(repoModDir);
            string deployed = Path.Combine(repoModDir, BundleName);
            File.Copy(built, deployed, true);
            Debug.Log("[Su-34] bundle copied to " + deployed);

            string reportPath = Path.Combine(repoModDir, "build_report.txt");
            File.WriteAllText(reportPath, string.Join("\n", report));
            Debug.Log("[Su-34] build report: " + reportPath);
            Debug.Log("[Su-34] DONE. Run tools/install.ps1 (or copy mod\\* to the Mods folder) and launch VTOL VR.");
        }

        [MenuItem("VTOL VR/Su-34/3 - Build DLL and install into the game", priority = 3)]
        public static void BuildDllAndInstall()
        {
            string repo = Path.GetFullPath(Path.Combine(Application.dataPath, "..", ".."));
            string script = Path.Combine(repo, "tools", "build.ps1");
            if (!File.Exists(script))
            {
                Debug.LogError("[Su-34] tools/build.ps1 not found under " + repo);
                return;
            }
            if (!File.Exists(Path.Combine(repo, "mod", BundleName)))
            {
                Debug.LogError("[Su-34] mod/" + BundleName + " is missing - run step 2 first.");
                return;
            }
            RunPowerShell("-ExecutionPolicy Bypass -File \"" + script + "\" -Deploy", repo);
        }

        private static void RunPowerShell(string arguments, string workingDirectory)
        {
            try
            {
                var psi = new System.Diagnostics.ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = arguments,
                    WorkingDirectory = workingDirectory,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                };
                using (var p = System.Diagnostics.Process.Start(psi))
                {
                    string stdout = p.StandardOutput.ReadToEnd();
                    string stderr = p.StandardError.ReadToEnd();
                    p.WaitForExit();
                    if (!string.IsNullOrEmpty(stdout)) Debug.Log("[Su-34] build.ps1:\n" + stdout);
                    if (!string.IsNullOrEmpty(stderr)) Debug.LogError("[Su-34] build.ps1 errors:\n" + stderr);
                    Debug.Log(p.ExitCode == 0 ? "[Su-34] DLL built and installed." : "[Su-34] build.ps1 exited with " + p.ExitCode);
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[Su-34] could not run PowerShell: " + e.Message +
                               " - run tools/build.ps1 manually from the repository root.");
            }
        }

        // ---------------------------------------------------------------- helpers
        private static void SetInfoFields(ExternalVehicleInfo info, List<string> report)
        {
            // SerializedObject keeps this working even if the field layout of
            // ExternalVehicleInfo changes between game versions.
            var so = new SerializedObject(info);
            SetString(so, "vehicleName", VehicleName, report);
            SetString(so, "description", VehicleDescription, report);
            SetString(so, "nickname", VehicleNickname, report);
            so.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(info);
            report.Add("ExternalVehicleInfo: " + VehicleName + " / " + VehicleNickname);
        }

        private static void SetString(SerializedObject so, string property, string value, List<string> report)
        {
            var p = so.FindProperty(property);
            if (p == null)
            {
                report.Add("WARNING: ExternalVehicleInfo has no field '" + property + "' on this game build");
                return;
            }
            p.stringValue = value;
        }

        private static void AttachModel(GameObject root, List<string> report)
        {
            var modelAsset = AssetDatabase.LoadAssetAtPath<GameObject>(ModelObjPath);
            if (modelAsset == null)
            {
                report.Add("ERROR: model asset not importable at " + ModelObjPath);
                return;
            }

            var existing = root.transform.Find("Su34_Visual");
            if (existing != null) UnityEngine.Object.DestroyImmediate(existing.gameObject);

            var visual = UnityEngine.Object.Instantiate(modelAsset);
            visual.name = "Su34_Visual";
            visual.transform.SetParent(root.transform, false);
            // The OBJ is authored nose-forward (+Z) at 1:1 metres, which is what
            // Unity and VTOL VR expect.
            visual.transform.localPosition = Vector3.zero;
            visual.transform.localRotation = Quaternion.identity;
            visual.transform.localScale = Vector3.one;

            int meshes = visual.GetComponentsInChildren<MeshRenderer>(true).Length;
            report.Add("visual model attached: " + meshes + " renderers");
            Debug.Log("[Su-34] attached model with " + meshes + " renderers");

            MakeGlassTransparent(visual, report);
        }

        /// <summary>
        /// Unity's OBJ importer keeps the MTL alpha but leaves the material
        /// opaque. The canopy is authored with alpha 0.30, so switch those
        /// materials to the transparent rendering mode.
        /// </summary>
        private static void MakeGlassTransparent(GameObject visual, List<string> report)
        {
            foreach (var r in visual.GetComponentsInChildren<Renderer>(true))
            {
                foreach (var mat in r.sharedMaterials)
                {
                    if (mat == null) continue;
                    if (mat.name.IndexOf("Glass", StringComparison.OrdinalIgnoreCase) < 0) continue;
                    mat.SetFloat("_Mode", 3f); // Standard shader: Transparent
                    mat.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
                    mat.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
                    mat.SetInt("_ZWrite", 0);
                    mat.DisableKeyword("_ALPHATEST_ON");
                    mat.EnableKeyword("_ALPHABLEND_ON");
                    mat.renderQueue = 3000;
                    report.Add("glass material made transparent: " + mat.name);
                }
            }
        }

        private static void HideDonorExterior(GameObject root, List<string> report)
        {
            int hidden = 0, kept = 0;
            foreach (var r in root.GetComponentsInChildren<Renderer>(true))
            {
                if (r == null) continue;
                string path = GetPath(root.transform, r.transform);
                if (path.StartsWith("Su34_Visual")) continue; // our own model

                bool keep = KeepVisibleKeywords.Any(k =>
                    path.IndexOf(k, StringComparison.OrdinalIgnoreCase) >= 0);

                if (keep)
                {
                    kept++;
                    report.Add("keep    " + path + "  (" + r.GetType().Name + ")");
                }
                else
                {
                    r.enabled = false;
                    hidden++;
                    report.Add("hidden  " + path + "  (" + r.GetType().Name + ")");
                }
            }
            report.Add("--- donor renderers: " + hidden + " hidden, " + kept + " kept (cockpit)");
            Debug.Log("[Su-34] donor renderers: " + hidden + " hidden, " + kept + " kept");
        }

        private static string GetPath(Transform root, Transform t)
        {
            var stack = new Stack<string>();
            while (t != null && t != root)
            {
                stack.Push(t.name);
                t = t.parent;
            }
            return string.Join("/", stack);
        }

        private static bool CheckFile(string assetPath, string what)
        {
            if (File.Exists(assetPath)) return true;
            Debug.LogError("[Su-34] missing " + what + ": " + assetPath);
            return false;
        }

        private static bool CheckFolder(string assetPath, string what)
        {
            if (AssetDatabase.IsValidFolder(assetPath)) return true;
            Debug.LogWarning("[Su-34] missing " + what + ": " + assetPath + " (it will be created)");
            return true;
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
