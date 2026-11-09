@echo off
rem Arranque manual, con la consola a la vista. Para probar en planta.
cd /d "%~dp0.."
".venv\Scripts\python.exe" main.py
pause
