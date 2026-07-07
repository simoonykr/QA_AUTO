@echo off
setlocal

REM Edit this path if adb.exe is not in PATH and platform-tools is not next to this file.
set ADB_PATH=platform-tools\adb.exe

if not exist "%ADB_PATH%" (
    echo adb.exe was not found at "%ADB_PATH%".
    echo.
    echo Options:
    echo  1. Copy the Android platform-tools folder next to this bat file.
    echo  2. Edit ADB_PATH in this file.
    echo  3. Add adb.exe to Windows PATH and run aos_game_auto.exe directly.
    echo.
    pause
    exit /b 1
)

aos_game_auto.exe --adb "%ADB_PATH%"
pause
