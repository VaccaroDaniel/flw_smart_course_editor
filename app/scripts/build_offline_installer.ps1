param(
  [string]$PythonRoot = "C:\Users\com\AppData\Local\Programs\Python\Python311",
  [string]$OutputRoot = "",
  [string]$BundleName = ""
)

$ErrorActionPreference = "Stop"

$appRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) {
  $OutputRoot = Join-Path $appRoot "dist"
}
if (-not $BundleName) {
  $BundleName = "FLW-Smart-Course-Editor-offline-py3119"
}

$pythonRootPath = (Resolve-Path -LiteralPath $PythonRoot).Path
$outputRootPath = [System.IO.Path]::GetFullPath($OutputRoot)
$stagePath = Join-Path $outputRootPath $BundleName
$zipPath = Join-Path $outputRootPath "$BundleName.zip"

if (-not (Test-Path -LiteralPath (Join-Path $pythonRootPath "python.exe"))) {
  throw "python.exe was not found under $pythonRootPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $pythonRootPath "pythonw.exe"))) {
  throw "pythonw.exe was not found under $pythonRootPath"
}

if (Test-Path -LiteralPath $stagePath) {
  Remove-Item -LiteralPath $stagePath -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}

New-Item -ItemType Directory -Path $stagePath | Out-Null

$appStage = Join-Path $stagePath "app"
$runtimeStage = Join-Path $stagePath "runtime\python311"
New-Item -ItemType Directory -Path $appStage | Out-Null
New-Item -ItemType Directory -Path $runtimeStage | Out-Null

$appItems = @(
  "server.py",
  "scorm_gui_support.py",
  "moodle_import_support.py",
  "p1_content_deployment_contract.py",
  "flw_moodle_course_map.json",
  "flw_moodle_stage_course_map.json",
  "flw_moodle_unit_section_map.json",
  "flw_moodle_unit_scorm_map.json",
  "README.md",
  "docs",
  "static",
  "scripts"
)
foreach ($item in $appItems) {
  $source = Join-Path $appRoot $item
  $dest = Join-Path $appStage $item
  if (Test-Path -LiteralPath $source -PathType Container) {
    Copy-Item -LiteralPath $source -Destination $dest -Recurse -Force
  } elseif (Test-Path -LiteralPath $source -PathType Leaf) {
    Copy-Item -LiteralPath $source -Destination $dest -Force
  }
}

$rootFiles = @(
  "python.exe",
  "pythonw.exe",
  "python3.dll",
  "python311.dll",
  "vcruntime140.dll",
  "vcruntime140_1.dll",
  "LICENSE.txt"
)
foreach ($file in $rootFiles) {
  $source = Join-Path $pythonRootPath $file
  if (Test-Path -LiteralPath $source) {
    Copy-Item -LiteralPath $source -Destination (Join-Path $runtimeStage $file) -Force
  }
}

$runtimeDirs = @("DLLs", "Lib", "tcl")
foreach ($dir in $runtimeDirs) {
  $source = Join-Path $pythonRootPath $dir
  if (Test-Path -LiteralPath $source -PathType Container) {
    Copy-Item -LiteralPath $source -Destination (Join-Path $runtimeStage $dir) -Recurse -Force
  }
}

$skipDirs = @(
  "Lib\site-packages",
  "Lib\ensurepip",
  "Lib\idlelib",
  "Lib\test",
  "Lib\tests",
  "Lib\tkinter\test",
  "Lib\unittest\test",
  "Lib\venv",
  "Lib\distutils",
  "Lib\lib2to3",
  "Lib\pydoc_data",
  "Lib\ctypes\test",
  "Lib\sqlite3\test",
  "Lib\urllib\test",
  "Lib\xml\test",
  "Lib\email\test"
)
foreach ($relDir in $skipDirs) {
  $target = Join-Path $runtimeStage $relDir
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}

Get-ChildItem -LiteralPath $runtimeStage -Recurse -Directory -Force |
  Where-Object { $_.Name -eq "__pycache__" } |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

Get-ChildItem -LiteralPath $runtimeStage -Recurse -File -Force |
  Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

$runPortable = @'
@echo off
setlocal
set "BUNDLE_DIR=%~dp0"
set "PYTHONHOME=%BUNDLE_DIR%runtime\python311"
set "PYTHONPATH="
pushd "%BUNDLE_DIR%app"
start "" "%BUNDLE_DIR%runtime\python311\pythonw.exe" "%BUNDLE_DIR%app\server.py" --host 127.0.0.1 --port 8788
popd
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8788
endlocal
'@
Set-Content -LiteralPath (Join-Path $stagePath "Run Editor.bat") -Value $runPortable -Encoding ASCII

$installPs1 = @'
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
'@
Set-Content -LiteralPath (Join-Path $stagePath "Install.ps1") -Value $installPs1 -Encoding UTF8

$installBat = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
pause
'@
Set-Content -LiteralPath (Join-Path $stagePath "Install.bat") -Value $installBat -Encoding ASCII

$readme = @"
# FLW Smart Course Editor Offline Installer

This folder contains the editor and its own bundled Python 3.11.9 runtime.
It does not require internet access or a system Python install.

## Install

Double-click:

    Install.bat

The installer copies the editor to:

    %LOCALAPPDATA%\AdventureScormEditor

and creates a Desktop shortcut named "FLW Smart Course Editor".

## Portable run

You can also run without installing:

    Run Editor.bat

The editor opens at:

    http://127.0.0.1:8788

## Notes

- This installs/runs the editor only. Course unit folders remain wherever you keep them.
- Use the Browse button in the editor to select the course root directory.
- The bundled runtime is Python 3.11.9.
- SCORM editing and export work offline. Direct Moodle import additionally requires access to the target Moodle installation, its config.php, and its compatible PHP executable.
- Machine-specific settings, certificates, logs, caches, source units, generated SCORM packages, and Moodle credentials are not included.
"@
Set-Content -LiteralPath (Join-Path $stagePath "README-OFFLINE-INSTALLER.md") -Value $readme -Encoding UTF8

$serverSource = Get-Content -LiteralPath (Join-Path $appRoot "server.py") -Raw
$navigatorVersion = if ($serverSource -match 'FLW_NAVIGATOR_VERSION\s*=\s*(\d+)') { [int]$Matches[1] } else { $null }
$manifest = [ordered]@{
  name = "FLW Smart Course Editor Offline Installer"
  bundle = $BundleName
  builtAt = (Get-Date).ToString("s")
  pythonRoot = $pythonRootPath
  pythonVersion = (& (Join-Path $pythonRootPath "python.exe") --version)
  navigatorVersion = $navigatorVersion
  appRoot = $appRoot
  entrypoints = @("Install.bat", "Run Editor.bat")
  excludedLocalState = @(".settings.json", "certs", "logs", "batch_jobs", "unit_cache", "verification_exports", "pilot_exports")
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stagePath "bundle-manifest.json") -Encoding UTF8

$testPythonHome = Join-Path $stagePath "runtime\python311"
$testPythonPath = ""
$testPython = Join-Path $testPythonHome "python.exe"
$testScript = "import tkinter, http.server, zipfile, pathlib; import sys; print(sys.version.split()[0])"
$oldPythonHome = $env:PYTHONHOME
$oldPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONHOME = $testPythonHome
  $env:PYTHONPATH = $testPythonPath
  $runtimeVersion = & $testPython -c $testScript
  & $testPython -m py_compile `
    (Join-Path $stagePath "app\server.py") `
    (Join-Path $stagePath "app\scorm_gui_support.py") `
    (Join-Path $stagePath "app\moodle_import_support.py") `
    (Join-Path $stagePath "app\p1_content_deployment_contract.py")
} finally {
  $env:PYTHONHOME = $oldPythonHome
  $env:PYTHONPATH = $oldPythonPath
}

Get-ChildItem -LiteralPath $appStage -Recurse -Directory -Force |
  Where-Object { $_.Name -eq "__pycache__" } |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

Get-ChildItem -LiteralPath $appStage -Recurse -File -Force |
  Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

Get-ChildItem -LiteralPath $runtimeStage -Recurse -Directory -Force |
  Where-Object { $_.Name -eq "__pycache__" } |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

Get-ChildItem -LiteralPath $runtimeStage -Recurse -File -Force |
  Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
  ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

Compress-Archive -Path (Join-Path $stagePath "*") -DestinationPath $zipPath -CompressionLevel Optimal

$zipItem = Get-Item -LiteralPath $zipPath
$stageBytes = (Get-ChildItem -LiteralPath $stagePath -Recurse -File | Measure-Object Length -Sum).Sum
[pscustomobject]@{
  Bundle = $stagePath
  Zip = $zipPath
  RuntimeVersion = $runtimeVersion
  StageMB = [math]::Round($stageBytes / 1MB, 1)
  ZipMB = [math]::Round($zipItem.Length / 1MB, 1)
} | ConvertTo-Json -Depth 4
