Param(
    [string]$ProjectRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path)
)

$ProjectRoot = (Resolve-Path "$ProjectRoot\..\").Path
Set-Location $ProjectRoot

uv run pyinstaller --clean --noconfirm scripts/build_dashboard.spec
