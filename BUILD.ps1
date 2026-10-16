$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python venv failed' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$converterSchema = (Resolve-Path -LiteralPath schema).Path
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onedir --windowed --name ShaprConverter --add-data "$converterSchema;schema" --collect-all OCP --collect-all parasolid_kit --copy-metadata cadquery-ocp-novtk --copy-metadata cadquery-ocp-proxy --copy-metadata parasolid-kit ShaprConverter.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Write-Host 'Ready: dist\ShaprConverter\ShaprConverter.exe'
