@echo off

REM Chemin absolu vers ton environnement virtuel (adapter le chemin si besoin)
set VENV_PATH=F:\GitHub\Voice_Transcriptor\venv

REM Chemin absolu vers ton script principal
set SCRIPT_PATH=F:\GitHub\Voice_Transcriptor\main.py

REM Utilisation de pythonw.exe pour éviter l'ouverture d'une fenêtre console noire
REM start "" "%VENV_PATH%\Scripts\pythonw.exe" "%SCRIPT_PATH%"
REM Demarrage avec fenêtre
start "" "%VENV_PATH%\Scripts\python.exe" "%SCRIPT_PATH%"

REM (Optionnel) Affiche un message furtif puis ferme la fenêtre batch
REM echo Application de transcription lancée en arriere-plan.
REM timeout /t 2 >nul