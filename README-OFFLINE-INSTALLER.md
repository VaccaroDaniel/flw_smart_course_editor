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
