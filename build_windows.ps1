[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $repositoryRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found on PATH. Activate the VideoText build environment first."
}

& python --version
& python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: python -m pip install -r requirements-packaging.txt"
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

& python -m PyInstaller --noconfirm VideoText.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed. Review build/VideoText/warn-VideoText.txt."
}

$executablePath = Join-Path $repositoryRoot "dist/VideoText/VideoText.exe"
if (-not (Test-Path -LiteralPath $executablePath)) {
    throw "Build completed without the expected executable: $executablePath"
}

Write-Host "Build complete."
Write-Host "Executable: $executablePath"
