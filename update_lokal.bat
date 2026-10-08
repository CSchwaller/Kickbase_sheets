@echo off
REM Kickbase-Sheet sofort lokal aktualisieren (Doppelklick genuegt).
REM Optional mit Spieltagen:  update_lokal.bat --days 4 5
cd /d "%~dp0"
set KICKBASE_LEAGUE=6924803
set KICKBASE_SHEET=1xyeA2gvEAq1F1FCoiqU8nNLFF1VorY3fc9t6gfVA5q0
if not exist service_account.json set GOOGLE_SA_FILE=%USERPROFILE%\OneDrive\Desktop\service_account.json
python kickbase_fetch.py %*
echo.
pause
