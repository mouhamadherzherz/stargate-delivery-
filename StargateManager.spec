# -*- mode: python ; coding: utf-8 -*-
import os
import sys

BASE = os.path.dirname(os.path.abspath('desktop_manager.py'))

a = Analysis(
    ['desktop_manager.py'],
    pathex=[BASE],
    binaries=[],
    datas=[
        (os.path.join(BASE, 'manager_templates'), 'manager_templates'),
        (os.path.join(BASE, 'stargate_logo.ico'), '.'),
        (os.path.join(BASE, 'license_manager.py'), '.'),
    ],
    hiddenimports=[
        'waitress',
        'license_manager',
        'stargate_manager',
        'webview',
        'clr',
        'pythonnet',
        'flask',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StargateManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(BASE, 'stargate_logo.ico'),
)
