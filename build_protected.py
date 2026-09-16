import os
import sys
import shutil
import subprocess

def main():
    print("=== حماية الكود المصدري باستخدام PyArmor ===")
    
    # 1. Clean previous builds
    for d in ['build', 'dist', 'protected_src']:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
            
    # 2. Obfuscate source code
    print("[*] Obfuscating source code...")
    scripts = ['app.py', 'node_lock.py', 'recovery_engine.py', 'migration_engine.py']
    
    # Check if all scripts exist
    for s in list(scripts):
        if not os.path.exists(s):
            print(f"[-] WARNING: Script {s} not found, skipping...")
            scripts.remove(s)
            
    # Add an empty __init__.py so PyInstaller treats protected_src as a module path if needed
    os.makedirs('protected_src', exist_ok=True)
    with open('protected_src/__init__.py', 'w') as f:
        pass
        
    cmd = ['pyarmor', 'gen', '-O', 'protected_src'] + scripts
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[-] PyArmor failed.")
        sys.exit(1)
        
    print("[+] Code obfuscated successfully in protected_src/")
    
    # 3. Create PyInstaller spec for protected build
    spec_content = """# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['protected_src/app.py'],
    pathex=['protected_src'],
    binaries=[],
    datas=[('static', 'static'), ('templates', 'templates'), ('data', 'data')],
    hiddenimports=['node_lock', 'recovery_engine', 'migration_engine'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['static/icons/stargate_logo.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='StargateDelivery',
)
"""
    with open('Protected_StargateDelivery.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)
        
    print("[*] Running PyInstaller on protected code...")
    # 4. Build with PyInstaller
    cmd_build = ['pyinstaller', '--clean', '-y', 'Protected_StargateDelivery.spec']
    result_build = subprocess.run(cmd_build)
    
    if result_build.returncode == 0:
        print("[+] SUCCESS! Protected executable built in dist/StargateDelivery/")
    else:
        print("[-] PyInstaller failed.")
        sys.exit(1)

if __name__ == '__main__':
    main()
