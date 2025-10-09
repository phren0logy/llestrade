<#
Convenience wrapper to build the unsigned Windows distribution via PyInstaller.
Produces dist/win32/llestrade/llestrade.exe using the shared spec file.
#>

[CmdletBinding()]
param(
    [switch]$FreshDist,
    [string]$PyInstallerConfigDir,
    [string]$UvCacheDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $ScriptDir ".." "..")).Path

function Write-Log {
    param([string]$Message)
    Write-Host "[windows-package] $Message"
}

$SpecFile = Join-Path (Join-Path $RootDir "scripts") "build_dashboard.spec"
if (-not (Test-Path $SpecFile)) {
    throw "Missing PyInstaller spec at $SpecFile"
}

if (-not $PyInstallerConfigDir) {
    $PyInstallerConfigDir = Join-Path $RootDir ".pyinstaller"
}
if (-not $UvCacheDir) {
    $UvCacheDir = Join-Path $RootDir ".uv_cache"
}

$DistRoot = Join-Path (Join-Path $RootDir "dist") "win32"
if ($FreshDist.IsPresent -and (Test-Path $DistRoot)) {
    Write-Log "Removing $DistRoot for a clean build"
    Remove-Item -Recurse -Force $DistRoot
}

$env:PYINSTALLER_CONFIG_DIR = $PyInstallerConfigDir
$env:UV_CACHE_DIR = $UvCacheDir

Write-Log "Root: $RootDir"
Write-Log "Spec: $SpecFile"
Write-Log "PyInstaller config dir: $env:PYINSTALLER_CONFIG_DIR"
Write-Log "uv cache dir: $env:UV_CACHE_DIR"

Push-Location $RootDir
try {
    Write-Log "Building Windows bundle via PyInstaller"
    uv run pyinstaller --clean --noconfirm $SpecFile
} finally {
    Pop-Location
}

$ExecutablePath = Join-Path (Join-Path $DistRoot "llestrade") "llestrade.exe"
if (Test-Path $ExecutablePath) {
    Write-Log "Bundle ready at $ExecutablePath"
} else {
    throw "Expected executable not found at $ExecutablePath"
}
