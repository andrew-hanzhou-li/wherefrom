import os
import sys

import pytest

from wherefrom import shell


class FakeRegistry:
    def __init__(self):
        self.values = {}

    def set_value(self, key, name, value):
        self.values[(key, name)] = value

    def get_value(self, key, name):
        return self.values.get((key, name))

    def delete_value(self, key, name):
        self.values.pop((key, name), None)

    def delete_key(self, key):
        for k in [k for k in self.values if k[0] == key or k[0].startswith(key + "\\")]:
            del self.values[k]


def test_install_adds_the_menu_entry():
    reg = FakeRegistry()
    shell.install(reg)
    assert reg.values[(shell.MENU_KEY, "")] == "Where did this come from?"
    command = reg.values[(shell.MENU_KEY + r"\command", "")]
    assert command.endswith(' show --gui -- "%1"')  # quoted: paths can have spaces; --: never an option
    assert command.startswith('"')
    if not getattr(__import__("sys"), "frozen", False):
        assert " -P -m wherefrom " in command      # never imports from the clicked file's folder
    assert (shell.RUN_KEY, shell.RUN_VALUE) not in reg.values


def test_autostart_and_uninstall_remove_everything():
    reg = FakeRegistry()
    reg.set_value(shell.RUN_KEY, "SomethingElse", "keep me")
    shell.install(reg, autostart=True)
    assert reg.values[(shell.RUN_KEY, shell.RUN_VALUE)].endswith(" watch")
    shell.uninstall(reg)
    assert reg.values == {(shell.RUN_KEY, "SomethingElse"): "keep me"}


def test_uninstall_twice_is_fine():
    reg = FakeRegistry()
    shell.uninstall(reg)
    shell.uninstall(reg)


@pytest.mark.skipif(sys.platform != "win32" or not os.environ.get("CI"),
                    reason="writes the real registry; only on a throwaway CI machine")
def test_real_registry_round_trip():
    reg = shell.WindowsRegistry()
    shell.install(reg, autostart=True)
    assert reg.get_value(shell.MENU_KEY, "") == "Where did this come from?"
    assert "show --gui" in reg.get_value(shell.MENU_KEY + r"\command", "")
    assert reg.get_value(shell.RUN_KEY, shell.RUN_VALUE).endswith(" watch")
    shell.uninstall(reg)
    assert reg.get_value(shell.MENU_KEY, "") is None
    assert reg.get_value(shell.RUN_KEY, shell.RUN_VALUE) is None


def test_a_module_planted_next_to_the_file_does_not_run(tmp_path):
    # Explorer runs the menu command in the clicked file's folder. Python's
    # -m would import argparse.py from there instead of its own, unless -P.
    import subprocess
    (tmp_path / "argparse.py").write_text("print('PLANTED MODULE RAN')\nraise SystemExit(9)\n")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command = shell.launcher(windowed=False)
    assert " -P -m wherefrom" in command
    out = subprocess.run([sys.executable, "-P", "-m", "wherefrom", "--version"], cwd=tmp_path,
                         capture_output=True, text=True, env={**os.environ, "PYTHONPATH": repo})
    assert "PLANTED" not in out.stdout and out.returncode == 0
    unsafe = subprocess.run([sys.executable, "-m", "wherefrom", "--version"], cwd=tmp_path,
                            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": repo})
    assert "PLANTED" in unsafe.stdout          # shows the test would catch it
