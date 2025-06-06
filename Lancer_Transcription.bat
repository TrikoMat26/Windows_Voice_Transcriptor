@echo off
echo ===============================================
echo   Lanceur avec droits d'administrateur
echo   (Necessaire pour le raccourci global F9)
echo ===============================================
echo.

REM Vérifier si on a déjà les droits admin
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Droits d'administrateur detectes.
    echo Lancement de l'application...
    echo.
    goto :launch_app
) else (
    echo Droits d'administrateur requis pour le raccourci F9.
    echo Relancement avec elevation de privileges...
    echo.
    
    REM Relancer avec élévation
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~dpnx0\"' -Verb RunAs"
    exit /b
)

:launch_app
REM Se déplacer dans le répertoire du script
cd /d "%~dp0"

REM Vérifier si l'environnement virtuel existe
if not exist "venv\" (
    echo Creation de l'environnement virtuel...
    python -m venv venv
    if errorlevel 1 (
        echo ERREUR: Impossible de creer l'environnement virtuel
        echo Verifiez que Python est installe et accessible
        pause
        exit /b 1
    )
)

REM Activer l'environnement virtuel
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERREUR: Impossible d'activer l'environnement virtuel
    pause
    exit /b 1
)

REM Installer les dépendances si nécessaire
if not exist "venv\Lib\site-packages\PySide6\" (
    echo Installation des dependances...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERREUR: Impossible d'installer les dependances
        pause
        exit /b 1
    )
)

REM Vérifier la clé API OpenAI
if "%OPENAI_API_KEY%"=="" (
    echo.
    echo ===============================================
    echo   CONFIGURATION DE LA CLE API OPENAI
    echo ===============================================
    echo.
    echo La variable d'environnement OPENAI_API_KEY n'est pas definie.
    echo.
    echo Pour configurer votre cle API:
    echo 1. Allez sur https://platform.openai.com/api-keys
    echo 2. Creez une nouvelle cle API
    echo 3. Copiez la cle
    echo 4. Executez cette commande (remplacez YOUR_API_KEY):
    echo    setx OPENAI_API_KEY "votre_cle_api_ici"
    echo.
    echo L'application peut demarrer sans la cle, mais la transcription ne fonctionnera pas.
    echo.
    set /p continue="Continuer quand meme ? (o/n): "
    if /i not "%continue%"=="o" exit /b
)

echo.
echo ===============================================
echo   LANCEMENT DE L'APPLICATION
echo ===============================================
echo.
echo Application lancee avec droits d'administrateur.
echo Le raccourci F9 devrait maintenant fonctionner.
echo.
echo Pour tester:
echo 1. Attendez que l'application soit chargee
echo 2. Appuyez sur F9 pour demarrer/arreter l'enregistrement
echo 3. L'icone apparaitra dans la barre des taches
echo.

REM Lancer l'application
python main.py

echo.
echo Application fermee.
pause