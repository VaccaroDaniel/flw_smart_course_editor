param(
  [string]$InstallDir = "$env:LOCALAPPDATA\AdventureScormEditor",
  [int]$Port = 8788
)

$ErrorActionPreference = "Stop"

$bundleDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installPath = [System.IO.Path]::GetFullPath($InstallDir)

New-Item -ItemType Directory -Path $installPath -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $bundleDir "app") -Destination $installPath -Recurse -Force
Copy-Item -LiteralPath (Join-Path $bundleDir "runtime") -Destination $installPath -Recurse -Force

$runBat = @"
@echo off
setlocal
set "APP_DIR=$installPath\app"
set "PYTHONHOME=$installPath\runtime\python311"
set "PYTHONPATH="
pushd "%APP_DIR%"
start "" "$installPath\runtime\python311\pythonw.exe" "$installPath\app\server.py" --host 127.0.0.1 --port $Port
popd
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:$Port
endlocal
"@
Set-Content -LiteralPath (Join-Path $installPath "Run Editor.bat") -Value $runBat -Encoding ASCII

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "FLW Smart Course Editor.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $installPath "Run Editor.bat"
$shortcut.WorkingDirectory = $installPath
$shortcut.Description = "FLW Smart Course Editor"
$shortcut.Save()

Write-Host "Installed FLW Smart Course Editor to: $installPath"
Write-Host "Shortcut created: $shortcutPath"
Write-Host "Run it with: $installPath\Run Editor.bat"
