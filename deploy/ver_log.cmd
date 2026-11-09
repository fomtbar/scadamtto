@echo off
rem Muestra logs\scadamtto.log en vivo. Ctrl+C para salir.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0control.ps1" -Accion log -Pausa
