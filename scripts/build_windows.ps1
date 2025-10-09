Param(
    [string]$ProjectRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path),
    [Parameter(ValueFromRemainingArguments = $true)]
    [object[]]$RemainingArgs
)

$ProjectRoot = (Resolve-Path "$ProjectRoot\..\").Path
$Wrapper = Join-Path (Join-Path $ProjectRoot "packaging") "windows\build_app.ps1"

if (Test-Path $Wrapper) {
    if ($RemainingArgs) {
        & $Wrapper @RemainingArgs
    } else {
        & $Wrapper
    }
    exit $LASTEXITCODE
}

Write-Warning "packaging/windows/build_app.ps1 not found; falling back to direct PyInstaller invocation."
Set-Location $ProjectRoot
uv run pyinstaller --clean --noconfirm scripts/build_dashboard.spec
