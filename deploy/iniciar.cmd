@echo off
rem iniciar el adquisidor scadaMtto (ver control.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0control.ps1" -Accion iniciar -Pausa
