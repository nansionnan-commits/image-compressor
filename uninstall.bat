@echo off
setlocal
title PicShrink Uninstaller
set "HERE=%~dp0"
set "EXE=%HERE%PicShrink.exe"

if not exist "%EXE%" (
    echo.
    echo [ERROR] PicShrink.exe not found next to this script.
    echo         Folder: %HERE%
    echo         Keep uninstall.bat and PicShrink.exe in the same folder.
    echo.
    echo Alternatively run PicShrink.exe --uninstall from the
    echo installed copy under your LOCALAPPDATA folder.
    echo.
    pause
    exit /b 1
)

echo ===============================================
echo   PicShrink v9  Uninstaller
echo ===============================================
echo.
echo Removing: Explorer right-click menu,
echo            SendTo entry, Desktop shortcut.
echo.
echo Compressed results will NOT be deleted.
echo.
"%EXE%" --uninstall
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo [FAILED] Uninstaller exited with code %RC%.
) else (
    echo [DONE] Uninstallation finished.
)
echo.
echo Log file: %TEMP%\picshrink_v9.log
echo.
pause
exit /b %RC%
