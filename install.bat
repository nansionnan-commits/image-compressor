@echo off
setlocal
title PicShrink Installer
set "HERE=%~dp0"
set "EXE=%HERE%PicShrink.exe"

if not exist "%EXE%" (
    echo.
    echo [ERROR] PicShrink.exe not found next to this script.
    echo         Folder: %HERE%
    echo         Keep install.bat and PicShrink.exe in the same folder.
    echo.
    pause
    exit /b 1
)

echo ===============================================
echo   PicShrink v9  Installer
echo ===============================================
echo.
echo Installing: Explorer right-click menu,
echo              SendTo entry, Desktop shortcut.
echo.
echo Your existing pictures are never modified.
echo.
"%EXE%" --install
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo [FAILED] Installer exited with code %RC%.
) else (
    echo [DONE] Installation finished.
)
echo.
echo Log file: %TEMP%\picshrink_v9.log
echo.
pause
exit /b %RC%
