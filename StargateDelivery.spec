# -*- mode: python ; coding: utf-8 -*-
# ============================================================
# Stargate Delivery System - PyInstaller Production Build Spec
# يقوم بتحويل البرنامج إلى EXE مستقل لا يحتاج Python
# ============================================================

import os
BASE = 'D:/STARGATE/repo'

a = Analysis(
    [f'{BASE}/app.py'],
    pathex=[BASE],
    binaries=[],
    datas=[
        # ── واجهات HTML ──
        (f'{BASE}/templates', 'templates'),
        # ── ملفات CSS/JS/صور ──
        (f'{BASE}/static',    'static'),
        # ── Core & Routes Blueprints ──
        (f'{BASE}/core',      'core'),
        (f'{BASE}/routes',    'routes'),
        # ── Database Template ──
        (f'{BASE}/data/stargate_empty.db', 'data'),
        # ── Cloud Config ──
        (f'{BASE}/cloud_config.json', '.'),
        # ── وحدات Python الداخلية ──
        (f'{BASE}/license_manager.py',          '.'),
        (f'{BASE}/node_lock.py',                '.'),
        (f'{BASE}/ota_updater.py',              '.'),
        (f'{BASE}/migration_engine.py',         '.'),
        (f'{BASE}/recovery_engine.py',          '.'),
        (f'{BASE}/secure_env.py',               '.'),
        (f'{BASE}/config.py',                   '.'),
        (f'{BASE}/stargate_ai_engine.py',       '.'),
        (f'{BASE}/telegram_reporter.py',        '.'),
        (f'{BASE}/backup_lifecycle_manager.py', '.'),
        (f'{BASE}/stargate_security_manager.py','.'),
        (f'{BASE}/gemini_client.py',            '.'),
        (f'{BASE}/stargate_master.py',          '.'),
    ],
    hiddenimports=[
        # Flask & WSGI
        'flask', 'flask.templating', 'flask.json', 'jinja2', 'jinja2.ext',
        'werkzeug', 'werkzeug.security', 'werkzeug.serving',
        'waitress',
        # Core & Blueprints
        'core', 'core.extensions', 'core.ai_engine', 'core.database', 'core.security',
        'routes', 'routes.auth', 'routes.orders', 'routes.couriers', 'routes.merchants',
        'routes.treasury', 'routes.reports', 'routes.admin', 'routes.api',
        'routes.products', 'routes.employees', 'routes.customers',
        'routes.service_providers', 'routes.misc',
        # Crypto & Security
        'cryptography', 'cryptography.fernet', 'cryptography.hazmat.primitives',
        'cryptography.hazmat.backends',
        # Project Modules
        'node_lock', 'license_manager', 'migration_engine', 'recovery_engine',
        'ota_updater', 'secure_env', 'config', 'stargate_ai_engine',
        'telegram_reporter', 'backup_lifecycle_manager', 'stargate_security_manager',
        'gemini_client', 'stargate_master',
        # Standard
        'sqlite3', 'hashlib', 'hmac', 'winreg', 'platform', 'threading',
        'urllib.request', 'zipfile', 'shutil', 'subprocess',
        # Networking
        'requests', 'urllib3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest', 'pdb', 'doctest'],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StargateDelivery',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_dir=None,
    console=False,                # لا نافذة سوداء - يعمل في الخلفية
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=f'{BASE}/static/icons/stargate_logo.ico',
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StargateDelivery',
)
