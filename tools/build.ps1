<#
    Builds Su34Mod.dll and stages the complete mod folder.

    Usage (from the repository root, PowerShell):
        .\tools\build.ps1
        .\tools\build.ps1 -GamePath "D:\Steam\steamapps\common\VTOL VR"
        .\tools\build.ps1 -Deploy          # also install into the game

    Requires the .NET SDK (8.x is fine, the project targets .NET Framework 4.7.2)
    and, for the asset bundle, Unity 2020.3.x (see unity/README.md).
#>
[CmdletBinding()]
param(
    [string]$GamePath = "",
    [switch]$Deploy
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

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
    # try the registry
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

if (-not $GamePath) { $GamePath = Find-VtolVr }
if (-not $GamePath -or -not (Test-Path (Join-Path $GamePath "VTOLVR_Data\Managed\Assembly-CSharp.dll"))) {
    throw "VTOL VR not found. Run: .\tools\build.ps1 -GamePath 'X:\Steam\steamapps\common\VTOL VR'"
}
Write-Host "VTOL VR: $GamePath" -ForegroundColor Cyan

# ---------------------------------------------------------------- build the dll
$project = Join-Path $repo "src\Su34Mod\Su34Mod.csproj"
$outDir = Join-Path $repo "build\mod"
& dotnet build $project -c Release -p:VtolDir="$GamePath" -o "$outDir"
if ($LASTEXITCODE -ne 0) { throw "dotnet build failed" }

$dll = Join-Path $outDir "Su34Mod.dll"
if (-not (Test-Path $dll)) { throw "Su34Mod.dll was not produced" }

# ------------------------------------------------------------- stage mod folder
$modDir = Join-Path $repo "mod"
Copy-Item $dll (Join-Path $modDir "Su34Mod.dll") -Force
if (Test-Path (Join-Path $outDir "Su34Mod.pdb")) {
    Copy-Item (Join-Path $outDir "Su34Mod.pdb") (Join-Path $modDir "Su34Mod.pdb") -Force
}
Write-Host "staged: $modDir" -ForegroundColor Green

if (-not (Test-Path (Join-Path $modDir "su34"))) {
    Write-Host ""
    Write-Host "NOTE: mod\su34 (the aircraft asset bundle) is missing." -ForegroundColor Yellow
    Write-Host "      Open the unity\ project in Unity 2020.3.x and run" -ForegroundColor Yellow
    Write-Host "      'VTOL VR / Su-34 / 2 - Build prefab + asset bundle'." -ForegroundColor Yellow
    Write-Host "      See unity\README.md for the one-time setup." -ForegroundColor Yellow
}

if ($Deploy) {
    $target = Join-Path $GamePath "@Mod Loader\Mods\Su-34"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item (Join-Path $modDir "*") $target -Recurse -Force
    Write-Host "installed to: $target" -ForegroundColor Green
}
