param(
    [Parameter(Mandatory = $true)]
    [string]$Source,
    [Parameter(Mandatory = $true)]
    [string]$Destination,
    [string]$BabelDocCache = "$env:USERPROFILE\.cache\babeldoc",
    [string]$BuildPython = "",
    [string]$BabelDocVersion = "0.6.4"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Resolve-PathFromProject {
    param([string]$Value)
    if ([IO.Path]::IsPathRooted($Value)) { return [IO.Path]::GetFullPath($Value) }
    return [IO.Path]::GetFullPath((Join-Path $projectRoot $Value))
}

function Copy-DirectoryContents {
    param([string]$From, [string]$To)
    if (-not (Test-Path -LiteralPath $From -PathType Container)) {
        throw "Directory does not exist: $From"
    }
    New-Item -ItemType Directory -Path $To -Force | Out-Null
    Get-ChildItem -LiteralPath $From -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $To -Recurse -Force
    }
}

$sourceRoot = Resolve-PathFromProject $Source
$destinationRoot = Resolve-PathFromProject $Destination

# Accept a venv/backend path directly, or the root of an existing Full edition.
foreach ($childName in @("TranslationEngine", "backend")) {
    $candidate = Join-Path $sourceRoot $childName
    if (Test-Path -LiteralPath (Join-Path $candidate "babeldoc.exe") -PathType Leaf) {
        $sourceRoot = $candidate
        break
    }
}

if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    throw "BabelDOC source does not exist: $sourceRoot"
}
if (Test-Path -LiteralPath $destinationRoot) {
    throw "BabelDOC destination must not already exist: $destinationRoot"
}

$destinationParent = Split-Path -Parent $destinationRoot
if (-not (Test-Path -LiteralPath $destinationParent -PathType Container)) {
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
}
New-Item -ItemType Directory -Path $destinationRoot | Out-Null

$sourcePortablePython = Join-Path $sourceRoot "python\python.exe"
$sourceSitePackages = Join-Path $sourceRoot "site-packages"
$sourceVenvPython = Join-Path $sourceRoot "Scripts\python.exe"
$destinationPython = Join-Path $destinationRoot "python"
$destinationSitePackages = Join-Path $destinationRoot "site-packages"
$destinationRuntime = Join-Path $destinationRoot "runtime"

if ((Test-Path -LiteralPath $sourcePortablePython -PathType Leaf) -and
    (Test-Path -LiteralPath $sourceSitePackages -PathType Container)) {
    Write-Host "Copying an existing portable BabelDOC runtime (read-only source)..."
    Copy-DirectoryContents (Join-Path $sourceRoot "python") $destinationPython
    Copy-DirectoryContents $sourceSitePackages $destinationSitePackages
    if (Test-Path -LiteralPath (Join-Path $sourceRoot "runtime") -PathType Container) {
        Copy-DirectoryContents (Join-Path $sourceRoot "runtime") $destinationRuntime
    } else {
        New-Item -ItemType Directory -Path $destinationRuntime -Force | Out-Null
    }
    Copy-Item -LiteralPath (Join-Path $sourceRoot "babeldoc.exe") `
        -Destination (Join-Path $destinationRoot "babeldoc.exe")
} elseif (Test-Path -LiteralPath $sourceVenvPython -PathType Leaf) {
    Write-Host "Building a relocatable BabelDOC runtime from a virtual environment..."
    $pythonHome = (& $sourceVenvPython -c "import sys; print(sys.base_prefix)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonHome)) {
        throw "Unable to identify the base Python installation for $sourceVenvPython"
    }

    New-Item -ItemType Directory -Path $destinationPython -Force | Out-Null
    foreach ($file in @(
        "python.exe",
        "python3.dll",
        "python312.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "LICENSE.txt"
    )) {
        $from = Join-Path $pythonHome $file
        if (Test-Path -LiteralPath $from -PathType Leaf) {
            $toName = if ($file -eq "LICENSE.txt") { "PYTHON_LICENSE.txt" } else { $file }
            Copy-Item -LiteralPath $from -Destination (Join-Path $destinationPython $toName)
        }
    }
    Copy-DirectoryContents (Join-Path $pythonHome "DLLs") (Join-Path $destinationPython "DLLs")
    Copy-DirectoryContents (Join-Path $pythonHome "Lib") (Join-Path $destinationPython "Lib")
    $copiedGlobalPackages = Join-Path $destinationPython "Lib\site-packages"
    if (Test-Path -LiteralPath $copiedGlobalPackages) {
        Remove-Item -LiteralPath $copiedGlobalPackages -Recurse -Force
    }
    Copy-DirectoryContents (Join-Path $sourceRoot "Lib\site-packages") $destinationSitePackages
    New-Item -ItemType Directory -Path $destinationRuntime -Force | Out-Null

    if ([string]::IsNullOrWhiteSpace($BuildPython)) {
        $BuildPython = Join-Path $projectRoot ".build-deps\app-venv\Scripts\python.exe"
    } else {
        $BuildPython = Resolve-PathFromProject $BuildPython
    }
    if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
        throw "A Python environment containing PyInstaller is required to build babeldoc.exe: $BuildPython"
    }
    & $BuildPython -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "BuildPython does not contain PyInstaller: $BuildPython" }

    $launcherDist = Join-Path $destinationParent "babeldoc-launcher-dist"
    $launcherWork = Join-Path $destinationParent "babeldoc-launcher-work"
    $launcherSpec = Join-Path $destinationParent "babeldoc-launcher-spec"
    New-Item -ItemType Directory -Path $launcherSpec -Force | Out-Null
    & $BuildPython -m PyInstaller --noconfirm --clean --onefile --console `
        --name babeldoc `
        --distpath $launcherDist `
        --workpath $launcherWork `
        --specpath $launcherSpec `
        (Join-Path $PSScriptRoot "babeldoc_portable_launcher.py")
    if ($LASTEXITCODE -ne 0) { throw "Unable to build the portable BabelDOC launcher." }
    Copy-Item -LiteralPath (Join-Path $launcherDist "babeldoc.exe") `
        -Destination (Join-Path $destinationRoot "babeldoc.exe")
} else {
    throw @"
Unsupported BabelDOC source layout: $sourceRoot
Provide either:
  * an existing Full edition/backend directory containing python, site-packages,
    runtime, and babeldoc.exe; or
  * a BabelDOC virtual environment containing Scripts\python.exe.
"@
}

# Copy only the known immutable layout resources. Never copy BabelDOC's
# per-user translation database or document working directories.
$assetTarget = Join-Path $destinationRuntime ".cache\babeldoc"
New-Item -ItemType Directory -Path $assetTarget -Force | Out-Null
$cacheRoot = Resolve-PathFromProject $BabelDocCache
if (Test-Path -LiteralPath $cacheRoot -PathType Container) {
    foreach ($folder in @("cmap", "fonts", "models", "tiktoken")) {
        $from = Join-Path $cacheRoot $folder
        if (Test-Path -LiteralPath $from -PathType Container) {
            $to = Join-Path $assetTarget $folder
            if (Test-Path -LiteralPath $to) {
                # The destination is always inside the newly created package.
                Remove-Item -LiteralPath $to -Recurse -Force
            }
            Copy-Item -LiteralPath $from -Destination $to -Recurse
        }
    }
}

function Remove-VerifiedRuntimeItem {
    param([string]$Path, [switch]$Recurse)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($destinationRoot + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove an item outside the new runtime: $full"
    }
    if ($Recurse) {
        Remove-Item -LiteralPath $full -Recurse -Force
    } else {
        Remove-Item -LiteralPath $full -Force
    }
}

function Remove-RuntimeBuildArtifacts {
    $standardLibrary = Join-Path $destinationPython "Lib"
    foreach ($name in @(
        "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip",
        "lib2to3", "msilib", "curses", "venv"
    )) {
        Remove-VerifiedRuntimeItem (Join-Path $standardLibrary $name) -Recurse
    }

    $dllDirectory = Join-Path $destinationPython "DLLs"
    if (Test-Path -LiteralPath $dllDirectory) {
        Get-ChildItem -LiteralPath $dllDirectory -File | Where-Object {
            $_.Name -like "_test*.pyd" -or
            $_.Name -in @(
                "_ctypes_test.pyd", "_tkinter.pyd", "tcl86t.dll", "tk86t.dll",
                "py.ico", "pyc.ico", "pyd.ico", "python_lib.cat"
            )
        } | ForEach-Object { Remove-VerifiedRuntimeItem $_.FullName }
    }

    if (Test-Path -LiteralPath $destinationSitePackages) {
        # Remove development-only package trees from deepest to shallowest.
        $developmentNames = @(
            "test", "tests", "__tests__", "benchmarks", "benchmark",
            "examples", "example", "docs", "doc", ".pytest_cache"
        )
        Get-ChildItem -LiteralPath $destinationSitePackages -Recurse -Directory |
            Where-Object { $_.Name.ToLowerInvariant() -in $developmentNames } |
            Sort-Object { $_.FullName.Length } -Descending |
            ForEach-Object { Remove-VerifiedRuntimeItem $_.FullName -Recurse }

        Get-ChildItem -LiteralPath $destinationSitePackages -Directory |
            Where-Object {
                $_.Name -eq "pip" -or
                $_.Name -like "pip-*.dist-info" -or
                $_.Name -eq "wheel" -or
                $_.Name -like "wheel-*.dist-info"
            } |
            ForEach-Object { Remove-VerifiedRuntimeItem $_.FullName -Recurse }

        Get-ChildItem -LiteralPath $destinationSitePackages -Recurse -File |
            Where-Object {
                $_.Extension -in @(".pyc", ".pyo") -or
                $_.Name -in @("RECORD", "INSTALLER", "REQUESTED", "direct_url.json")
            } |
            ForEach-Object { Remove-VerifiedRuntimeItem $_.FullName }
    }

    Get-ChildItem -LiteralPath $destinationRoot -Recurse -Directory -Force |
        Where-Object { $_.Name -eq "__pycache__" } |
        Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object { Remove-VerifiedRuntimeItem $_.FullName -Recurse }

    Get-ChildItem -LiteralPath $destinationRuntime -Recurse -File -Force |
        Where-Object {
            $_.Name -like "cache.v1.db*" -or
            $_.Extension -in @(".log", ".tmp")
        } |
        ForEach-Object { Remove-VerifiedRuntimeItem $_.FullName }
}

Remove-RuntimeBuildArtifacts

foreach ($folder in @("cmap", "fonts", "models", "tiktoken")) {
    if (-not (Test-Path -LiteralPath (Join-Path $assetTarget $folder) -PathType Container)) {
        throw "Bundled BabelDOC asset folder is missing: $folder"
    }
}

$engineInfo = @"
BabelDOC Smart PDF Engine
Version: $BabelDocVersion
License: GNU AGPL 3.0
Source: https://github.com/funstory-ai/BabelDOC

This folder is required by the Full and Setup editions.
Do not delete, rename, or move it away from DocumentTranslator.exe.
It contains no DeepSeek API key, user translation cache, or source document.
"@
[IO.File]::WriteAllText(
    (Join-Path $destinationRoot "ENGINE_INFO.txt"),
    $engineInfo,
    [Text.UTF8Encoding]::new($false)
)

$engineExecutable = Join-Path $destinationRoot "babeldoc.exe"
Write-Host "Testing the pruned BabelDOC runtime..."
& $engineExecutable --version | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Pruned BabelDOC runtime failed its version smoke test." }

# The smoke test imports BabelDOC and may recreate bytecode or an empty
# translation database. They are runtime state and must not enter the release.
Remove-RuntimeBuildArtifacts

$sizeBytes = (Get-ChildItem -LiteralPath $destinationRoot -Recurse -File |
    Measure-Object Length -Sum).Sum
Write-Host ("BabelDOC runtime ready: {0} MiB" -f [math]::Round($sizeBytes / 1MB, 1))
