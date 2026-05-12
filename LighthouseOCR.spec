# -*- mode: python ; coding: utf-8 -*-
#
# LighthouseOCR — PyInstaller build spec
#
# Build command:
#   pyinstaller LighthouseOCR.spec
#
# Output:
#   dist/LighthouseOCR/          ← distribute the whole folder
#     LighthouseOCR.exe
#     _internal/                 ← bundled Python + libs (managed by PyInstaller)
#     Data structure/            ← master Excel files (editable by users)
#     python_env/                ← NOT included here; created by Setup_Moi_Truong.bat
#
# Notes:
#   - PaddleOCR runs in a separate portable Python (python_env/) via subprocess.
#     It is intentionally excluded from this bundle.
#   - After building, copy python_env/ into dist/LighthouseOCR/ (or have users
#     run Setup_Moi_Truong.bat inside the dist folder).

block_cipher = None

a = Analysis(
    ['main_app_qt.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Master data files — placed alongside the exe so users can edit them
        ('Data structure', 'Data structure'),
        # Runtime assets
        ('app_style.qss', '.'),
        ('icon.ico', '.'),
        ('pipeline.yaml', '.'),
        # OCR subprocess script — called by module_paddle_ocr.py via portable Python
        ('ocr_runner.py', '.'),
    ],
    hiddenimports=[
        'PyQt5.sip',
        'openpyxl.cell._writer',
        'google.genai',
        'google.auth',
        'google.auth.transport.requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude OCR stack — it runs in python_env/ subprocess, not in the main process
    excludes=['paddlepaddle', 'paddleocr', 'paddle', 'pytesseract', 'cv2'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # folder build (not onefile)
    name='LighthouseOCR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,              # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LighthouseOCR',       # → dist/LighthouseOCR/
)
