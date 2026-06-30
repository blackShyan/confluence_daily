from pathlib import Path

ROOT = Path.cwd().resolve()
if not (ROOT / "src" / "confluence_daily").exists():
    ROOT = Path(SPECPATH).resolve()
if not (ROOT / "src" / "confluence_daily").exists():
    ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
ICON = SRC / "confluence_daily" / "assets" / "app_icon.ico"

hiddenimports = [
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "keyring.backends.Windows",
    "keyring.backends.chainer",
    "keyring.backends.null",
]

a = Analysis(
    [str(SRC / "confluence_daily" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(ICON), "confluence_daily/assets")],
    hiddenimports=hiddenimports,
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
    name="ConfluenceDailyUploader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ConfluenceDailyUploader",
)
