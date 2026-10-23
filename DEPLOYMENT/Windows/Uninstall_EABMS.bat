@echo off
setlocal EnableDelayedExpansion
title EABMS Application Uninstaller
color 0B

:: ==============================================================================
:: ENTERPRISE ACCOUNTS & BUSINESS MANAGEMENT SYSTEM (EABMS) - Uninstall_EABMS.bat
:: ==============================================================================
:: Flow:
::   1. If not admin -> relaunch THIS EXACT FILE elevated (no arg passing)
::   2. Resolve AppRoot from this file's own location (two levels up)
::   3. Stage Uninstall-EABMS.ps1 to %%TEMP%%
::   4. Confirm prompt
::   5. Run PS1 engine
::   6. pause
:: ==============================================================================

:: ---------------------------------------------------------------------------
:: STEP 1 - Admin elevation
:: ---------------------------------------------------------------------------
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [*] Requesting Administrator Privileges...
    powershell -Command "Start-Process cmd.exe '/c \"%~f0\"' -Verb RunAs"
    exit /b 0
)

:: ---------------------------------------------------------------------------
:: STEP 2 - Resolve AppRoot from this bat's location
::   This file is at: <AppRoot>\DEPLOYMENT\Windows\Uninstall_EABMS.bat
::   So AppRoot = two levels up from %~dp0
:: ---------------------------------------------------------------------------
set "_SD=%~dp0"
set "_SD=!_SD:~0,-1!"
for %%I in ("!_SD!\..") do set "_PAR=%%~fI"
for %%I in ("!_PAR!\..") do set "TARGET_ROOT=%%~fI"
if "!TARGET_ROOT:~-1!"=="\" set "TARGET_ROOT=!TARGET_ROOT:~0,-1!"

:: Accept optional argument override
if not "%~1"=="" (
    set "TARGET_ROOT=%~1"
    if "!TARGET_ROOT:~-1!"=="\" set "TARGET_ROOT=!TARGET_ROOT:~0,-1!"
)

:: Validate
if not exist "!TARGET_ROOT!\02_Backend\manage.py" (
    if exist "D:\EABMS\02_Backend\manage.py" (
        set "TARGET_ROOT=D:\EABMS"
    ) else (
        echo.
        echo [!] Cannot locate EABMS installation.
        echo     Expected: ^<AppRoot^>\02_Backend\manage.py
        echo     Tried   : !TARGET_ROOT!
        echo.
        pause
        exit /b 1
    )
)

:: ---------------------------------------------------------------------------
:: STEP 3 - Stage PS1 to %%TEMP%%
:: ---------------------------------------------------------------------------
set "STAGE_DIR=%TEMP%\EABMS_Uninstall"
if not exist "%STAGE_DIR%" mkdir "%STAGE_DIR%" >nul 2>&1
copy /Y "%~dp0Uninstall-EABMS.ps1" "%STAGE_DIR%\Uninstall-EABMS.ps1" >nul 2>&1
if not exist "%STAGE_DIR%\Uninstall-EABMS.ps1" (
    echo.
    echo [!] Could not stage Uninstall-EABMS.ps1 to %%TEMP%%.
    echo     Ensure Uninstall-EABMS.ps1 is in the same folder as this .bat file.
    echo.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: STEP 4 - Show header
:: ---------------------------------------------------------------------------
echo.
echo ============================================================
echo   ENTERPRISE ACCOUNTS ^& BUSINESS MANAGEMENT SYSTEM (EABMS)
echo            APPLICATION UNINSTALLER
echo ============================================================
echo.
echo  Target  : !TARGET_ROOT!
echo  Ports   : 8020 (NGL)   8021 (EWF)   8022 (CPF)
echo.
echo  This will remove:
echo    [1] Running EABMS servers and app windows (all 3 accounts)
echo    [2] EABMS scheduled tasks and Windows services (if any)
echo    [3] Windows Startup and Registry autorun entries
echo    [4] Desktop and Start Menu shortcuts
echo    [5] Programs and Features entry (if any)
echo    [6] Application folder (you will be asked separately)
echo.
echo ==================== STRICT SAFEGUARDS ====================
echo  [+] PostgreSQL server will NOT be uninstalled.
echo  [+] Databases (eabms_ngl, eabms_ewf, eabms_cpf) will NOT
echo      be modified or deleted.
echo  [+] Python and the shared virtual environment will NOT
echo      be touched.
echo  [+] The original ABMS installation (D:\ABMS) will NOT
echo      be touched.
echo ===========================================================
echo.

:: ---------------------------------------------------------------------------
:: STEP 5 - Confirm
:: ---------------------------------------------------------------------------
choice /C YN /M "Proceed with uninstalling EABMS"
if errorlevel 2 (
    echo.
    echo  Uninstallation cancelled.
    echo.
    pause
    exit /b 0
)

:: ---------------------------------------------------------------------------
:: STEP 6 - Change dir away from app folder, run PS1 engine
:: ---------------------------------------------------------------------------
cd /d "%SystemDrive%\"
echo.
echo  [*] Starting uninstall engine...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass ^
    -File "%STAGE_DIR%\Uninstall-EABMS.ps1" ^
    -AppRoot "!TARGET_ROOT!" ^
    -FromBatch

echo.
pause
exit /b 0
