@echo off
REM Startet den lokalen Kickbase-Runner. Fenster offen lassen (oder per Aufgabenplanung beim Anmelden starten).
cd /d "%~dp0"
:loop
python local_runner.py
echo Runner beendet (%date% %time%) - Neustart in 30 s ...
timeout /t 30 /nobreak >nul
goto loop
