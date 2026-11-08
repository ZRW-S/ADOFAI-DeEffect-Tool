# -*- coding: utf-8 -*-
"""ADOFAI 去特效工具 卸载程序。"""
import os
import sys
import time
import tempfile
import shutil
import ctypes
import winreg
import subprocess
import tkinter as tk
from tkinter import messagebox

APP_NAME = "ADOFAI 去特效工具"
APP_VERSION = "2.0.0"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ADOFAI_DeEffect"
CREATE_NO_WINDOW = 0x08000000
MOVEFILE_DELAY_UNTIL_REBOOT = 0x4


def desktop_dir():
    override = os.environ.get("ADOFAI_DESKTOP_DIR")
    if override:
        return override
    return os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")


def start_menu_dir():
    override = os.environ.get("ADOFAI_START_MENU_DIR")
    if override:
        return override
    base = os.environ.get("APPDATA") or os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Roaming")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs")


def remove_shortcuts():
    desktop_lnk = os.path.join(desktop_dir(), f"{APP_NAME}.lnk")
    if os.path.exists(desktop_lnk):
        try:
            os.remove(desktop_lnk)
        except OSError:
            pass
    menu_folder = os.path.join(start_menu_dir(), APP_NAME)
    if os.path.isdir(menu_folder):
        try:
            shutil.rmtree(menu_folder, ignore_errors=True)
        except OSError:
            pass


def remove_registry():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass


def schedule_delete(path):
    try:
        ctypes.windll.kernel32.MoveFileExW(str(path), None, MOVEFILE_DELAY_UNTIL_REBOOT)
    except Exception:
        pass


def cleanup_install_dir(install_dir):
    """把自身移到临时目录后同步删除安装目录。"""
    me = os.path.abspath(sys.executable)
    moved = None
    try:
        temp_copy = os.path.join(tempfile.gettempdir(), f"ADOFAI_卸载_{os.getpid()}.exe")
        os.replace(me, temp_copy)
        moved = temp_copy
    except OSError:
        moved = None

    for root, dirs, files in os.walk(install_dir, topdown=False):
        for f in files:
            p = os.path.join(root, f)
            if os.path.abspath(p) == me:
                continue
            try:
                os.remove(p)
            except OSError:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass
    try:
        os.rmdir(install_dir)
    except OSError:
        # 兜底：交给系统在重启后删除
        schedule_delete(install_dir)
    if moved:
        schedule_delete(moved)


def uninstall(install_dir):
    remove_shortcuts()
    remove_registry()
    cleanup_install_dir(install_dir)


def main():
    install_dir = os.path.dirname(os.path.abspath(sys.executable))
    if "--silent" not in sys.argv:
        root = tk.Tk()
        root.withdraw()
        if not messagebox.askyesno(
                f"卸载 {APP_NAME}",
                f"确定要卸载 {APP_NAME} v{APP_VERSION} 吗？\n\n"
                "安装目录中的过滤器配置、设置和窗口记录也会一并删除。"):
            return
        uninstall(install_dir)
        messagebox.showinfo("卸载完成", f"{APP_NAME} 已卸载。")
        root.destroy()
    else:
        uninstall(install_dir)


if __name__ == "__main__":
    main()
