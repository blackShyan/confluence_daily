from __future__ import annotations

import sys


APP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "ConfluenceDailyUploader"


def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        return

    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m confluence_daily'

