# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build used by the Windows installer and portable ZIPs.

The application used to be shipped as a onefile executable. Onefile has to
extract its Python and Qt runtime before every launch, which made cold starts
needlessly slow. The onedir layout starts in place and keeps support files in
the user-facing ``ApplicationFiles`` directory.
"""

from pathlib import Path


project_root = Path(SPEC).resolve().parent
assets_root = project_root / "translator_app" / "assets"

a = Analysis(
    [str(project_root / "launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(assets_root / "app_icon.png"), "translator_app/assets"),
        (str(assets_root / "*.svg"), "translator_app/assets"),
    ],
    hiddenimports=["PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # These packages are not used by the Qt application. Excluding them keeps
    # accidental global-environment packages out of public builds.
    excludes=[
        "tkinter",
        "torch",
        "pandas",
        "scipy",
        "matplotlib",
        "numpy",
        "pytest",
        "unittest",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DocumentTranslator",
    icon=str(assets_root / "app_icon.ico"),
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
    # PyInstaller 6 places onedir dependencies here. A descriptive ASCII name
    # is clearer than the default "_internal" in portable releases.
    contents_directory="ApplicationFiles",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DocumentTranslator",
)
