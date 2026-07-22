param(
    [string]$Version = "1.2.0",
    [string]$BabelDocEnvironment = ".babeldoc-env",
    [string]$BabelDocCache = "$env:USERPROFILE\.cache\babeldoc"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $projectRoot "release"
$stagingRoot = Join-Path $outputRoot "staging"
$liteName = "DocumentTranslator-v$Version-Windows-Lite-no-BabelDOC"
$fullName = "DocumentTranslator-v$Version-Windows-Full-with-BabelDOC"
$liteRoot = Join-Path $stagingRoot $liteName
$fullRoot = Join-Path $stagingRoot $fullName
$appExe = Join-Path $projectRoot "dist\EngineeringDocumentTranslator.exe"
$venvRoot = Join-Path $projectRoot $BabelDocEnvironment
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$pythonHome = (& $venvPython -c "import sys; print(sys.base_prefix)").Trim()

if (-not (Test-Path $appExe)) { throw "Application EXE not found: $appExe" }
if (-not (Test-Path $venvPython)) { throw "BabelDOC environment not found: $venvRoot" }
if (-not (Test-Path $BabelDocCache)) { throw "BabelDOC asset cache not found: $BabelDocCache" }

Remove-Item $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item $liteRoot -ItemType Directory -Force | Out-Null
New-Item $fullRoot -ItemType Directory -Force | Out-Null

foreach ($root in @($liteRoot, $fullRoot)) {
    Copy-Item $appExe (Join-Path $root "DocumentTranslator.exe")
    Copy-Item (Join-Path $projectRoot "LICENSE.txt") $root
    Copy-Item (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") $root
    Copy-Item (Join-Path $projectRoot "docs\DOWNLOADS.md") (Join-Path $root "使用说明-README.md")
}

$backendRoot = Join-Path $fullRoot "backend"
$portablePython = Join-Path $backendRoot "python"
$sitePackages = Join-Path $backendRoot "site-packages"
$assetTarget = Join-Path $backendRoot "runtime\.cache\babeldoc"
New-Item $portablePython -ItemType Directory -Force | Out-Null
New-Item $sitePackages -ItemType Directory -Force | Out-Null
New-Item $assetTarget -ItemType Directory -Force | Out-Null

foreach ($file in @("python.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll")) {
    $source = Join-Path $pythonHome $file
    if (Test-Path $source) { Copy-Item $source $portablePython }
}
Copy-Item (Join-Path $pythonHome "DLLs") $portablePython -Recurse
Copy-Item (Join-Path $pythonHome "Lib") $portablePython -Recurse
Remove-Item (Join-Path $portablePython "Lib\site-packages") -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $pythonHome "LICENSE.txt") (Join-Path $portablePython "PYTHON_LICENSE.txt")
Copy-Item (Join-Path $venvRoot "Lib\site-packages\*") $sitePackages -Recurse

# Copy models, fonts, CMaps, and tokenizer data, but never ship the user's
# BabelDOC translation database or per-document working directories.
foreach ($folder in @("cmap", "fonts", "models", "tiktoken")) {
    $source = Join-Path $BabelDocCache $folder
    if (Test-Path $source) { Copy-Item $source $assetTarget -Recurse }
}
Get-ChildItem $BabelDocCache -File | Where-Object { $_.Name -ne "cache.v1.db" } | Copy-Item -Destination $assetTarget

$savedPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $projectRoot ".build-deps"
& (Join-Path $pythonHome "python.exe") -m PyInstaller --noconfirm --clean --onefile --console `
    --name babeldoc `
    --distpath $backendRoot `
    --workpath (Join-Path $stagingRoot "launcher-build") `
    --specpath $stagingRoot `
    (Join-Path $PSScriptRoot "babeldoc_portable_launcher.py")
$env:PYTHONPATH = $savedPythonPath

& (Join-Path $backendRoot "babeldoc.exe") --version
# Importing BabelDOC initializes a fresh empty translation database. It is
# runtime state, not a release asset, so never place it in the archive.
Remove-Item (Join-Path $assetTarget "cache.v1.db") -Force -ErrorAction SilentlyContinue

New-Item $outputRoot -ItemType Directory -Force | Out-Null
$liteZip = Join-Path $outputRoot "$liteName.zip"
$fullZip = Join-Path $outputRoot "$fullName.zip"
Remove-Item $liteZip, $fullZip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$liteRoot\*" -DestinationPath $liteZip -CompressionLevel Optimal
Compress-Archive -Path "$fullRoot\*" -DestinationPath $fullZip -CompressionLevel Optimal

Get-FileHash $liteZip, $fullZip -Algorithm SHA256 | Format-Table Path, Hash -AutoSize
