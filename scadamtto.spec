# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para scadaMtto.

Se arma en modo onedir (no onefile) a proposito: onefile descomprime todo a una
carpeta temporal en cada arranque, y este proceso arranca y rearranca bajo un
watchdog. Onedir arranca mas rapido, no deja basura en %TEMP% y permite mirar
que hay adentro cuando algo falla en planta.

Se invoca desde build.sh, que ademas arma la carpeta de distribucion.
"""
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

# Los subcomandos (probe / leer / testdb) se importan tarde, adentro de funciones,
# asi que el analisis estatico no los ve.
ocultos = [
    "scripts.probe_plc",
    "scripts.read_once",
    "scripts.test_db",
    "pymcprotocol",
    "pymcprotocol.type3e",
    "pymcprotocol.type4e",
    "pymcprotocol.mcprotocolconst",
    *collect_submodules("pytds"),
    *collect_submodules("snap7"),
]

# python-snap7 trae la DLL nativa adentro del paquete; sin esto el driver
# Siemens revienta recien al intentar conectar, en planta.
binarios = collect_dynamic_libs("snap7")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binarios,
    datas=[("src/web/static/index.html", "src/web/static")],
    hiddenimports=ocultos,
    hookspath=[],
    runtime_hooks=[],
    # Bulto que no se usa y agranda el paquete varios cientos de MB.
    excludes=[
        "tkinter", "numpy", "PIL", "cv2", "matplotlib", "pandas",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "pytest", "IPython",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scadamtto",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Con consola: el watchdog la mantiene abierta y ahi se ve el log en vivo.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="scadamtto",
)
