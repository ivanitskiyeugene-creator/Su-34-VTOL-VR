// -----------------------------------------------------------------------------
//  Su-34 for VTOL VR - one-click Unity builder
//
//  What it does:
//    1. loads a vehicle prefab from your AssetRipper export of VTOL VR. The
//       preferred donor is a *two-crew* jet (EF-24G, then T-55), because VTOL
//       VR only offers a second player slot for vehicles whose prefab has two
//       seat rigs. The two-seat prefabs also carry the flight model, gear,
//       weapons, cockpit, MFDs and VR interactables. If neither DLC is
//       installed the builder falls back to the single-seat F/A-26B and logs
//       that the second player will not be able to join,
//    2. renames it "Su34", adds ExternalVehicleInfo and fills in the mod data,
//    3. drops the procedural Su-34 exterior from this repo under the root and
//       hides the donor's exterior renderers (cockpit / MFD / seat stay),
//    4. moves the donor's two seat rigs to the Su-34 chairs, side by side
//       (pilot left, WSO right) - that is what turns a tandem two-seater into
//       a two-player Su-34,
//    5. saves the prefab, tags it for an asset bundle named "su34" and builds
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
using System.Reflection;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Su34.EditorTools
{
    public static class Su34BundleBuilder
    {
        // ------------------------------------------------------------------ config
        // Change these if your AssetRipper export uses different paths.
        //
        // DONOR. VTOL VR has three vehicles with a second player slot: the
        // AH-94 helicopter, the T-55 trainer jet and the EF-24G EW jet. All
        // three are DLC and all three are tandem. Mods may not reuse their
        // code, but a mod *can* be built on the vehicle prefab itself - that
        // is how the AH-6 mod gets two pilots sitting side by side (it
        // requires the AH-94). The Su-34 needs the same thing, only with
        // jets, so the builder picks the best two-seat jet it can find and
        // moves its seat rigs to the Su-34 chairs in AlignCrewSeats().
        //
        // Leave the override empty to auto-pick; set a prefab path to force
        // a specific donor.
        public const string DonorPrefabOverride = "";
        public static readonly string[] DonorCandidates =
        {
            "EF-24G",   // two-seat EW jet, pilot + WSO   (DLC)
            "EF24G",    // same prefab, other export naming
            "T-55",     // two-seat trainer jet           (DLC)
            "T55",      // same prefab, other export naming
            "FA-26B",   // single-seat fallback           (base game)
            "FA26B",
        };

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
        private static string _activeDonorName = "?";
        private static int _activeDonorSeats = -1;

        /// <summary>Donor picked by the builder ("EF-24G", "T-55", "FA-26B").</summary>
        public static string ActiveDonorName
        {
            get { var _ = DonorPrefab; return _activeDonorName; }
        }

        /// <summary>Crew seat rigs the donor actually has (2 = multicrew).</summary>
        public static int ActiveDonorSeats
        {
            get
            {
                if (_activeDonorSeats < 0)
                {
                    var scratch = new List<string>();
                    _activeDonorSeats = CountSeatRigs(DonorPrefab, scratch);
                }
                return _activeDonorSeats;
            }
        }

        // Auto-detect the best donor available in this AssetRipper export.
        // Direct path first, then exact prefab name, then any vehicle prefab
        // whose name starts with the candidate (exports vary).
        private static string DonorPrefab
        {
            get
            {
                if (!string.IsNullOrEmpty(_resolvedDonor)) return _resolvedDonor;

                if (!string.IsNullOrEmpty(DonorPrefabOverride))
                {
                    if (File.Exists(DonorPrefabOverride))
                        return RememberDonor(DonorPrefabOverride, Path.GetFileNameWithoutExtension(DonorPrefabOverride));
                    Debug.LogWarning("[Su-34] DonorPrefabOverride not found: " + DonorPrefabOverride +
                                     " - auto-detecting instead.");
                }

                foreach (string name in DonorCandidates)
                {
                    string direct = "Assets/Resources/vehicles/" + name + ".prefab";
                    if (File.Exists(direct)) return RememberDonor(direct, name);

                    string[] guids = AssetDatabase.FindAssets(SearchableName(name) + " t:GameObject");
                    foreach (string guid in guids)
                    {
                        string path = AssetDatabase.GUIDToAssetPath(guid);
                        if (!path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase)) continue;
                        if (!string.Equals(Path.GetFileNameWithoutExtension(path), name,
                                           StringComparison.OrdinalIgnoreCase)) continue;
                        return RememberDonor(path, name);
                    }
                    foreach (string guid in guids)
                    {
                        string path = AssetDatabase.GUIDToAssetPath(guid);
                        if (!path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase)) continue;
                        if (path.IndexOf("vehicle", StringComparison.OrdinalIgnoreCase) < 0) continue;
                        return RememberDonor(path, name);
                    }
                }

                Debug.LogError("[Su-34] no donor prefab found. Export the game with AssetRipper and make sure " +
                               "Assets/Resources/vehicles/ exists, or set DonorPrefabOverride.");
                _resolvedDonor = "Assets/Resources/vehicles/FA-26B.prefab";
                _activeDonorName = "FA-26B";
                return _resolvedDonor;
            }
        }

        private static string RememberDonor(string path, string name)
        {
            _resolvedDonor = path;
            _activeDonorName = name;
            Debug.Log("[Su-34] donor: " + name + " -> " + path);
            return _resolvedDonor;
        }

        private static string SearchableName(string name)
        {
            // AssetDatabase search treats some characters as operators.
            return name.Replace("/", "");
        }

        // Only applied to the donor: our own Su34_Visual is skipped by path.
        // The donor's seats and canopy are left out on purpose - the model in
        // this repo has both of its own, and two overlapping cockpits read as
        // a mess. Hands/helmet stay so the pilot still has VR presence.
        private static readonly string[] KeepVisibleKeywords =
        {
            "cockpit", "interior", "mfd", "hud", "stick",
            "throttle", "panel", "switch", "button", "helmet", "pilot", "glove"
        };

        // ------------------------------------------------------------------ menu
        // The OBJ, its MTL and the PNG textures live in the repository
        // (assets/model). Unity's OBJ importer resolves "textures/foo.png"
        // relative to the OBJ, so the PNGs have to sit in Models/textures.
        // Copying them automatically removes a step that is easy to get wrong.
        private const string ModelsDir = "Assets/Su34/Models";

        private static string RepoModelDir
        {
            get
            {
                string project = Directory.GetCurrentDirectory();   // ...\unity
                return Path.GetFullPath(Path.Combine(project, "..", "assets", "model"));
            }
        }

        [MenuItem("VTOL VR/Su-34/0 - Copy model + textures into Assets", priority = 0)]
        public static void CopyModelAssets()
        {
            string source = RepoModelDir;
            if (!Directory.Exists(source))
            {
                Debug.LogError("[Su-34] cannot find the model folder: " + source +
                               " - run this from the unity/ folder of the repository.");
                return;
            }
            EnsureFolder("Assets/Su34");
            EnsureFolder(ModelsDir);
            EnsureFolder(ModelsDir + "/textures");

            int copied = 0;
            foreach (string file in Directory.GetFiles(source))
            {
                string ext = Path.GetExtension(file).ToLowerInvariant();
                if (ext != ".obj" && ext != ".mtl") continue;
                File.Copy(file, Path.Combine(ModelsDir, Path.GetFileName(file)), true);
                copied++;
            }
            foreach (string file in Directory.GetFiles(Path.Combine(source, "textures")))
            {
                if (Path.GetExtension(file).ToLowerInvariant() != ".png") continue;
                File.Copy(file, Path.Combine(ModelsDir, "textures", Path.GetFileName(file)), true);
                copied++;
            }
            AssetDatabase.Refresh();
            Debug.Log("[Su-34] copied " + copied + " model files into " + ModelsDir);
        }

        [MenuItem("VTOL VR/Su-34/0b - Check setup", priority = 1)]
        public static void CheckSetup()
        {
            CopyModelAssets();
            bool ok = true;
            ok &= CheckFile(DonorPrefab, ActiveDonorName + " donor prefab (AssetRipper export of VTOL VR)");
            ok &= CheckFile(ModelObjPath, "Su-34 model");
            ok &= CheckFolder(ModelsDir + "/textures", "Su-34 textures");
            ok &= CheckFolder("Assets/Su34", "output folder");

            int seats = ActiveDonorSeats;
            Debug.Log("[Su-34] donor: " + ActiveDonorName + " (" + DonorPrefab +
                      "), crew seat rigs: " + seats);
            if (seats < 2)
            {
                Debug.LogWarning("[Su-34] this donor is single-seat. The aircraft will fly, but a second " +
                                 "player cannot join it: VTOL VR only offers a second player slot when the " +
                                 "vehicle prefab has two seat rigs. Install the EF-24G or T-55 DLC, " +
                                 "re-export the game and run the check again for a two-player Su-34.");
            }
            else
            {
                Debug.Log("[Su-34] two crew seats found: the builder will place them side by side " +
                          "(pilot left, WSO right).");
            }

            Debug.Log(ok
                ? "[Su-34] Setup looks good - run '2 - Build prefab + asset bundle'."
                : "[Su-34] Fix the missing paths above, then run the check again.");
        }

        [MenuItem("VTOL VR/Su-34/1 - Dump donor hierarchy", priority = 2)]
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

        [MenuItem("VTOL VR/Su-34/2 - Build prefab + asset bundle", priority = 3)]
        public static void Build()
        {
            CopyModelAssets();
            if (!CheckFile(DonorPrefab, "donor prefab")) return;
            if (!CheckFile(ModelObjPath, "Su-34 model")) return;

            EnsureFolder("Assets/Su34");

            GameObject root = PrefabUtility.LoadPrefabContents(DonorPrefab);
            List<string> report = new List<string>();
            try
            {
                root.name = PrefabAssetName;
                report.Add("donor prefab: " + ActiveDonorName + "  (" + DonorPrefab + ")");

                // ------------------------------------------------ vehicle metadata
                var info = root.GetComponent<ExternalVehicleInfo>();
                if (info == null) info = root.AddComponent<ExternalVehicleInfo>();
                SetInfoFields(info, report);

                // ------------------------------------------------------- visual mesh
                AttachModel(root, report);

                // ------------------------------------------- hide donor exterior
                HideDonorExterior(root, report);

                // ---------------------------------------- two crew, side by side
                AlignCrewSeats(root, report);

                // ------------------------------------------- crew seat anchors
                AddCrewAnchors(root, report);

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
            bool okName = SetString(so, new[] { "vehicleName", "name", "displayName", "vehicleTitle" },
                VehicleName, report);
            SetString(so, new[] { "description", "desc", "vehicleDescription" }, VehicleDescription, report);
            SetString(so, new[] { "nickname", "shortName", "callsign" }, VehicleNickname, report);
            so.ApplyModifiedPropertiesWithoutUndo();

            // Belt and braces: some builds keep these as plain runtime fields.
            SetFieldByReflection(info, new[] { "vehicleName", "name", "displayName", "vehicleTitle" }, VehicleName);
            SetFieldByReflection(info, new[] { "nickname", "shortName", "callsign" }, VehicleNickname);

            EditorUtility.SetDirty(info);
            report.Add("ExternalVehicleInfo: " + VehicleName + " / " + VehicleNickname +
                       (okName ? "" : "  <-- vehicleName field not found, see field dump below"));

            // Dump the real field names so a mismatch is visible instead of
            // silently producing an unselectable aircraft.
            var fields = info.GetType().GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            report.Add("ExternalVehicleInfo fields (" + fields.Length + "):");
            foreach (var f in fields)
            {
                object value = null;
                try { value = f.GetValue(info); } catch { }
                report.Add("   " + f.FieldType.Name + " " + f.Name + " = " + (value ?? "null"));
            }
        }

        private static void SetFieldByReflection(object target, string[] names, string value)
        {
            var t = target.GetType();
            foreach (var name in names)
            {
                var f = t.GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                if (f == null || f.FieldType != typeof(string)) continue;
                f.SetValue(target, value);
            }
        }

        private static bool SetString(SerializedObject so, string[] properties, string value, List<string> report)
        {
            foreach (var property in properties)
            {
                var p = so.FindProperty(property);
                if (p == null || p.propertyType != SerializedPropertyType.String) continue;
                p.stringValue = value;
                report.Add("ExternalVehicleInfo." + property + " = " + value);
                return true;
            }
            report.Add("WARNING: none of [" + string.Join(", ", properties) +
                       "] exist on ExternalVehicleInfo in this game build");
            return false;
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

        // ------------------------------------------------------------- crew seats
        // VTOL VR gives a vehicle a second player slot when its prefab carries
        // two seat rigs; the mission editor then offers "1 slot / 2 slots" for
        // a player spawn, and in single player the seat can be switched like in
        // the T-55. Every vanilla two-seater (AH-94, T-55, EF-24G) is tandem.
        // The Su-34 is side by side, so the two donor rigs are moved to our
        // chairs: front donor seat -> pilot (left), rear donor seat -> WSO
        // (right). Rig = whatever the donor uses to seat a player: a component
        // whose type contains "Seat", or a Transform/GameObject field named
        // like seat / pilot / crew / WSO on the cockpit component.
        private const bool AlignSeatsSideBySide = true;

        // The donor's instruments are built around its own cockpit station. On a
        // shorter airframe (T-55 is 13.4 m, the Su-34 is ~25 m) that station is
        // metres away from our seats, so the whole cockpit group is moved with
        // the front seat. Set to false to keep the donor cockpit where it was.
        private const bool MoveDonorCockpitToSu34 = true;

        private static readonly Vector3 PilotSeatAnchor = new Vector3(-0.30f, 1.15f, 6.40f);
        private static readonly Vector3 WsoSeatAnchor = new Vector3(0.30f, 1.15f, 6.40f);

        // Escape hatch: if auto-detection picks the wrong objects, copy the two
        // hierarchy paths from Su34_donor_hierarchy.txt here (relative to the
        // prefab root, e.g. "Cockpit/Seats/PilotSeat").
        public const string SeatPathPilot = "";
        public const string SeatPathWso = "";

        private sealed class SeatRig
        {
            public Transform transform;
            public string path;
            public readonly List<string> sources = new List<string>();
        }

        private static readonly string[] CrewWords =
            { "seat", "pilot", "crew", "wso", "ewo", "gunner", "instructor" };

        private static bool IsCrewFieldName(string name)
        {
            if (string.IsNullOrEmpty(name)) return false;
            foreach (string word in CrewWords)
                if (name.IndexOf(word, StringComparison.OrdinalIgnoreCase) >= 0) return true;
            return false;
        }

        private static List<SeatRig> FindSeatRigs(GameObject root, List<string> report)
        {
            var rigs = new List<SeatRig>();
            var index = new Dictionary<Transform, SeatRig>();

            Action<Transform, string> add = (t, why) =>
            {
                if (t == null) return;
                SeatRig rig;
                if (!index.TryGetValue(t, out rig))
                {
                    rig = new SeatRig { transform = t, path = GetPath(root.transform, t) };
                    index[t] = rig;
                    rigs.Add(rig);
                }
                if (!rig.sources.Contains(why)) rig.sources.Add(why);
            };

            foreach (var c in root.GetComponentsInChildren<Component>(true))
            {
                if (c == null) continue;
                string typeName = c.GetType().Name;

                if (typeName.IndexOf("Seat", StringComparison.OrdinalIgnoreCase) >= 0)
                    add(c.transform, typeName);

                FieldInfo[] fields;
                try
                {
                    fields = c.GetType().GetFields(
                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                }
                catch { continue; }

                foreach (var f in fields)
                {
                    if (!IsCrewFieldName(f.Name)) continue;
                    object value;
                    try { value = f.GetValue(c); } catch { continue; }
                    if (value == null) continue;

                    Transform t = value as Transform;
                    if (t == null)
                    {
                        var go = value as GameObject;
                        if (go != null) t = go.transform;
                    }
                    if (t != null)
                    {
                        add(t, typeName + "." + f.Name);
                        continue;
                    }

                    // Cockpits often keep the seats in an array or a list.
                    var list = value as System.Collections.IEnumerable;
                    if (list == null || value is string) continue;
                    int index = 0;
                    foreach (object item in list)
                    {
                        Transform it = item as Transform;
                        if (it == null)
                        {
                            var go = item as GameObject;
                            if (go != null) it = go.transform;
                        }
                        if (it != null) add(it, typeName + "." + f.Name + "[" + index + "]");
                        index++;
                    }
                }
            }

            // A rig nested inside another rig would get the offset twice.
            var filtered = new List<SeatRig>();
            foreach (var rig in rigs)
            {
                bool nested = rigs.Any(other => other != rig && rig.transform.IsChildOf(other.transform));
                if (nested)
                {
                    report.Add("seat rig ignored (child of another rig): " + rig.path);
                    continue;
                }
                filtered.Add(rig);
            }

            // Nose first: the forward seat becomes the pilot, the rear one the WSO.
            filtered.Sort((a, b) =>
            {
                float za = root.transform.InverseTransformPoint(a.transform.position).z;
                float zb = root.transform.InverseTransformPoint(b.transform.position).z;
                return zb.CompareTo(za);
            });
            return filtered;
        }

        private static Transform LowestCommonAncestor(List<Transform> transforms)
        {
            if (transforms == null || transforms.Count == 0) return null;
            Transform lca = transforms[0];
            for (int i = 1; i < transforms.Count && lca != null; i++)
            {
                Transform other = transforms[i];
                while (lca != null && lca != other && !other.IsChildOf(lca))
                    lca = lca.parent;
            }
            return lca;
        }

        private static int CountSeatRigs(string prefabPath, List<string> report)
        {
            if (string.IsNullOrEmpty(prefabPath) || !File.Exists(prefabPath)) return 0;
            GameObject root = PrefabUtility.LoadPrefabContents(prefabPath);
            try
            {
                return FindSeatRigs(root, report).Count;
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }
        }

        private static void AlignCrewSeats(GameObject root, List<string> report)
        {
            List<SeatRig> rigs;

            // Explicit paths win over auto-detection.
            if (!string.IsNullOrEmpty(SeatPathPilot) && !string.IsNullOrEmpty(SeatPathWso))
            {
                Transform p = root.transform.Find(SeatPathPilot);
                Transform w = root.transform.Find(SeatPathWso);
                if (p != null && w != null)
                {
                    rigs = new List<SeatRig>
                    {
                        new SeatRig { transform = p, path = SeatPathPilot },
                        new SeatRig { transform = w, path = SeatPathWso },
                    };
                    report.Add("crew seats taken from SeatPathPilot / SeatPathWso");
                }
                else
                {
                    report.Add("WARNING: SeatPathPilot / SeatPathWso not found at " +
                               SeatPathPilot + " / " + SeatPathWso + " - falling back to auto-detection");
                    rigs = FindSeatRigs(root, report);
                }
            }
            else
            {
                rigs = FindSeatRigs(root, report);
            }

            report.Add("crew seat rigs found: " + rigs.Count);
            foreach (var rig in rigs)
                report.Add("   " + rig.path + "   [" + string.Join(", ", rig.sources.ToArray()) + "]");

            if (rigs.Count == 0)
            {
                report.Add("WARNING: no seat rig found on this donor - the game will treat the aircraft as " +
                           "single-seat. Use the EF-24G or T-55 donor.");
                Debug.LogWarning("[Su-34] no seat rig found on the donor prefab");
                return;
            }

            if (!AlignSeatsSideBySide)
            {
                report.Add("seat alignment disabled - donor seating kept");
                return;
            }

            // Bring the donor's cockpit group to our cockpit station first, so
            // its MFDs, HUD and switches sit in front of the crew instead of
            // staying at the donor's own (much shorter) fuselage position.
            if (MoveDonorCockpitToSu34 && rigs.Count > 0)
            {
                var seatTransforms = new List<Transform>();
                foreach (var rig in rigs) seatTransforms.Add(rig.transform);
                Transform cockpit = LowestCommonAncestor(seatTransforms);

                if (cockpit == null || cockpit == root.transform)
                {
                    report.Add("donor cockpit group not moved (seat rigs sit directly under the vehicle root)");
                }
                else
                {
                    Vector3 pilotNow = root.transform.InverseTransformPoint(rigs[0].transform.position);
                    Vector3 delta = PilotSeatAnchor - pilotNow;
                    if (delta.magnitude > 0.02f)
                    {
                        cockpit.position += root.transform.TransformVector(delta);
                        report.Add(string.Format(
                            "donor cockpit group moved: {0} by ({1:0.00}, {2:0.00}, {3:0.00}) so the " +
                            "front seat lands on the Su-34 pilot chair",
                            GetPath(root.transform, cockpit), delta.x, delta.y, delta.z));
                    }
                }
            }

            Vector3[] anchors = { PilotSeatAnchor, WsoSeatAnchor };
            int moves = Mathf.Min(rigs.Count, anchors.Length);
            for (int i = 0; i < moves; i++)
            {
                Transform t = rigs[i].transform;
                Vector3 before = root.transform.InverseTransformPoint(t.position);
                t.position = root.transform.TransformPoint(anchors[i]);
                Vector3 after = root.transform.InverseTransformPoint(t.position);
                string line = string.Format(
                    "{0} -> ({1:0.00}, {2:0.00}, {3:0.00})  was ({4:0.00}, {5:0.00}, {6:0.00})",
                    rigs[i].path, after.x, after.y, after.z, before.x, before.y, before.z);
                report.Add("seat moved: " + line);
                Debug.Log("[Su-34] seat moved: " + line);
            }

            if (moves < 2)
            {
                report.Add("WARNING: only one crew seat on this donor - the second player cannot join. " +
                           "Install the EF-24G or T-55 DLC and re-export the game.");
                Debug.LogWarning("[Su-34] donor is single-seat: two-player crew will not work");
            }
            else
            {
                report.Add("two crew seats aligned side by side: pilot left, WSO right");
            }
        }

        // The Su-34 cockpit is side-by-side: pilot on the left, weapons systems
        // officer on the right, exactly as in the real aircraft. The model in
        // this repository already contains that interior (Su34_Seat*, panel,
        // MFDs, HUD, consoles), so the external view is correct.
        //
        // These two empty transforms are our own markers: cameras, mission
        // logic and a future fully custom interactive cockpit can use them.
        // The actual player seats are the donor rigs moved by AlignCrewSeats().
        private static void AddCrewAnchors(GameObject root, List<string> report)
        {
            // Values match tools/su34_model/generate_su34.py: seats at x = +-0.30,
            // eye height 1.15, seat centre z = 6.40 (nose points along +Z).
            var existing = root.transform.Find("Su34_CrewSeats");
            GameObject seats = existing != null
                ? existing.gameObject
                : new GameObject("Su34_CrewSeats");
            seats.transform.SetParent(root.transform, false);
            seats.transform.localPosition = Vector3.zero;
            seats.transform.localRotation = Quaternion.identity;

            CreateAnchor(seats.transform, "CrewSeat_Pilot", new Vector3(-0.30f, 1.15f, 6.40f));
            CreateAnchor(seats.transform, "CrewSeat_WSO", new Vector3(0.30f, 1.15f, 6.40f));

            report.Add("crew anchors: CrewSeat_Pilot (-0.30, 1.15, 6.40), " +
                       "CrewSeat_WSO (+0.30, 1.15, 6.40) [side-by-side]");
            Debug.Log("[Su-34] crew anchors added (side-by-side pilot / WSO)");
        }

        private static void CreateAnchor(Transform parent, string name, Vector3 localPos)
        {
            var existing = parent.Find(name);
            GameObject go = existing != null ? existing.gameObject : new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPos;
            go.transform.localRotation = Quaternion.Euler(0f, 0f, 0f);
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
