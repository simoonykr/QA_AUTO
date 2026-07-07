$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment..."
    python -m venv (Join-Path $ProjectDir ".venv")
}

Write-Host "Installing dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $ProjectDir "requirements.txt")
& $Python -m pip install pyinstaller

Write-Host "Building executable..."
Push-Location $ProjectDir
try {
    & $Python -m PyInstaller `
        --onefile `
        --name aos_game_auto `
        --clean `
        --paths $ProjectDir `
        main.py

    & $Python -m PyInstaller `
        --onefile `
        --name template_capture_gui `
        --clean `
        --paths $ProjectDir `
        --windowed `
        template_capture_gui.py

    $PackageDir = Join-Path $ProjectDir "dist\aos_game_auto_package"
    New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null
    Copy-Item -Force (Join-Path $ProjectDir "dist\aos_game_auto.exe") $PackageDir
    Copy-Item -Force (Join-Path $ProjectDir "dist\template_capture_gui.exe") $PackageDir
    Copy-Item -Force (Join-Path $ProjectDir "run_with_adb_path.bat") $PackageDir
    Copy-Item -Recurse -Force (Join-Path $ProjectDir "config") $PackageDir
    Copy-Item -Recurse -Force (Join-Path $ProjectDir "templates") $PackageDir
    New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "logs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "screenshots") | Out-Null

    Write-Host "Build complete:"
    Write-Host $PackageDir
}
finally {
    Pop-Location
}
