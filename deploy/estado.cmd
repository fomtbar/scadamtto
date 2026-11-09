@echo off
rem estado el adquisidor scadaMtto (ver control.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0control.ps1" -Accion estado -Pausa
