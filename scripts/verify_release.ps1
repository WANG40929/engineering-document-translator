param(
    [Parameter(Mandatory = $true)]
    [string]$PackageRoot,
    [ValidateSet("Lite", "Full")]
    [string]$Edition = "Lite",
    [switch]$SmokeTestEngine
)

$ErrorActionPreference = "Stop"

$root = [IO.Path]::GetFullPath($PackageRoot).TrimEnd("\")
if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw "Package directory does not exist: $root"
}

function Get-RelativeReleasePath {
    param([string]$FullName)
    return $FullName.Substring($root.Length).TrimStart("\")
}

function Test-AsciiText {
    param([string]$Value)
    foreach ($character in $Value.ToCharArray()) {
        if ([int][char]$character -gt 127) { return $false }
    }
    return $true
}

$requiredTopLevel = @(
    "DocumentTranslator.exe",
    "ApplicationFiles",
    "ReadMe.html",
    "ReadMe.txt",
    "Legal"
)
if ($Edition -eq "Full") { $requiredTopLevel += "TranslationEngine" }

foreach ($name in $requiredTopLevel) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $name))) {
        throw "Required release item is missing: $name"
    }
}

$allowedTopLevel = @($requiredTopLevel)
$unexpected = Get-ChildItem -LiteralPath $root -Force |
    Where-Object { $_.Name -notin $allowedTopLevel }
if ($unexpected) {
    throw "Unexpected top-level release item(s): $($unexpected.Name -join ', ')"
}

if ($Edition -eq "Lite" -and (Test-Path -LiteralPath (Join-Path $root "TranslationEngine"))) {
    throw "Lite package unexpectedly contains TranslationEngine."
}

$allItems = Get-ChildItem -LiteralPath $root -Force -Recurse
foreach ($item in $allItems) {
    $relative = Get-RelativeReleasePath $item.FullName
    if (-not (Test-AsciiText $relative)) {
        throw "Non-ASCII release path found: $relative"
    }
}

$blockedDirectoryNames = @(
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".github",
    "tests",
    "test",
    "benchmarks",
    "examples"
)
$blockedDirectories = $allItems |
    Where-Object { $_.PSIsContainer -and $_.Name.ToLowerInvariant() -in $blockedDirectoryNames }
if ($blockedDirectories) {
    $paths = $blockedDirectories | ForEach-Object { Get-RelativeReleasePath $_.FullName }
    throw "Development/cache directories found in release: $($paths -join ', ')"
}

$blockedFilePatterns = @(
    "*.pyc",
    "*.pyo",
    "*.key",
    ".env",
    ".env.*",
    "config.json",
    "translations.sqlite3*",
    "translation_report_*.json",
    "cache.v1.db"
)
foreach ($pattern in $blockedFilePatterns) {
    $matches = Get-ChildItem -LiteralPath $root -Force -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue
    if ($matches) {
        $paths = $matches | ForEach-Object { Get-RelativeReleasePath $_.FullName }
        throw "Private/cache file(s) found in release: $($paths -join ', ')"
    }
}

# Scan only the human-readable top-level/legal files. Engine source code
# legitimately contains fields named api_key, so a broad scan would be noisy.
$textFiles = @(
    (Join-Path $root "ReadMe.html"),
    (Join-Path $root "ReadMe.txt")
)
$textFiles += Get-ChildItem -LiteralPath (Join-Path $root "Legal") -Recurse -File |
    Select-Object -ExpandProperty FullName
if ($Edition -eq "Full") {
    $engineInfo = Join-Path $root "TranslationEngine\ENGINE_INFO.txt"
    if (Test-Path -LiteralPath $engineInfo) { $textFiles += $engineInfo }
}
foreach ($file in $textFiles) {
    if ((Get-Item -LiteralPath $file).Length -gt 5MB) { continue }
    $text = Get-Content -LiteralPath $file -Raw -ErrorAction SilentlyContinue
    if ($text -match 'sk-[A-Za-z0-9_-]{16,}') {
        throw "Possible API credential found in release text: $(Get-RelativeReleasePath $file)"
    }
}

if ($Edition -eq "Full") {
    $engine = Join-Path $root "TranslationEngine\babeldoc.exe"
    if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) {
        throw "Full package is missing TranslationEngine\babeldoc.exe."
    }
    if ($SmokeTestEngine) {
        & $engine --version | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Bundled BabelDOC smoke test failed." }
        $database = Join-Path $root "TranslationEngine\runtime\.cache\babeldoc\cache.v1.db"
        if (Test-Path -LiteralPath $database) {
            Remove-Item -LiteralPath $database -Force
        }
    }
}

$sizeBytes = (Get-ChildItem -LiteralPath $root -Recurse -File | Measure-Object Length -Sum).Sum
$fileCount = (Get-ChildItem -LiteralPath $root -Recurse -File | Measure-Object).Count
Write-Host ("Verified {0} release: {1} files, {2} MiB" -f `
    $Edition, $fileCount, [math]::Round($sizeBytes / 1MB, 1))
