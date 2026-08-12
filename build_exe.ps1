param(
    [string]$Python = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectDir

if (-not $Python) {
    if ($env:DONUT_MONITOR_PYTHON) {
        $Python = $env:DONUT_MONITOR_PYTHON
    } elseif (Test-Path -LiteralPath ".venv\Scripts\python.exe") {
        $Python = (Resolve-Path -LiteralPath ".venv\Scripts\python.exe").Path
    } else {
        $Python = "python"
    }
}

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $env:LOCALAPPDATA "DonutHASELMonitorBuild"
}
$distDir = Join-Path $OutputRoot "dist"
$workDir = Join-Path $OutputRoot "work"
$specDir = Join-Path $OutputRoot "spec"
New-Item -ItemType Directory -Path $distDir, $workDir, $specDir -Force | Out-Null

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name "Donut-HASEL-Drive-Monitor-V3" `
    --paths "src" `
    --specpath $specDir `
    --distpath $distDir `
    --workpath $workDir `
    "run_monitor.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$builtExe = Join-Path $distDir "Donut-HASEL-Drive-Monitor-V3.exe"
$deliveryDir = Join-Path $projectDir "dist"
New-Item -ItemType Directory -Path $deliveryDir -Force | Out-Null
$exe = Join-Path $deliveryDir "Donut-HASEL-Drive-Monitor-V3.exe"
Copy-Item -LiteralPath $builtExe -Destination $exe -Force
Write-Host "Build complete: $exe"
