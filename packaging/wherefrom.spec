# PyInstaller spec for the installed (folder) build: wherefrom.exe and the
# windowless wherefromw.exe share one folder of libraries. Unlike the
# single-file programs, nothing is unpacked to a temp folder on each start,
# so the right-click window and the browser extension's helper start fast.
#
#   pyinstaller packaging/wherefrom.spec      -> dist/wherefrom/
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - set by PyInstaller
ICON = os.path.join(ROOT, "packaging", "wherefrom.ico")

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "packaging", "entry.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "wherefrom", "extension"), "wherefrom/extension")],
)
pyz = PYZ(a.pure)  # noqa: F821

console = EXE(  # noqa: F821
    pyz, a.scripts, [], exclude_binaries=True, name="wherefrom", console=True, icon=ICON)
windowless = EXE(  # noqa: F821
    pyz, a.scripts, [], exclude_binaries=True, name="wherefromw", console=False, icon=ICON)

COLLECT(console, windowless, a.binaries, a.datas, name="wherefrom")  # noqa: F821
