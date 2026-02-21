# bot_discord.spec
# ════════════════════════════════════════════════════════════════════════
# Compilation :
#     python -m PyInstaller bot_discord.spec --clean
# ════════════════════════════════════════════════════════════════════════

block_cipher = None

a = Analysis(
    ["bot_discord.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "discord",
        "discord.ext.commands",
        "discord.ext.tasks",
        "discord.app_commands",
        "aiohttp",
        "sqlite3",
        "json",
        "pathlib",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "customtkinter",
        "tkinter",
        "matplotlib",
        "reportlab",
        "fpdf",
        "PIL",
        "unittest",
        "doctest",
        "pydoc",
        "distutils",
        "xmlrpc",
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
    name="DDV_Bot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # console visible pour voir les logs du bot
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
