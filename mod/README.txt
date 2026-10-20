SU-34 FULLBACK for VTOL VR
==========================

Install
-------
1. Install "VTOL VR Mod Loader" from Steam (app 3018410). It must sit on the
   same drive as VTOL VR.
2. Copy this whole "Su-34" folder into
      <Steam>\steamapps\common\VTOL VR\@Mod Loader\Mods\Su-34\
   The folder must contain:
      item.json
      Su34Mod.dll
      su34            (asset bundle, no extension)
      su34.cfg
3. Subscribe to and enable the "VTOLAPI" workshop mod (needed for the shader
   fix-up of external aircraft).
4. Launch VTOL VR through the Mod Loader, enable "Su-34 Fullback", press Play.
   The aircraft appears in the pilot / vehicle selection screen.

Two players
-----------
The Su-34 is a two-crew aircraft. In VTOL VR a second player slot exists only
when the vehicle prefab has two seat rigs, so this package must be built on the
EF-24G or the T-55 prefab (both DLC). The builder puts those two seats side by
side: pilot left, WSO right.

In the mission editor select the player spawn and set it to 2 slots (the
default is 1 - that is why "the second player cannot join" in most mods).
Then host the mission and let the second player pick the same aircraft.

If the package was built on the single-seat F/A-26B (no DLC installed), the
aircraft still flies, but only one player can crew it. build_report.txt says
"crew seat rigs found: 1" in that case.

Tuning
------
Edit su34.cfg (mass, thrust scale, control response). Restart the game after
changing it.

Troubleshooting
---------------
The mod writes to the game's Output.log with the prefix [Su-34]. Check:
  "asset bundle not found"          -> the file "su34" is missing or renamed
  "the game did not register"       -> Unity bundle was built without
                                       ExternalVehicleInfo or wrong prefab name
  "patch '...' could not be applied" -> game update renamed a method; the rest
                                       of the mod still works

Press F10 in flight for an on-screen diagnostic overlay.

This package contains no VTOL VR game files. The 3D model was generated from
scratch by the tools in the source repository (MIT licence). The flight model,
cockpit interactables and seat rigs come from the VTOL VR vehicle the package
was built on, exactly like other aircraft mods that require a DLC donor.
