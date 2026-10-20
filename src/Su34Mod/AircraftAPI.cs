using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using HarmonyLib;
using UnityEngine;
using VTNetworking;

namespace Su34Mod
{
    /// <summary>
    /// Loads the Su-34 asset bundle into the game as an external player vehicle
    /// and cleans everything back up when the mod is disabled.
    ///
    /// API notes (VTOL VR 1.12 / 1.13, Mod Loader 6.x):
    ///   VTResources.OnLoadingPlayerVehicles  - fired while the vehicle list is built
    ///   VTResources.FinallyLoadExtVehicleAsync(path, prefabName) - loads a bundle
    ///   ExternalVehicleInfo on the prefab root - vehicle metadata read by the game
    /// </summary>
    internal static class AircraftAPI
    {
        public static AssetBundle Bundle { get; private set; }
        public static PlayerVehicle PlayerVehicle { get; private set; }
        public static bool LoadInProgress { get; private set; }

        private static readonly List<string> OverriddenResources = new List<string>();
        private static readonly List<TargetIdentity> RegisteredIdentities = new List<TargetIdentity>();

        public static void VehicleAdd()
        {
            if (LoadInProgress || PlayerVehicle != null) return;

            if (!File.Exists(Main.BundlePath))
            {
                Su34Log.Error("asset bundle not found at " + Main.BundlePath +
                              " - rebuild unity/ and copy the bundle next to the dll");
                return;
            }

            var host = new GameObject("Su34VehicleLoader");
            UnityEngine.Object.DontDestroyOnLoad(host);
            host.AddComponent<AsyncVehicleLoader>().Begin(Main.BundlePath, Main.PrefabName);
        }

        public static void VehicleRemove()
        {
            foreach (var path in OverriddenResources)
            {
                VTResources.ResetOverriddenResource(path);
                VTNetworkManager.overriddenResources.Remove(path);
            }
            OverriddenResources.Clear();

            if (PlayerVehicle != null)
            {
                if (!string.IsNullOrEmpty(PlayerVehicle.resourcePath))
                {
                    VTResources.ResetOverriddenResource(PlayerVehicle.resourcePath);
                    VTNetworkManager.overriddenResources.Remove(PlayerVehicle.resourcePath);
                }
                VTResources.finalPVList.Remove(PlayerVehicle);
                VTResources.pvDict.Remove(PlayerVehicle.vehicleName);
                var info = PlayerVehicle.vehiclePrefab != null
                    ? PlayerVehicle.vehiclePrefab.GetComponent<ExternalVehicleInfo>()
                    : null;
                if (info != null) VTResources.loadedExternalVehicles.Remove(info);
            }

            foreach (var identity in RegisteredIdentities)
            {
                TargetIdentityManager.indexedIdentities.Remove(identity);
                TargetIdentityManager.identityDict.Remove(identity.targetId);
            }
            RegisteredIdentities.Clear();
            SortIdentities();

            if (Bundle != null)
            {
                try { Bundle.Unload(true); }
                catch (Exception e) { Su34Log.Warn("bundle unload: " + e.Message); }
                Bundle = null;
            }
            PlayerVehicle = null;
            LoadInProgress = false;
        }

        internal static void SetReady(AssetBundle bundle, PlayerVehicle vehicle)
        {
            Bundle = bundle;
            PlayerVehicle = vehicle;
            LoadInProgress = false;
            Main.MarkRegistered();
        }

        internal static void SetLoading(bool value) { LoadInProgress = value; }

        internal static void TrackIdentity(TargetIdentity identity)
        {
            if (identity != null && !RegisteredIdentities.Contains(identity))
                RegisteredIdentities.Add(identity);
        }

        internal static void TrackOverride(string resourcePath)
        {
            if (!string.IsNullOrEmpty(resourcePath) && !OverriddenResources.Contains(resourcePath))
                OverriddenResources.Add(resourcePath);
        }

        internal static void SortIdentities()
        {
            TargetIdentityManager.indexedIdentities.Sort(TargetIdentityManager.IdentSorter);
            for (int i = 0; i < TargetIdentityManager.indexedIdentities.Count; i++)
                TargetIdentityManager.indexedIdentities[i].index = i;
        }

        /// <summary>
        /// Registers the aircraft so AI / radar / replays know about it.
        /// Also registers the aircraft's loadout missiles, which is what makes
        /// custom weapons show up in the loadout configurator.
        /// </summary>
        internal static void RegisterAircraft(PlayerVehicle pv)
        {
            var identity = TargetIdentityManager.RegisterNonSpawnIdentity(
                pv.vehicleName, pv.vehicleName, Actor.Roles.Air);
            if (!TargetIdentityManager.indexedIdentities.Contains(identity))
            {
                identity.index = TargetIdentityManager.indexedIdentities.Count;
                TargetIdentityManager.indexedIdentities.Add(identity);
            }
            TrackIdentity(identity);
            SortIdentities();

            var wm = pv.vehiclePrefab != null ? pv.vehiclePrefab.GetComponent<WeaponManager>() : null;
            if (wm == null || pv.allEquipPrefabs == null) return;

            foreach (var equipPrefab in pv.allEquipPrefabs)
            {
                if (equipPrefab == null) continue;
                TrackOverride(wm.resourcePath + "/" + equipPrefab.name);

                var ml = equipPrefab.GetComponent<HPEquipMissileLauncher>();
                if (ml == null || ml.ml == null || ml.ml.missilePrefab == null) continue;

                var missile = ml.ml.missilePrefab;
                BuiltMixerFixer.FixAudioSourcesInChildren(missile);
                VTResources.RegisterOverriddenResource(ml.missileResourcePath, missile);
                VTNetworkManager.RegisterOverrideResource(ml.missileResourcePath, missile);
                TrackOverride(ml.missileResourcePath);

                var unitId = missile.GetComponent<UnitIDIdentifier>();
                if (unitId == null)
                {
                    unitId = missile.AddComponent<UnitIDIdentifier>();
                    unitId.targetName = missile.name;
                    unitId.unitID = "su34." + missile.name.ToLowerInvariant();
                    unitId.role = Actor.Roles.Missile;
                }
                if (unitId.unitID != null && unitId.unitID.ToLowerInvariant().StartsWith("su34."))
                {
                    var missileIdentity = TargetIdentityManager.RegisterNonSpawnIdentity(
                        unitId.unitID, unitId.targetName, unitId.role);
                    TrackIdentity(missileIdentity);
                }
            }
        }
    }

    /// <summary>
    /// Coroutine driver around VTResources.FinallyLoadExtVehicleAsync, plus the
    /// shader / LOD / scenario fix-ups the game normally does for its own craft.
    /// </summary>
    public class AsyncVehicleLoader : MonoBehaviour
    {
        public void Begin(string pathToBundle, string prefabName)
        {
            StartCoroutine(LoadRoutine(pathToBundle, prefabName));
        }

        private IEnumerator LoadRoutine(string pathToBundle, string prefabName)
        {
            AircraftAPI.SetLoading(true);
            Su34Log.Info("loading bundle " + pathToBundle + " (prefab '" + prefabName + "')");

            AsyncOperation op = null;
            try
            {
                op = VTResources.FinallyLoadExtVehicleAsync(pathToBundle, prefabName);
            }
            catch (Exception e)
            {
                Su34Log.Exception(e, "FinallyLoadExtVehicleAsync threw");
            }

            if (op != null)
            {
                while (!op.isDone)
                {
                    yield return null;
                }
            }

            PlayerVehicle pv = null;
            try
            {
                pv = VTResources.GetPlayerVehicle(Main.AircraftName);
            }
            catch (Exception e)
            {
                Su34Log.Exception(e, "GetPlayerVehicle threw");
            }

            if (pv == null)
            {
                Su34Log.Error("the game did not register the vehicle - check that the prefab " +
                              "is named '" + prefabName + "' and carries ExternalVehicleInfo");
                AircraftAPI.SetLoading(false);
                Destroy(gameObject);
                yield break;
            }

            // Find the bundle instance the game just loaded (used for clean unload).
            AssetBundle bundle = null;
            foreach (var b in AssetBundle.GetAllLoadedAssetBundles())
            {
                if (b.name == Path.GetFileName(Main.BundlePath) || b.name == Main.BundleFileName)
                {
                    bundle = b;
                    break;
                }
            }

            // VTOLAPI is an optional workshop dependency, so it is called
            // through reflection (see Compat.TryFixShaders).
            Compat.TryFixShaders(pv.vehiclePrefab, false, true, true);

            try
            {
                VTResources.LoadStandaloneLODInfos(false, false);
                pv.standaloneCustomScenarios = VTResources.GenerateStandaloneCustomScenarios(Main.AircraftName);
            }
            catch (Exception e)
            {
                Su34Log.Warn("standalone scenario generation failed (non-fatal): " + e.Message);
            }

            try
            {
                AircraftAPI.RegisterAircraft(pv);
            }
            catch (Exception e)
            {
                Su34Log.Exception(e, "identity registration failed");
            }

            AircraftAPI.SetReady(bundle, pv);
            Su34Log.Info("vehicle ready: " + pv.vehicleName);

            if (bundle != null) bundle.Unload(false);
            Destroy(gameObject);
        }
    }
}
