# Unity: сборка самолётного asset bundle

Этот проект Unity нужен ровно для одного: превратить `assets/model/su34.obj`
в asset bundle `su34`, который читает мод. Всё остальное (код, полётная модель,
кабина, оружие) приходит из префаба F/A-26B, который вы экспортируете из своей
копии VTOL VR.

> **Важно.** Файлы игры вы экспортируете сами, на своём компьютере. В репозитории
> нет ни одного файла из VTOL VR — только наш собственный OBJ-меш.

## 1. Один раз: Unity нужной версии

VTOL VR собран на Unity 2020.3.x. Точную версию видно:

* в `player.log` (третья строка: `Initialize engine version: 2020.3.xx`), или
* в `ProjectSettings/ProjectVersion.txt` после экспорта игры AssetRipper'ом.

Поставьте через Unity Hub именно эту версию, с модулем **Windows Build Support
(Mono)**. Unity 2020.3.48f1 / 2020.3.49f1 — то, на чём собирает сообщество.

## 2. Один раз: экспорт игры в Unity-проект

1. Скачайте **AssetRipper** (https://github.com/AssetRipper/AssetRipper/releases),
   запустите `AssetRipper.GUI.Free.exe`.
2. Перетащите в него папку `...\steamapps\common\VTOL VR` целиком.
3. `Export > Export All Files`, выберите пустую папку.
4. После экспорта:
   * удалите папку `AuxiliaryFiles`;
   * перенесите содержимое `ExportedProject` в корень вашей папки проекта;
   * в `Assets/Plugins` удалите все DLL движка Unity и SteamVR;
   * удалите шейдер `Hidden_UIElements_EditorUIE`;
   * через Package Manager поставьте `TextMeshPro`, `XR Plugin Management`,
     `2D Sprite`, `Input System`;
   * из SteamVR Plugin (Asset Store) импортируйте плагин, **сняв галочку** с
     `JSON.NET / Valve.Newtonsoft.Json.dll`.
5. Скопируйте в `Assets/Plugins` DLL из `VTOL VR/VTOLVR_Data/Managed`:
   `Assembly-CSharp.dll`, `Assembly-CSharp-firstpass.dll`, `0Harmony.dll`,
   `ModLoader.Framework.dll` (последние две — из `@Mod Loader/Managed`),
   `Facepunch.Steamworks.Win64.dll`, `Unity.TextMeshPro.dll`.
6. Откройте проект в Unity. Первый запуск долгий, это нормально.

Если Unity ругается на `ControlMapper.cs` — в официальной инструкции
(https://vtolvr-mods.com/docs/vtolvr/asset-ripper/) написано, какую строку
закомментировать.

## 3. Подключить файлы этого репозитория

1. Скопируйте папку `unity/Assets/Su34` в `Assets/` вашего Unity-проекта.
2. Скопируйте `assets/model/su34.obj` и `assets/model/su34.mtl` в
   `Assets/Su34/Models/` (папку создайте, если её нет).
3. В Unity дождитесь импорта OBJ (он появится как префаб с мешами).

## 4. Сборка

В меню Unity появятся пункты **VTOL VR / Su-34**:

| Пункт | Что делает |
|---|---|
| `0 - Check setup` | проверяет, что на месте префаб-донор и модель |
| `1 - Dump donor hierarchy` | пишет в корень проекта `Su34_donor_hierarchy.txt` со всеми объектами донора — по нему видно, какие части кабины оставить |
| `2 - Build prefab + asset bundle` | собирает `Su34.prefab`, бандл `su34` и копирует его в `mod/` этого репозитория |
| `3 - Build DLL and install into the game` | запускает `tools/build.ps1 -Deploy`: собирает `Su34Mod.dll` и ставит всё в `@Mod Loader/Mods/Su-34` |

Префаб-донор ищется автоматически: сначала по пути `Assets/Resources/vehicles/FA-26B.prefab`,
если его нет — поиском по проекту среди `*.prefab`, в пути которых есть «vehicle».
Выбранный путь печатается в консоль.

После `2 - ...` в `mod/` появятся:

```
mod/su34               <- asset bundle (его и грузит мод)
mod/build_report.txt   <- что скрыто, что оставлено из кабины донора
```

Если Unity пишет, что не нашёл `Assets/Resources/vehicles/FA-26B.prefab` —
откройте `Su34_donor_hierarchy.txt` (или поиск в Project) и поправьте константу
`DonorPrefabPath` в `Assets/Su34/Editor/Su34BundleBuilder.cs`.

## Как это устроено

`Su34BundleBuilder`:

1. грузит префаб F/A-26B (в нём уже есть полётная модель, шасси, оружие,
   MFD, VR-интерактивы и кабина);
2. переименовывает его в `Su34`, добавляет `ExternalVehicleInfo` и заполняет
   имя/описание/никнейм;
3. вставляет под корень наш `su34.obj` (`Su34_Visual`);
4. отключает у донора **внешние** рендереры (фюзеляж, крылья, шасси-меши),
   оставляя всё, что похоже на кабину (`cockpit`, `seat`, `mfd`, `hud`,
   `canopy`, `panel`, `switch`, ...). Полный список — в `build_report.txt`;
5. сохраняет префаб, помечает его в бандл `su34` и собирает
   `StandaloneWindows64`.

Такой путь даёт полностью рабочий самолёт: кликабельная кабина, оружие,
радар, HUD, посадка на палубу — всё от донора, а снаружи и в анфас — Су-34.

## Замена модели на hi-poly

Модель в репозитории — процедурная, ~7 тысяч треугольников, силуэт правильный,
но это не фотореализм. Чтобы поставить нормальную модель:

1. возьмите Su-34 с нормальной лицензией (CC-BY / купленную / заказанную у
   3D-художника) — **не** выдранную из War Thunder или другой игры;
2. импортируйте FBX в Unity, поверните носом по +Z, масштаб 1:1 в метрах
   (длина 23.3 м, размах 14.7 м);
3. вынесите рули/закрылки/шасси в отдельные объекты, если хотите анимацию;
4. положите префаб в `Assets/Su34/Models/` и в `Su34BundleBuilder.AttachModel`
   замените загрузку OBJ на свой префаб (одна строка).

Инструкция по подготовке меша (разрезка рулей, шарниры, UV) —
`docs/МОДЕЛЬ.md`.
