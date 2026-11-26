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
    assert command.endswith(' show --gui "%1"')     # quoted: paths can have spaces
    assert command.startswith('"')
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
