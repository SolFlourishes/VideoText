[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $repositoryRoot
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$specificationPath = Join-Path $repositoryRoot "VideoText.spec"

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
        (Join-Path $repositoryRoot "build/VideoText"),
        (Join-Path $repositoryRoot "dist/VideoText")
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
& $venvPython -m PyInstaller --noconfirm $specificationPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed. Review build/VideoText/warn-VideoText.txt."
}

$executablePath = Join-Path $repositoryRoot "dist/VideoText/VideoText.exe"
if (-not (Test-Path -LiteralPath $executablePath)) {
    throw "Build completed without the expected executable: $executablePath"
}

Write-Host "Build complete."
Write-Host "Executable: $executablePath"
