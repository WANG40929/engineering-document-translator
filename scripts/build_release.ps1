param(
    [string]$Version = "1.4.1",
    [string]$BabelDocSource = "",
    [string]$BabelDocCache = "$env:USERPROFILE\.cache\babeldoc",
    [string]$Python = "python",
    [string]$InnoSetupPath = "",
    [switch]$SkipAppBuild,
    [switch]$SkipInstaller,
    [switch]$LiteOnly,
    [switch]$KeepStaging
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $projectRoot "release"
$stagingRoot = Join-Path $outputRoot "staging"
$liteName = "DocumentTranslator-v$Version-Windows-Portable-Lite"
$fullName = "DocumentTranslator-v$Version-Windows-Portable-Full"
$setupName = "DocumentTranslator-v$Version-Windows-Setup-Full"
$liteRoot = Join-Path $stagingRoot $liteName
$fullRoot = Join-Path $stagingRoot $fullName
$applicationRoot = Join-Path $projectRoot "dist\DocumentTranslator"
$applicationExe = Join-Path $applicationRoot "DocumentTranslator.exe"

if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$') {
    throw "Version must be an ASCII semantic version, for example 1.4.0."
}

function Assert-InstallerUpgradeContract {
    $installerDefinition = Get-Content -LiteralPath `
        (Join-Path $projectRoot "installer\DocumentTranslator.iss") -Raw
    $requiredSettings = @(
        'AppId={{57E46738-9460-4DE4-B3E8-65E00A68BAED}',
        'DefaultDirName={localappdata}\Programs\DocumentTranslator',
        'UsePreviousAppDir=yes',
        'CloseApplications=yes',
        'CloseApplicationsFilter={#MyAppExeName}',
        'Type: filesandordirs; Name: "{app}\ApplicationFiles"',
        'Type: filesandordirs; Name: "{app}\TranslationEngine"'
    )
    foreach ($setting in $requiredSettings) {
        if (-not $installerDefinition.Contains($setting)) {
            throw "Installer upgrade contract is missing: $setting"
        }
    }
    Write-Host "Verified installer upgrade contract (stable AppId and in-place replacement)."
}

function Remove-SafeReleaseItem {
    param([string]$Path, [switch]$Recurse)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $full = [IO.Path]::GetFullPath($Path)
    $allowed = [IO.Path]::GetFullPath($outputRoot).TrimEnd("\")
    if (-not $full.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove an item outside the release directory: $full"
    }
    if ($Recurse) {
        Remove-Item -LiteralPath $full -Recurse -Force
    } else {
        Remove-Item -LiteralPath $full -Force
    }
}

function Copy-DirectoryContents {
    param([string]$From, [string]$To)
    New-Item -ItemType Directory -Path $To -Force | Out-Null
    Get-ChildItem -LiteralPath $From -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $To -Recurse -Force
    }
}

function Write-EditionGuide {
    param([string]$Destination, [string]$Edition)
    $html = Get-Content -LiteralPath (Join-Path $projectRoot "docs\user-guide.html") -Raw -Encoding UTF8
    $text = Get-Content -LiteralPath (Join-Path $projectRoot "docs\user-guide.txt") -Raw -Encoding UTF8
    $html = $html.Replace("{{VERSION}}", $Version).Replace("{{EDITION}}", $Edition)
    $text = $text.Replace("{{VERSION}}", $Version).Replace("{{EDITION}}", $Edition)
    $utf8WithBom = New-Object Text.UTF8Encoding($true)
    [IO.File]::WriteAllText((Join-Path $Destination "ReadMe.html"), $html, $utf8WithBom)
    [IO.File]::WriteAllText((Join-Path $Destination "ReadMe.txt"), $text, $utf8WithBom)
}

function Copy-PackageLicenses {
    param(
        [string]$SitePackages,
        [string]$Destination
    )
    if (-not (Test-Path -LiteralPath $SitePackages -PathType Container)) { return }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Get-ChildItem -LiteralPath $SitePackages -Directory -Filter "*.dist-info" | ForEach-Object {
        $packageName = ($_.Name -replace '\.dist-info$', '') -replace '[^0-9A-Za-z._-]', '_'
        $licenses = Get-ChildItem -LiteralPath $_.FullName -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^(LICENSE|LICENCE|COPYING|NOTICE)(\..*)?$' }
        $index = 0
        foreach ($license in $licenses) {
            $index += 1
            $extension = [IO.Path]::GetExtension($license.Name)
            if ([string]::IsNullOrWhiteSpace($extension)) { $extension = ".txt" }
            $destinationName = "{0}--LICENSE-{1}{2}" -f $packageName, $index, $extension
            Copy-Item -LiteralPath $license.FullName -Destination (Join-Path $Destination $destinationName)
        }
    }
}

function Add-LegalFiles {
    param(
        [string]$PackageRoot,
        [string]$EngineRoot = ""
    )
    $legalRoot = Join-Path $PackageRoot "Legal"
    $applicationLicenses = Join-Path $legalRoot "ThirdPartyLicenses\Application"
    New-Item -ItemType Directory -Path $legalRoot -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE.txt") `
        -Destination (Join-Path $legalRoot "LICENSE.txt")
    Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") `
        -Destination (Join-Path $legalRoot "THIRD_PARTY_NOTICES.txt")
    foreach ($licenseName in @(
        "GPL-3.0.txt",
        "LGPL-3.0.txt",
        "InnoSetup-License.txt"
    )) {
        Copy-Item -LiteralPath (Join-Path $projectRoot "installer\licenses\$licenseName") `
            -Destination (Join-Path $legalRoot $licenseName)
    }

    $sourceNotice = @"
Document Translator v$Version
License: AGPL-3.0-or-later
Source code and updates:
https://github.com/WANG40929/engineering-document-translator

The Full and Setup editions include BabelDOC $script:BabelDocPinnedVersion.
BabelDOC source:
https://github.com/funstory-ai/BabelDOC
"@
    [IO.File]::WriteAllText(
        (Join-Path $legalRoot "SOURCE_CODE.txt"),
        $sourceNotice,
        [Text.UTF8Encoding]::new($false)
    )

    $applicationSitePackages = Join-Path $projectRoot ".build-deps\app-venv\Lib\site-packages"
    Copy-PackageLicenses $applicationSitePackages $applicationLicenses

    if (-not [string]::IsNullOrWhiteSpace($EngineRoot)) {
        $engineLicenses = Join-Path $legalRoot "ThirdPartyLicenses\TranslationEngine"
        Copy-PackageLicenses (Join-Path $EngineRoot "site-packages") $engineLicenses
        $pythonLicense = Join-Path $EngineRoot "python\PYTHON_LICENSE.txt"
        if (Test-Path -LiteralPath $pythonLicense) {
            Copy-Item -LiteralPath $pythonLicense `
                -Destination (Join-Path $engineLicenses "CPython--LICENSE.txt")
        }
    }

    # Include the complete AGPL text, not only a web link. Prefer the bundled
    # BabelDOC copy; the PyMuPDF distribution is the Lite-build fallback.
    $agplCandidates = @()
    if (-not [string]::IsNullOrWhiteSpace($EngineRoot)) {
        $agplCandidates += Get-ChildItem -LiteralPath (Join-Path $EngineRoot "site-packages") `
            -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -match 'babeldoc-.*\.dist-info' -and
                $_.Name -match '^(LICENSE|COPYING)'
            } |
            Select-Object -ExpandProperty FullName
    }
    if (Test-Path -LiteralPath $applicationSitePackages) {
        $agplCandidates += Get-ChildItem -LiteralPath $applicationSitePackages `
            -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -match 'pymupdf-.*\.dist-info' -and
                $_.Name -match '^(LICENSE|COPYING)'
            } |
            Select-Object -ExpandProperty FullName
    }
    $agplSource = $agplCandidates | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($agplSource)) {
        throw "Unable to locate a complete AGPL license text in the build environments."
    }
    Copy-Item -LiteralPath $agplSource -Destination (Join-Path $legalRoot "AGPL-3.0.txt")
}

function Resolve-BabelDocSource {
    if (-not [string]::IsNullOrWhiteSpace($BabelDocSource)) {
        return [IO.Path]::GetFullPath($BabelDocSource)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:UDT_BABELDOC_SOURCE)) {
        return [IO.Path]::GetFullPath($env:UDT_BABELDOC_SOURCE)
    }
    $localEnvironment = Join-Path $projectRoot ".babeldoc-env"
    if (Test-Path -LiteralPath (Join-Path $localEnvironment "Scripts\python.exe")) {
        return $localEnvironment
    }

    # Migration convenience: accept one existing Full-edition folder on the
    # desktop as a read-only source. Never write to or remove it.
    $desktop = [Environment]::GetFolderPath("Desktop")
    if (Test-Path -LiteralPath $desktop -PathType Container) {
        $candidates = @(
            Get-ChildItem -LiteralPath $desktop -Directory -ErrorAction SilentlyContinue |
                Where-Object {
                    Test-Path -LiteralPath (Join-Path $_.FullName "backend\babeldoc.exe")
                } |
                Select-Object -ExpandProperty FullName
        )
        if ($candidates.Count -eq 1) { return $candidates[0] }
    }
    return ""
}

$script:BabelDocPinnedVersion = "0.6.4"
Assert-InstallerUpgradeContract
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
Remove-SafeReleaseItem $stagingRoot -Recurse
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

if (-not $SkipAppBuild) {
    & (Join-Path $projectRoot "build.ps1") -Python $Python
    if ($LASTEXITCODE -ne 0) { throw "Application build failed." }
}
if (-not (Test-Path -LiteralPath $applicationExe -PathType Leaf)) {
    throw "Application onedir build is missing: $applicationExe"
}

Write-Host "Staging Portable Lite..."
New-Item -ItemType Directory -Path $liteRoot -Force | Out-Null
Copy-DirectoryContents $applicationRoot $liteRoot
Write-EditionGuide $liteRoot "Portable Lite"
Add-LegalFiles $liteRoot
& (Join-Path $PSScriptRoot "verify_release.ps1") -PackageRoot $liteRoot -Edition Lite

if (-not $LiteOnly) {
    $resolvedBabelSource = Resolve-BabelDocSource
    if ([string]::IsNullOrWhiteSpace($resolvedBabelSource)) {
        throw @"
No BabelDOC runtime source was found.
Pass -BabelDocSource with either an existing Full-edition folder/backend
directory or a BabelDOC virtual environment. The source is read only.
"@
    }

    Write-Host "Staging Portable Full from read-only engine source: $resolvedBabelSource"
    New-Item -ItemType Directory -Path $fullRoot -Force | Out-Null
    Copy-DirectoryContents $applicationRoot $fullRoot
    Write-EditionGuide $fullRoot "Portable Full"
    $engineDestination = Join-Path $fullRoot "TranslationEngine"
    & (Join-Path $PSScriptRoot "build_babeldoc_runtime.ps1") `
        -Source $resolvedBabelSource `
        -Destination $engineDestination `
        -BabelDocCache $BabelDocCache `
        -BuildPython (Join-Path $projectRoot ".build-deps\app-venv\Scripts\python.exe") `
        -BabelDocVersion $script:BabelDocPinnedVersion
    if ($LASTEXITCODE -ne 0) { throw "BabelDOC runtime build failed." }
    Add-LegalFiles $fullRoot $engineDestination
    & (Join-Path $PSScriptRoot "verify_release.ps1") `
        -PackageRoot $fullRoot -Edition Full
}

$zipPython = Join-Path $projectRoot ".build-deps\app-venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $zipPython -PathType Leaf)) { $zipPython = $Python }

$liteZip = Join-Path $outputRoot "$liteName.zip"
Remove-SafeReleaseItem $liteZip
Write-Host "Compressing Portable Lite..."
& $zipPython (Join-Path $PSScriptRoot "create_release_zip.py") $liteRoot $liteZip
if ($LASTEXITCODE -ne 0) { throw "Unable to create Portable Lite ZIP." }

$releaseFiles = @($liteZip)
if (-not $LiteOnly) {
    $fullZip = Join-Path $outputRoot "$fullName.zip"
    Remove-SafeReleaseItem $fullZip
    Write-Host "Compressing Portable Full..."
    & $zipPython (Join-Path $PSScriptRoot "create_release_zip.py") $fullRoot $fullZip
    if ($LASTEXITCODE -ne 0) { throw "Unable to create Portable Full ZIP." }
    $releaseFiles += $fullZip
}

if (-not $LiteOnly -and -not $SkipInstaller) {
    if ([string]::IsNullOrWhiteSpace($InnoSetupPath)) {
        $innoCandidates = @()
        foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, $env:LOCALAPPDATA)) {
            if ([string]::IsNullOrWhiteSpace($base)) { continue }
            $prefix = if ($base -eq $env:LOCALAPPDATA) { "Programs" } else { "" }
            foreach ($major in @("7", "6")) {
                $relative = if ($prefix) {
                    "$prefix\Inno Setup $major\ISCC.exe"
                } else {
                    "Inno Setup $major\ISCC.exe"
                }
                $innoCandidates += Join-Path $base $relative
            }
        }
        $InnoSetupPath = $innoCandidates |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) } |
            Select-Object -First 1
    }

    if ([string]::IsNullOrWhiteSpace($InnoSetupPath) -or
        -not (Test-Path -LiteralPath $InnoSetupPath -PathType Leaf)) {
        Write-Warning @"
Inno Setup 6 was not found, so the Setup EXE was not built.
Install it once with:
  winget install --id JRSoftware.InnoSetup --exact
Then rerun this script with -SkipAppBuild.
"@
    } else {
        $setupExe = Join-Path $outputRoot "$setupName.exe"
        Remove-SafeReleaseItem $setupExe
        Write-Host "Building Windows Setup Full with Inno Setup..."

        # Inno Setup 6 still encounters MAX_PATH while reading deeply nested
        # Python packages. Map the verified staging folder to a temporary drive
        # for compilation, then always remove the mapping.
        $setupSource = $fullRoot
        $mappedDrive = ""
        $longestSourcePath = Get-ChildItem -LiteralPath $fullRoot -Recurse -File |
            ForEach-Object { $_.FullName.Length } |
            Measure-Object -Maximum |
            Select-Object -ExpandProperty Maximum
        if ($longestSourcePath -ge 240) {
            foreach ($letter in @("R", "S", "T", "U", "V", "W", "X", "Y", "Z")) {
                if (-not (Test-Path "$letter`:\")) {
                    $mappedDrive = "$letter`:"
                    break
                }
            }
            if ([string]::IsNullOrWhiteSpace($mappedDrive)) {
                throw "No free drive letter is available for the Inno Setup short-path mapping."
            }
            & (Join-Path $env:SystemRoot "System32\subst.exe") $mappedDrive $fullRoot
            if ($LASTEXITCODE -ne 0) { throw "Unable to create the temporary installer source mapping." }
            $setupSource = "$mappedDrive\"
        }

        $compilerExitCode = 1
        try {
            & $InnoSetupPath `
                "/Qp" `
                "/DMyAppVersion=$Version" `
                "/DSourceDir=$setupSource" `
                "/DReleaseDir=$outputRoot" `
                "/DOutputBaseName=$setupName" `
                (Join-Path $projectRoot "installer\DocumentTranslator.iss")
            $compilerExitCode = $LASTEXITCODE
        } finally {
            if (-not [string]::IsNullOrWhiteSpace($mappedDrive)) {
                & (Join-Path $env:SystemRoot "System32\subst.exe") $mappedDrive /D
            }
        }
        if ($compilerExitCode -ne 0) { throw "Inno Setup compilation failed." }
        if (-not (Test-Path -LiteralPath $setupExe -PathType Leaf)) {
            throw "Expected setup executable was not produced: $setupExe"
        }
        $releaseFiles += $setupExe
    }
}

$checksumFile = Join-Path $outputRoot "SHA256SUMS.txt"
Remove-SafeReleaseItem $checksumFile
$checksumLines = $releaseFiles | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $([IO.Path]::GetFileName($_))"
}
[IO.File]::WriteAllLines($checksumFile, $checksumLines, [Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "Release artifacts:"
foreach ($file in $releaseFiles) {
    $item = Get-Item -LiteralPath $file
    Write-Host ("  {0} ({1} MiB)" -f $item.FullName, [math]::Round($item.Length / 1MB, 1))
}
Write-Host "  $checksumFile"

if (-not $KeepStaging) {
    Remove-SafeReleaseItem $stagingRoot -Recurse
    Write-Host "Removed release staging files. Build environments and dist remain reusable."
} else {
    Write-Host "Staging kept for inspection: $stagingRoot"
}
