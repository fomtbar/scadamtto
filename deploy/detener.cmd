@echo off
rem detener el adquisidor scadaMtto (ver control.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0control.ps1" -Accion detener -Pausa
