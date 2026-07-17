$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean EngineeringDocumentTranslator.spec
Write-Host "生成文件：$PSScriptRoot\dist\EngineeringDocumentTranslator.exe"
