@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_field_notes.ps1"
if errorlevel 1 (
    echo.
    echo The sync did not complete. Review the message above.
)
echo.
pause
