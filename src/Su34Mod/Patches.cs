using System;
using System.Reflection;
using HarmonyLib;

namespace Su34Mod
{
    /// <summary>
    /// Harmony patches that make the game treat the Su-34 like a built-in
    /// vehicle: it appears in the pilot/loadout UI, spawns in scenarios,
    /// multiplayer and the mission editor, and shares its weapons.
    ///
    /// Every patch is registered inside a try/catch. VTOL VR is updated
    /// regularly and a renamed method must never take the whole mod down - the
    /// log then tells you exactly which patch is missing for your game build.
    /// </summary>
    internal static class Patches
    {
        public static void Apply(Harmony harmony)
        {
            Try(harmony, "VTResources.LoadExternalVehicle", Patch_ExternalVehiclesAllowed.Apply);
            Try(harmony, "PilotSelectUI.StartSelectedPilotButton", Patch_PilotSelectRefresh.Apply);
            Try(harmony, "VehicleConfigSceneSetup.Start", Patch_VehicleConfigAllWeapons.Apply);
            Try(harmony, "LoadoutConfigurator.Initialize", Patch_LoadoutEquips.Apply);
            Try(harmony, "PlayerSpawn spawn hooks", Patch_PlayerSpawnScenarioVehicle.Apply);
            Try(harmony, "MultiplayerSpawn.PlayerSpawnRoutine (MP)", Patch_MultiplayerSpawnVehicle.Apply);
        }

        private static void Try(Harmony harmony, string label, Action<Harmony> apply)
        {
            try
            {
                apply(harmony);
                Su34Log.Info("patch ok: " + label);
            }
            catch (Exception e)
            {
                Su34Log.Warn("patch '" + label + "' could not be applied on this game build (" +
                             e.GetType().Name + ": " + e.Message + "). The mod still loads; " +
                             "that one feature will be missing.");
            }
        }

        private static MethodInfo Method(Type type, string name)
        {
            var mi = AccessTools.Method(type, name);
            if (mi == null) throw new MissingMethodException(type.Name + "." + name);
            return mi;
        }

        /// <summary>The game hides external vehicles behind a private flag.</summary>
        internal static class Patch_ExternalVehiclesAllowed
        {
            public static void Apply(Harmony harmony)
            {
                var target = Method(typeof(VTResources), "LoadExternalVehicle");
                harmony.Patch(target, prefix: new HarmonyMethod(
                    typeof(Patch_ExternalVehiclesAllowed).GetMethod(nameof(Prefix))));
            }

            public static bool Prefix()
            {
                var field = AccessTools.Field(typeof(VTResources), "canLoadExternalVehicles");
                if (field != null) field.SetValue(null, true);
                return true;
            }
        }

        /// <summary>Re-read the vehicle list so the new aircraft shows up in the UI.</summary>
        internal static class Patch_PilotSelectRefresh
        {
            public static void Apply(Harmony harmony)
            {
                var target = Method(typeof(PilotSelectUI), "StartSelectedPilotButton");
                harmony.Patch(target, prefix: new HarmonyMethod(
                    typeof(Patch_PilotSelectRefresh).GetMethod(nameof(Prefix))));
            }

            public static bool Prefix(PilotSelectUI __instance)
            {
                try
                {
                    AccessTools.Field(typeof(PilotSelectUI), "vehicles")
                        ?.SetValue(__instance, PilotSaveManager.GetVehicleList());
                }
                catch (Exception e)
                {
                    Su34Log.Warn("could not refresh pilot select list: " + e.Message);
                }
                return true;
            }
        }

        /// <summary>Let the configurator offer every weapon the vehicle owns.</summary>
        internal static class Patch_VehicleConfigAllWeapons
        {
            public static void Apply(Harmony harmony)
            {
                var target = Method(typeof(VehicleConfigSceneSetup), "Start");
                harmony.Patch(target, prefix: new HarmonyMethod(
                    typeof(Patch_VehicleConfigAllWeapons).GetMethod(nameof(Prefix))));
            }

            public static bool Prefix()
            {
                if (PilotSaveManager.currentVehicle == null ||
                    PilotSaveManager.currentVehicle.vehicleName != Main.AircraftName)
                    return true;
                try
                {
                    // Standalone scenarios ship their own allowed-equip lists; for
                    // external aircraft those are empty, so fall back to the
                    // vehicle definition.
                    PilotSaveManager.currentCampaign.isStandaloneScenarios = false;
                }
                catch (Exception e)
                {
                    Su34Log.Warn("vehicle config patch: " + e.Message);
                }
                return true;
            }
        }

        /// <summary>Fill the loadout screen with the Su-34's own equipment.</summary>
        internal static class Patch_LoadoutEquips
        {
            public static void Apply(Harmony harmony)
            {
                var target = Method(typeof(LoadoutConfigurator), "Initialize");
                harmony.Patch(target, prefix: new HarmonyMethod(
                    typeof(Patch_LoadoutEquips).GetMethod(nameof(Prefix))));
            }

            public static bool Prefix(LoadoutConfigurator __instance)
            {
                var pv = PilotSaveManager.currentVehicle;
                if (pv == null || pv.vehicleName != Main.AircraftName) return true;
                try
                {
                    var list = AccessTools.Field(typeof(LoadoutConfigurator), "availableEquipStrings")
                        ?.GetValue(__instance) as System.Collections.Generic.List<string>;
                    if (list == null) return true;

                    // Only replace the list when the vehicle really defines
                    // equipment, otherwise the loadout screen would go empty.
                    var wanted = pv.GetEquipNamesList();
                    if (wanted == null || wanted.Count == 0) return true;

                    list.Clear();
                    foreach (var equip in wanted)
                    {
                        if (!string.IsNullOrEmpty(equip)) list.Add(equip);
                    }
                }
                catch (Exception e)
                {
                    Su34Log.Warn("loadout patch: " + e.Message);
                }
                return true;
            }
        }

        /// <summary>Make missions spawn the selected external aircraft.</summary>
        internal static class Patch_PlayerSpawnScenarioVehicle
        {
            public static void Apply(Harmony harmony)
            {
                foreach (var name in new[] { "PlayerSpawnRoutine", "OnPreSpawnUnit" })
                {
                    var mi = AccessTools.Method(typeof(PlayerSpawn), name);
                    if (mi == null) continue;
                    harmony.Patch(mi, prefix: new HarmonyMethod(
                        typeof(Patch_PlayerSpawnScenarioVehicle).GetMethod(nameof(Prefix))));
                }
            }

            public static bool Prefix()
            {
                var pv = PilotSaveManager.currentVehicle;
                if (pv != null && pv.vehicleName == Main.AircraftName && VTScenario.current != null)
                {
                    VTScenario.current.vehicle = pv;
                }
                return true;
            }
        }

        /// <summary>
        /// Multiplayer spawns use their own path through the same data. The
        /// class lives in the VTOLVR.Multiplayer namespace on some builds, so
        /// it is resolved by name instead of a compile-time reference.
        /// </summary>
        internal static class Patch_MultiplayerSpawnVehicle
        {
            public static void Apply(Harmony harmony)
            {
                var type = AccessTools.TypeByName("MultiplayerSpawn")
                           ?? AccessTools.TypeByName("VTOLVR.Multiplayer.MultiplayerSpawn")
                           ?? AccessTools.TypeByName("MPPlayerSpawn");
                if (type == null) throw new TypeLoadException("MultiplayerSpawn not found");
                var target = Method(type, "PlayerSpawnRoutine");
                harmony.Patch(target, prefix: new HarmonyMethod(
                    typeof(Patch_MultiplayerSpawnVehicle).GetMethod(nameof(Prefix))));
            }

            public static bool Prefix()
            {
                var pv = PilotSaveManager.currentVehicle;
                if (pv != null && pv.vehicleName == Main.AircraftName && VTScenario.current != null)
                {
                    VTScenario.current.vehicle = pv;
                }
                return true;
            }
        }
    }
}
