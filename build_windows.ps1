[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$BuildName = "VideoText",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $repositoryRoot
$venvPython = if ($PythonExecutable) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PythonExecutable)
} else {
    Join-Path $repositoryRoot ".venv\Scripts\python.exe"
}
$specificationPath = Join-Path $repositoryRoot "VideoText.spec"

$reservedBuildNames = @("CON", "PRN", "AUX", "NUL") +
    (1..9 | ForEach-Object { "COM$_" }) +
    (1..9 | ForEach-Object { "LPT$_" })
$buildNameBase = ($BuildName -split '\.', 2)[0].ToUpperInvariant()
if (
    $BuildName -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$' -or
    $BuildName.EndsWith('.') -or
    $buildNameBase -in $reservedBuildNames
) {
    throw "BuildName must start with a letter or number and contain only letters, numbers, periods, underscores, or hyphens (80 characters maximum)."
}

$buildDirectory = Join-Path $repositoryRoot ("build\" + $BuildName)
$distributionDirectory = Join-Path $repositoryRoot ("dist\" + $BuildName)
$topLevelExecutable = Join-Path $repositoryRoot ("dist\" + $BuildName + ".exe")
$collectedExecutable = Join-Path $distributionDirectory ($BuildName + ".exe")

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Project virtual environment was not found: $venvPython. Create .venv and install requirements before building."
}
if (-not (Test-Path -LiteralPath $specificationPath)) {
    throw "PyInstaller specification was not found: $specificationPath"
}

Write-Host "Using project Python: $venvPython"
& $venvPython --version

& $venvPython (Join-Path $repositoryRoot "packaging\preflight.py")
if ($LASTEXITCODE -ne 0) {
    throw "Packaging preflight failed. Install the declared requirements into .venv."
}

& $venvPython -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed in .venv. Run: .venv\Scripts\python.exe -m pip install -r requirements-packaging.txt"
}

$paddleCache = if ($env:PADDLE_PDX_CACHE_HOME) {
    $env:PADDLE_PDX_CACHE_HOME
} else {
    Join-Path $env:USERPROFILE ".paddlex"
}
Write-Host "PaddleX cache: $paddleCache ($(if (Test-Path -LiteralPath $paddleCache) { 'found' } else { 'not found' }))"

$writeProbe = Join-Path $repositoryRoot ".videotext-packaging-write-probe"
try {
    [System.IO.File]::WriteAllText($writeProbe, "ok")
} finally {
    if (Test-Path -LiteralPath $writeProbe) {
        Remove-Item -LiteralPath $writeProbe -Force
    }
}

if ($Clean) {
    foreach ($target in @(
        $buildDirectory,
        $distributionDirectory,
        $topLevelExecutable
    )) {
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }
}

# PaddleX performs a hoster-connectivity check while PyInstaller discovers its
# dynamically loaded modules.  Packaging needs module analysis, not OCR model
# initialization, so disable only that build-time check.  Runtime OCR remains
# unchanged and still reports genuine model availability errors.
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "True"
$previousBuildName = $env:VIDEOTEXT_BUILD_NAME
try {
    $env:VIDEOTEXT_BUILD_NAME = $BuildName
    & $venvPython -m PyInstaller --noconfirm `
        --workpath $buildDirectory `
        --distpath (Join-Path $repositoryRoot "dist") `
        $specificationPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed. Review $buildDirectory\warn-$BuildName.txt."
    }
} finally {
    $env:VIDEOTEXT_BUILD_NAME = $previousBuildName
}

if (-not (Test-Path -LiteralPath $collectedExecutable)) {
    throw "Build completed without the expected executable: $collectedExecutable"
}

Write-Host "Build complete."
Write-Host "Build identity: $BuildName"
Write-Host "Executable: $collectedExecutable"
