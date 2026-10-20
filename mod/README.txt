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
scratch by the tools in the source repository (MIT licence).
