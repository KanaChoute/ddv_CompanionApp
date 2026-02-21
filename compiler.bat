@echo off
setlocal
cd /d "%~dp0"

echo ════════════════════════════════════════
echo   DDV Checklist — Compilation .exe
echo ════════════════════════════════════════
echo.

:: Vérifie PyInstaller
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : PyInstaller non trouvé.
    echo Lance : pip install pyinstaller
    pause
    exit /b 1
)

:: ── 1. Compilation de l'application principale ──
echo [1/2] Compilation de DDV_Checklist.exe ...
python -m PyInstaller dreamlight_checklist.spec --clean --noconfirm
if errorlevel 1 (
    echo ERREUR lors de la compilation de l'application !
    pause
    exit /b 1
)
echo OK - DDV_Checklist.exe genere dans dist\

echo.

:: ── 2. Compilation du bot Discord ──
echo [2/2] Compilation de DDV_Bot.exe ...
python -m PyInstaller bot_discord.spec --clean --noconfirm
if errorlevel 1 (
    echo ERREUR lors de la compilation du bot !
    pause
    exit /b 1
)
echo OK - DDV_Bot.exe genere dans dist\

echo.
echo ════════════════════════════════════════
echo   Compilation terminee avec succes !
echo   Fichiers dans le dossier : dist\
echo     - DDV_Checklist.exe
echo     - DDV_Bot.exe
echo ════════════════════════════════════════
echo.

:: Met à jour le lanceur dans dist\
echo Copie du lanceur dans dist\ ...
copy /Y lancer_ddv.bat dist\lancer_ddv.bat >nul 2>&1

pause
