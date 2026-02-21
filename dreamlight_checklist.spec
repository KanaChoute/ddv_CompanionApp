# dreamlight_checklist.spec
# ════════════════════════════════════════════════════════════════════════
# Compilation :
#     python -m PyInstaller dreamlight_checklist.spec --clean
# ════════════════════════════════════════════════════════════════════════

block_cipher = None

from pathlib import Path

# Assets obligatoires de CustomTkinter (thèmes JSON + images)
try:
    import customtkinter
    ctk_path = Path(customtkinter.__file__).parent
    ctk_assets = [(str(ctk_path), "customtkinter")]
except ImportError:
    ctk_assets = []

a = Analysis(
    ["dreamlight_checklist.py"],
    pathex=[],
    binaries=[],
    datas=ctk_assets,
    hiddenimports=[
        "customtkinter",
        "sqlite3",
        "csv",
        "json",
        "pathlib",
        "fpdf",
        "fpdf.enums",
        "fpdf.fonts",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "tkinter",
        "tkinter.messagebox",
        "tkinter.simpledialog",
        "tkinter.filedialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "matplotlib.pyplot",
        "matplotlib.backends",
        "scipy",
        "numpy.testing",
        "numpy.distutils",
        "reportlab",
        "discord",
        "aiohttp",
        "asyncio",
        "tkinter.test",
        "unittest",
        "doctest",
        "pydoc",
        "distutils",
        "xmlrpc",
        "xml.etree",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DDV_Checklist",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
