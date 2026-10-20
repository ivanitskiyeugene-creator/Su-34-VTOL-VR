<#
    Copies the finished mod into VTOL VR's Mod Loader folder.

    Usage:
        .\tools\install.ps1
        .\tools\install.ps1 -GamePath "D:\Steam\steamapps\common\VTOL VR"
        .\tools\install.ps1 -Uninstall

    Folder layout expected here:
        mod\item.json     mod\Su34Mod.dll     mod\su34 (asset bundle)     mod\su34.cfg
#>
[CmdletBinding()]
param(
    [string]$GamePath = "",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$modDir = Join-Path $repo "mod"

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
        $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
        $libs = @($steam)
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

if (-not $GamePath) { $GamePath = Find-VtolVr }
if (-not $GamePath) {
    throw "VTOL VR not found. Run: .\tools\install.ps1 -GamePath 'X:\Steam\steamapps\common\VTOL VR'"
}

$modsRoot = Join-Path $GamePath "@Mod Loader\Mods"
$target = Join-Path $modsRoot "Su-34"

if ($Uninstall) {
    if (Test-Path $target) {
        Remove-Item $target -Recurse -Force
        Write-Host "removed $target" -ForegroundColor Yellow
    } else {
        Write-Host "nothing to remove" -ForegroundColor Yellow
    }
    return
}

if (-not (Test-Path (Join-Path $modDir "Su34Mod.dll"))) {
    throw "mod\Su34Mod.dll is missing - run .\tools\build.ps1 first"
}
if (-not (Test-Path (Join-Path $modDir "su34"))) {
    Write-Host "WARNING: mod\su34 (asset bundle) is missing - the mod will load but the" -ForegroundColor Yellow
    Write-Host "         aircraft will not appear. Build it from the unity\ project." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item (Join-Path $modDir "*") $target -Recurse -Force
Write-Host "installed to: $target" -ForegroundColor Green
Write-Host ""
Write-Host "Launch VTOL VR through the VTOL VR Mod Loader, enable 'Su-34 Fullback'," -ForegroundColor Cyan
Write-Host "then pick the Su-34 in the pilot/vehicle selection screen." -ForegroundColor Cyan
