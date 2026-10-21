﻿<#
    prepare_unity_project.ps1 - собирает Unity-проект для мода Су-34 из
    выгрузки AssetRipper и файлов этого репозитория.

    Что делает:
      1. находит установленный VTOL VR и печатает версию Unity из Player.log;
      2. копирует ExportedProject (без AuxiliaryFiles) в папку проекта;
      3. удаляет Assets\Plugins, на котором Unity обычно падает;
      4. кладёт Assets\Su34 из репозитория;
      5. копирует модель, её .mtl и текстуры в Assets\Su34\Models;
      6. создаёт Assets\Plugins заново и копирует туда шесть DLL из игры.

    Чего он НЕ делает (это только руками в редакторе Unity):
      Package Manager (TextMeshPro, XR Plugin Management, 2D Sprite,
      Input System), SteamVR Plugin с Asset Store, Assets > Reimport All.

    Примеры (из корня репозитория, в PowerShell):

        .\tools\prepare_unity_project.ps1 -Export "D:\RipperExport" -Project "D:\VTOLVR_Project"

        # если игра стоит не в стандартном месте
        .\tools\prepare_unity_project.ps1 -Export "D:\RipperExport" -Project "D:\VTOLVR_Project" `
            -GamePath "E:\SteamLibrary\steamapps\common\VTOL VR"

        # проверить, что скрипт собирается делать, ничего не трогая
        .\tools\prepare_unity_project.ps1 -Export ... -Project ... -WhatIf

    Замечание: -WhatIf здесь показывает только удаление Assets\Plugins;
    копирование 20-30 ГБ скрипт всё равно выполнит.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$Export,
    [Parameter(Mandatory = $true)][string]$Project,
    [string]$GamePath = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

# Имя модели. Должно совпадать с Su34BundleBuilder.ModelFileName.
$ModelFile = "su34_donor.obj"
$ExpectedUnity = "2020.3.49f1"

function Fail([string]$message) {
    Write-Host ""
    Write-Host "ОШИБКА: $message" -ForegroundColor Red
    exit 1
}

function Info([string]$message) { Write-Host $message -ForegroundColor Gray }
function Step([string]$message) { Write-Host ("== " + $message) -ForegroundColor Cyan }

# --------------------------------------------------------------- 1. игра и Unity
function Find-VtolVr {
    param([string]$explicit)
    if ($explicit) { return $explicit }
    $candidates = @(
        "C:\Program Files (x86)\Steam\steamapps\common\VTOL VR",
        "C:\Program Files\Steam\steamapps\common\VTOL VR",
        "D:\Steam\steamapps\common\VTOL VR",
        "D:\SteamLibrary\steamapps\common\VTOL VR",
        "E:\SteamLibrary\steamapps\common\VTOL VR",
        "F:\SteamLibrary\steamapps\common\VTOL VR",
        "G:\SteamLibrary\steamapps\common\VTOL VR"
    )
    foreach ($path in $candidates) {
        if (Test-Path (Join-Path $path "VTOLVR_Data\Managed\Assembly-CSharp.dll")) { return $path }
    }
    try {
        $steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam" -ErrorAction Stop).SteamPath
        $libs = @($steam)
        $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
        if (Test-Path $vdf) {
            $libs += Select-String -Path $vdf -Pattern '"path"\s+"(.+?)"' |
                ForEach-Object { $_.Matches[0].Groups[1].Value.Replace('\\', '\') }
        }
        foreach ($lib in $libs) {
            $p = Join-Path $lib "steamapps\common\VTOL VR"
            if (Test-Path (Join-Path $p "VTOLVR_Data\Managed\Assembly-CSharp.dll")) { return $p }
        }
    } catch { }
    return ""
}

Step "1/6 проверяю игру и Unity"

$GamePath = Find-VtolVr -explicit $GamePath
if (-not $GamePath) {
    Fail "VTOL VR не найден. Запустите скрипт с -GamePath 'X:\Steam\steamapps\common\VTOL VR'."
}
if (-not (Test-Path (Join-Path $GamePath "VTOLVR_Data\Managed\Assembly-CSharp.dll"))) {
    Fail "в '$GamePath' нет VTOLVR_Data\Managed\Assembly-CSharp.dll - путь неверный."
}
Info ("игра:      " + $GamePath)

# версия Unity из лога игры - то, под что нужно собирать бандл
$log = Join-Path $env:USERPROFILE "AppData\LocalLow\Boundless Dynamics, LLC\VTOLVR\Player.log"
if (Test-Path $log) {
    $line = Select-String -Path $log -Pattern "Initialize engine version" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($line) {
        Info ("лог:       " + $line.Line.Trim())
        if ($line.Line -notmatch [regex]::Escape($ExpectedUnity)) {
            Write-Host ("ВНИМАНИЕ:  в логе не $ExpectedUnity. Если игра обновилась, поставьте в Unity Hub" +
                        " ту версию, что написана в строке выше, и пересоберите бандл.") -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "ВНИМАНИЕ:  Player.log не найден - запустите игру хотя бы раз, чтобы проверить версию Unity." -ForegroundColor Yellow
}

$unityCandidates = @(
    (Join-Path $env:ProgramFiles "Unity\Hub\Editor\$ExpectedUnity\Editor\Unity.exe"),
    ("C:\Program Files\Unity $ExpectedUnity\Editor\Unity.exe"),
    (Join-Path $env:ProgramFiles "Unity $ExpectedUnity\Editor\Unity.exe")
)
$unity = $unityCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($unity) {
    Info ("unity:     " + $unity)
} else {
    Write-Host ("ВНИМАНИЕ:  Unity $ExpectedUnity не найдена в стандартных папках. " +
                "Если она стоит в другом месте - это нормально, просто откройте проект ею вручную.") -ForegroundColor Yellow
}

# ------------------------------------------------------------- 2. выгрузка игры
Step "2/6 проверяю выгрузку AssetRipper"

if (-not (Test-Path $Export)) { Fail "папка выгрузки не найдена: $Export" }
$source = $Export
$inner = Join-Path $Export "ExportedProject"
if (Test-Path $inner) { $source = $inner }   # AssetRipper кладёт всё в ExportedProject

if (-not (Test-Path (Join-Path $source "Assets"))) {
    Fail ("в '$source' нет папки Assets. Укажите папку, куда AssetRipper сделал " +
          "Export > Export All Files.")
}
if (-not (Test-Path (Join-Path $source "ProjectSettings"))) {
    Write-Host "ВНИМАНИЕ:  нет ProjectSettings - выгрузка выглядит неполной." -ForegroundColor Yellow
}
Info ("выгрузка:  " + $source)

if (Test-Path $Project) {
    $existing = Get-ChildItem -Path $Project -Force | Select-Object -First 1
    if ($existing -and -not $Force) {
        Fail ("папка проекта не пустая: $Project. Возьмите новую папку или добавьте -Force, " +
              "чтобы дописать в существующую.")
    }
}

# ------------------------------------------------------------------ 3. копия
Step "3/6 копирую проект (это долго: 10-40 минут и 20-30 ГБ)"

if (-not (Test-Path $Project)) { New-Item -ItemType Directory -Path $Project -Force | Out-Null }

# ExportedProject уже развёрнут в $source, поэтому копируем его содержимое.
# AuxiliaryFiles не нужны и весят много.
$robocopyArgs = @($source, $Project, "/E", "/XD", "AuxiliaryFiles",
                  "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1")
Write-Host ("robocopy " + ($robocopyArgs -join " ")) -ForegroundColor DarkGray
robocopy @robocopyArgs | Out-Null
$code = $LASTEXITCODE
if ($code -ge 8) { Fail "robocopy вернул код $code - копирование не удалось (нет места? нет прав?)." }
$LASTEXITCODE = 0

# ------------------------------------------------------- 4. чистка Plugins
Step "4/6 убираю Assets\Plugins (DLL движка и SteamVR валят Unity)"

$plugins = Join-Path $Project "Assets\Plugins"
if (Test-Path $plugins) {
    if ($PSCmdlet.ShouldProcess($plugins, "удалить папку")) {
        Remove-Item -Path $plugins -Recurse -Force
        Info "удалено: $plugins"
    }
}

# ------------------------------------------------------- 5. наши ассеты
Step "5/6 копирую Assets\Su34 и модель"

$srcSu34 = Join-Path $repo "unity\Assets\Su34"
if (-not (Test-Path $srcSu34)) { Fail "не найдена папка unity\Assets\Su34 в репозитории: $repo" }

$dstSu34 = Join-Path $Project "Assets\Su34"
New-Item -ItemType Directory -Path $dstSu34 -Force | Out-Null
Copy-Item -Path (Join-Path $srcSu34 "*") -Destination $dstSu34 -Recurse -Force
Info "билдер:    $dstSu34"

$modelDir = Join-Path $dstSu34 "Models"
$texDir = Join-Path $modelDir "textures"
New-Item -ItemType Directory -Path $texDir -Force | Out-Null

$repoModel = Join-Path $repo "assets\model"
if (-not (Test-Path (Join-Path $repoModel $ModelFile))) {
    Fail "в репозитории нет $ModelFile (папка $repoModel). Скачайте репозиторий целиком."
}
Copy-Item (Join-Path $repoModel $ModelFile) $modelDir -Force
$mtl = [System.IO.Path]::ChangeExtension($ModelFile, ".mtl")
Copy-Item (Join-Path $repoModel $mtl) $modelDir -Force
Copy-Item (Join-Path $repoModel "textures\donor_*.png") $texDir -Force
$pngCount = (Get-ChildItem $texDir -Filter *.png).Count
Info ("модель:    $ModelFile + $mtl + $pngCount текстур")

# ------------------------------------------------------- 6. DLL из игры
Step "6/6 копирую DLL игры в Assets\Plugins"

$dstPlugins = Join-Path $Project "Assets\Plugins"
New-Item -ItemType Directory -Path $dstPlugins -Force | Out-Null

$managed = Join-Path $GamePath "VTOLVR_Data\Managed"
$loaderManaged = Join-Path $GamePath "@Mod Loader\Managed"

$dlls = @(
    @{ Name = "Assembly-CSharp.dll";            From = $managed },
    @{ Name = "Assembly-CSharp-firstpass.dll";  From = $managed },
    @{ Name = "Facepunch.Steamworks.Win64.dll"; From = $managed },
    @{ Name = "Unity.TextMeshPro.dll";          From = $managed },
    @{ Name = "0Harmony.dll";                   From = $loaderManaged },
    @{ Name = "ModLoader.Framework.dll";        From = $loaderManaged }
)

$missing = @()
foreach ($dll in $dlls) {
    $src = Join-Path $dll.From $dll.Name
    if (-not (Test-Path $src)) {
        # мод-лоадер 6.10.x мог переехать - ищем рядом
        $found = Get-ChildItem -Path (Join-Path $GamePath "@Mod Loader") -Filter $dll.Name `
            -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $src = $found.FullName }
    }
    if (Test-Path $src) {
        Copy-Item $src $dstPlugins -Force
        Info ("  + " + $dll.Name)
    } else {
        $missing += $dll.Name
    }
}
if ($missing.Count -gt 0) {
    Write-Host ("ВНИМАНИЕ:  не найдены: " + ($missing -join ", ")) -ForegroundColor Yellow
    Write-Host ("Ищите их в $managed и $loaderManaged. Без Assembly-CSharp.dll " +
                "билдер не соберётся.") -ForegroundColor Yellow
}

# ------------------------------------------------------------------ итог
Write-Host ""
Write-Host "Проект готов: $Project" -ForegroundColor Green
Write-Host ""
Write-Host "Дальше, руками в Unity:" -ForegroundColor Cyan
Write-Host "  1. Unity Hub -> Add -> $Project, открыть редактором $ExpectedUnity"
Write-Host "     (первый импорт 10-40 минут; 'Enter Safe Mode' -> Ignore)"
Write-Host "  2. Package Manager: TextMeshPro ('No Thanks' на импорт примеров),"
Write-Host "     XR Plugin Management, 2D Sprite, Input System"
Write-Host "  3. Asset Store -> SteamVR Plugin -> Import, СНЯТЬ галочку с"
Write-Host "     SteamVR\Input\Plugins\JSON.NET\Valve.Newtonsoft.Json.dll"
Write-Host "  4. Assets -> Reimport All (ошибок быть не должно)"
Write-Host "  5. меню VTOL VR / Su-34: '0b - Check setup', затем '2 - Build prefab + asset bundle'"
Write-Host ""
