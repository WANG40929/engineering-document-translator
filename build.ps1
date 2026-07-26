param(
    [string]$Python = "python",
    [switch]$RefreshDependencies,
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$buildEnvironment = Join-Path $PSScriptRoot ".build-deps\app-venv"
$buildPython = Join-Path $buildEnvironment "Scripts\python.exe"

if ($RefreshDependencies -and (Test-Path -LiteralPath $buildEnvironment)) {
    $resolvedBuildEnvironment = [IO.Path]::GetFullPath($buildEnvironment)
    $allowedRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".build-deps"))
    if (-not $resolvedBuildEnvironment.StartsWith($allowedRoot + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove an unexpected build environment: $resolvedBuildEnvironment"
    }
    Remove-Item -LiteralPath $resolvedBuildEnvironment -Recurse -Force
}

if (-not (Test-Path -LiteralPath $buildPython)) {
    Write-Host "Creating isolated application build environment..."
    & $Python -m venv $buildEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the application build environment." }
}

$requirementsFile = Join-Path $PSScriptRoot "requirements.txt"
$dependencyMarker = Join-Path $buildEnvironment "udt-build-dependencies.txt"
$requirementsHash = (Get-FileHash -LiteralPath $requirementsFile -Algorithm SHA256).Hash
$dependencySignature = "$requirementsHash|pyinstaller>=6.10,<7"
$installedSignature = if (Test-Path -LiteralPath $dependencyMarker) {
    (Get-Content -LiteralPath $dependencyMarker -Raw).Trim()
} else {
    ""
}
if ($installedSignature -ne $dependencySignature) {
    Write-Host "Installing reproducible application build dependencies..."
    & $buildPython -m pip install --disable-pip-version-check --upgrade `
        -r $requirementsFile `
        "pyinstaller>=6.10,<7"
    if ($LASTEXITCODE -ne 0) { throw "Unable to install application build dependencies." }
    [IO.File]::WriteAllText(
        $dependencyMarker,
        $dependencySignature,
        [Text.UTF8Encoding]::new($false)
    )
} else {
    Write-Host "Reusing verified application build dependencies."
}

$pyInstallerArguments = @("--noconfirm")
if (-not $NoClean) { $pyInstallerArguments += "--clean" }
$pyInstallerArguments += (Join-Path $PSScriptRoot "EngineeringDocumentTranslator.spec")

Write-Host "Building the fast-start onedir application..."
& $buildPython -m PyInstaller @pyInstallerArguments
if ($LASTEXITCODE -ne 0) { throw "PyInstaller application build failed." }

$application = Join-Path $PSScriptRoot "dist\DocumentTranslator\DocumentTranslator.exe"
if (-not (Test-Path -LiteralPath $application)) {
    throw "The expected application was not produced: $application"
}

$sizeMiB = [math]::Round(
    ((Get-ChildItem -LiteralPath (Split-Path -Parent $application) -Recurse -File |
        Measure-Object Length -Sum).Sum / 1MB),
    1
)
Write-Host "Application build ready: $application ($sizeMiB MiB, onedir)"
