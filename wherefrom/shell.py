"""Add or remove wherefrom's Explorer menu entry and its start-at-login entry.

Everything goes under HKEY_CURRENT_USER, so no admin rights are needed and
other users are not affected. `uninstall` removes exactly what `install`
added.
"""

import sys
from pathlib import Path

MENU_KEY = r"Software\Classes\*\shell\wherefrom"
MENU_TEXT = "Where did this come from?"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "wherefrom"


def launcher(windowed):
    """How to start wherefrom: the .exe when packaged, else Python itself.
    `windowed` picks pythonw.exe so no console window flashes up."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if windowed:
            quiet = exe.with_name("wherefromw.exe")
            if quiet.is_file():
                exe = quiet
        return f'"{exe}"'
    python = Path(sys.executable)
    if windowed and python.with_name("pythonw.exe").is_file():
        python = python.with_name("pythonw.exe")
    return f'"{python}" -m wherefrom'


class WindowsRegistry:
    """The few registry operations needed, on HKEY_CURRENT_USER."""

    def __init__(self):
        import winreg
        self.winreg = winreg

    def set_value(self, key_path, name, value):
        with self.winreg.CreateKey(self.winreg.HKEY_CURRENT_USER, key_path) as key:
            self.winreg.SetValueEx(key, name, 0, self.winreg.REG_SZ, value)

    def get_value(self, key_path, name):
        try:
            with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, key_path) as key:
                return self.winreg.QueryValueEx(key, name)[0]
        except OSError:
            return None

    def delete_value(self, key_path, name):
        try:
            with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, key_path, 0,
                                     self.winreg.KEY_SET_VALUE) as key:
                self.winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass

    def delete_key(self, key_path):
        """Delete a key and its subkeys (winreg can only delete empty keys)."""
        try:
            with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, key_path) as key:
                subkeys = []
                index = 0
                while True:
                    try:
                        subkeys.append(self.winreg.EnumKey(key, index))
                    except OSError:
                        break
                    index += 1
            for subkey in subkeys:
                self.delete_key(key_path + "\\" + subkey)
            self.winreg.DeleteKey(self.winreg.HKEY_CURRENT_USER, key_path)
        except FileNotFoundError:
            pass


def install(registry, autostart=False):
    """Add the menu entry (and, if asked, start the watcher at login)."""
    registry.set_value(MENU_KEY, "", MENU_TEXT)
    registry.set_value(MENU_KEY + r"\command", "", f'{launcher(windowed=True)} show --gui "%1"')
    if autostart:
        registry.set_value(RUN_KEY, RUN_VALUE, f"{launcher(windowed=True)} watch")


def uninstall(registry):
    registry.delete_key(MENU_KEY)
    registry.delete_value(RUN_KEY, RUN_VALUE)
