@echo off
chcp 65001 >nul
adb kill-server
adb start-server
timeout /t 1 >nul

setlocal enabledelayedexpansion
set PORT=27180

set "FAILED_DEVICES="

echo [ Starting scrcpy for connected devices... ]

for /f "skip=1 tokens=1" %%i in ('adb devices') do (
    set /a PORT+=1
    set DEVICE=%%i
    echo.
    echo === Connecting to !DEVICE! (Port !PORT!) ===

    scrcpy -s !DEVICE! --no-audio --port !PORT! --window-title "Device !DEVICE!" >nul 2>&1

    if !errorlevel! neq 0 (
        echo [!] Failed to connect: !DEVICE! — Retrying...
        timeout /t 1 >nul

        scrcpy -s !DEVICE! --no-audio --port !PORT! --window-title "Device !DEVICE!" >nul 2>&1

        if !errorlevel! neq 0 (
            echo [X] Failed again: !DEVICE!
            set "FAILED_DEVICES=!FAILED_DEVICES! !DEVICE!"
        ) else (
            echo [+] Retry success: !DEVICE!
        )
    ) else (
        echo [+] Connected: !DEVICE!
    )

    timeout /t 1 >nul
)

echo.
echo ===== Summary =====
if defined FAILED_DEVICES (
    echo [!] Devices that failed to connect:
    echo     !FAILED_DEVICES!
) else (
    echo [+] All devices connected successfully!
)
echo ====================
pause
