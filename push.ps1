
et-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($PSScriptRoot) { Set-Location $PSScriptRoot } else { Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) }

Write-Host "`n==> Cleaning previous build artifacts..." -ForegroundColor Yellow
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }
if (Test-Path ThaiSmartCardReader.spec) { Remove-Item ThaiSmartCardReader.spec -Force }

$venvPython = Join-Path '.venv' 'Scripts/python.exe'
$python = if (Test-Path $venvPython) { Resolve-Path $venvPython } else { 'python' }
Write-Host "Using Python: $python" -ForegroundColor Cyan

try {
	& $python -m PyInstaller --version | Out-Null
} catch {
	Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
	& $python -m pip install --upgrade pip
	& $python -m pip install pyinstaller
}

Write-Host "`n==> Building executable with PyInstaller..." -ForegroundColor Yellow

& $python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --noconsole `
  --icon "icon.ico" `
  --name ThaiSmartCardReader `
  ThaiSmartCardReader.py

if (-not (Test-Path 'dist/ThaiSmartCardReader.exe')) {
	throw 'Build failed: dist/ThaiSmartCardReader.exe not found.'
}

Write-Host "`n==> Build completed: dist/ThaiSmartCardReader.exe" -ForegroundColor Green


$today = Get-Date -Format 'yyyy/MM/dd HH:mm:ss'
Write-Host "`n==> Git add/commit/push..." -ForegroundColor Yellow
git add .
git commit -m "build: ThaiSmartCardReader ($today)"
git push