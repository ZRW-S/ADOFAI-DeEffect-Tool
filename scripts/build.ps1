# 构建脚本（Windows / PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m PyInstaller --noconfirm --onefile --windowed --name UI `
  --icon src/app.ico --version-file src/version_info.txt `
  --add-data "src/icons;icons" `
  --add-data "src/categories;categories" `
  --add-data "src/categories.json;." `
  --add-data "src/app.ico;." `
  --hidden-import PIL._tkinter_finder `
  src/UI.py

Write-Host ""
Write-Host "构建完成：$root\dist\UI.exe"
Write-Host "运行时请把 UI.exe 与 level.exe、events.txt、levelsset.txt、options.txt 放在同一目录。"
