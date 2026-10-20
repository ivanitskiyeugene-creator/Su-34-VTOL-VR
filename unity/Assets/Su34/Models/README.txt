Put su34.obj and su34.mtl here (copy from ../../../../assets/model/).

The Unity builder (VTOL VR / Su-34 / 2 - Build prefab + asset bundle) loads
Assets/Su34/Models/su34.obj, instantiates it under the donor prefab as
"Su34_Visual" and builds the "su34" asset bundle.

If you replace the procedural model with your own prefab/FBX, point
Su34BundleBuilder.ModelObjPath at it (or drop a prefab with the same name
here and change the one LoadAssetAtPath call).
