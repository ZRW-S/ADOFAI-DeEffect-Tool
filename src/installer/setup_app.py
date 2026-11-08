# -*- coding: utf-8 -*-
"""ADOFAI 去特效工具 安装程序（自解压安装）。"""
import os
import sys
import shutil
import threading
import winreg
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import pylnk3
except ImportError:
    pylnk3 = None

APP_NAME = "ADOFAI 去特效工具"
APP_VERSION = "2.0.0"
PUBLISHER = "Zrw"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ADOFAI_DeEffect"
APP_EXE = "UI.exe"
UNINSTALL_EXE = "卸载.exe"
CREATE_NO_WINDOW = 0x08000000

PAYLOAD_DIR = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "payload")


def debug_log(msg):
    path = os.environ.get("ADOFAI_SETUP_LOG")
    if not path:
        return
    try:
        import time
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.2f} {msg}\n")
    except Exception:
        pass


def default_dir():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", "ADOFAI_去特效工具")


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


def make_shortcut(lnk_path, target, workdir, icon, desc):
    """用纯 Python 生成 .lnk，避免调用 PowerShell / COM。"""
    if pylnk3 is None:
        raise RuntimeError("缺少 pylnk3 组件，无法创建快捷方式")
    pylnk3.for_file(target, lnk_name=lnk_path, description=desc,
                    icon_file=icon, icon_index=0, work_dir=workdir)


def copy_payload(install_dir, progress=None):
    files = []
    for root, dirs, names in os.walk(PAYLOAD_DIR):
        for n in names:
            files.append(os.path.join(root, n))
    total = len(files) or 1
    os.makedirs(install_dir, exist_ok=True)
    for i, src in enumerate(files):
        rel = os.path.relpath(src, PAYLOAD_DIR)
        dst = os.path.join(install_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        if progress:
            progress(int((i + 1) / total * 100))
    # 写入卸载程序
    payload_uninstall = os.path.join(PAYLOAD_DIR, UNINSTALL_EXE)
    if os.path.exists(payload_uninstall):
        shutil.copy2(payload_uninstall, os.path.join(install_dir, UNINSTALL_EXE))


def register_uninstall(install_dir):
    exe = os.path.join(install_dir, APP_EXE)
    uninstaller = os.path.join(install_dir, UNINSTALL_EXE)
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    values = {
        "DisplayName": APP_NAME,
        "DisplayVersion": APP_VERSION,
        "Publisher": PUBLISHER,
        "InstallLocation": install_dir,
        "DisplayIcon": exe,
        "UninstallString": f'"{uninstaller}"',
        "NoModify": 1,
        "NoRepair": 1,
    }
    for name, value in values.items():
        kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
        winreg.SetValueEx(key, name, 0, kind, value)
    try:
        total = sum(os.path.getsize(os.path.join(install_dir, f))
                    for f in os.listdir(install_dir)
                    if os.path.isfile(os.path.join(install_dir, f)))
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, max(1, total // 1024))
    except Exception:
        pass
    winreg.CloseKey(key)


def install(install_dir, create_desktop, progress=None):
    debug_log("install start " + install_dir)
    copy_payload(install_dir, progress)
    debug_log("payload copied")
    exe = os.path.join(install_dir, APP_EXE)
    uninstaller = os.path.join(install_dir, UNINSTALL_EXE)
    icon = exe
    warnings = []
    if create_desktop:
        try:
            debug_log("desktop shortcut")
            make_shortcut(os.path.join(desktop_dir(), f"{APP_NAME}.lnk"), exe, install_dir, icon, APP_NAME)
        except Exception as exc:
            warnings.append(f"创建桌面快捷方式失败：{exc}")
            debug_log("desktop shortcut failed: %s" % exc)
    try:
        menu_dir = os.path.join(start_menu_dir(), APP_NAME)
        os.makedirs(menu_dir, exist_ok=True)
        debug_log("menu shortcut")
        make_shortcut(os.path.join(menu_dir, f"{APP_NAME}.lnk"), exe, install_dir, icon, APP_NAME)
        make_shortcut(os.path.join(menu_dir, "卸载.lnk"), uninstaller, install_dir, icon, f"卸载 {APP_NAME}")
        debug_log("uninstall shortcut")
    except Exception as exc:
        warnings.append(f"创建开始菜单快捷方式失败：{exc}")
        debug_log("menu shortcut failed: %s" % exc)
    try:
        register_uninstall(install_dir)
        debug_log("registry done")
    except Exception as exc:
        warnings.append(f"写入卸载信息失败：{exc}")
        debug_log("registry failed: %s" % exc)
    return warnings


class SetupApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} 安装程序 v{APP_VERSION}")
        try:
            self.root.iconbitmap(default=os.path.join(getattr(sys, "_MEIPASS", "."), "app.ico"))
        except Exception:
            pass
        self.root.resizable(False, False)
        self.dir_var = tk.StringVar(value=default_dir())
        self.desktop_var = tk.BooleanVar(value=True)
        self._build()
        self.root.update_idletasks()
        w, h = 620, 400
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        outer = tk.Frame(self.root, padx=24, pady=18)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text=f"安装 {APP_NAME}", font=("Microsoft YaHei UI", 16, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(outer, text=f"版本 v{APP_VERSION}  ·  {PUBLISHER}", anchor="w",
                 fg="#666666").pack(fill="x", pady=(4, 12))
        tk.Label(outer, text="本程序用于清理《冰与火之舞》谱面中的视觉特效，降低游玩卡顿。",
                 anchor="w", justify="left", wraplength=560).pack(fill="x", pady=(0, 16))

        row = tk.Frame(outer)
        row.pack(fill="x")
        tk.Label(row, text="安装位置：").pack(side="left")
        self.path_entry = ttk.Entry(row, textvariable=self.dir_var)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="浏览…", command=self.browse).pack(side="left")

        ttk.Checkbutton(outer, text="创建桌面快捷方式", variable=self.desktop_var).pack(
            anchor="w", pady=(14, 10))

        self.progress = ttk.Progressbar(outer, maximum=100)
        self.progress.pack(fill="x", pady=(8, 6))
        self.status = tk.StringVar(value="准备就绪")
        tk.Label(outer, textvariable=self.status, anchor="w", fg="#555555").pack(fill="x")

        btns = tk.Frame(outer)
        btns.pack(fill="x", side="bottom", pady=(16, 0))
        self.install_btn = ttk.Button(btns, text="安装", command=self.start_install)
        self.install_btn.pack(side="right")
        ttk.Button(btns, text="退出", command=self.root.destroy).pack(side="right", padx=(0, 10))

    def browse(self):
        path = filedialog.askdirectory(title="选择安装位置")
        if path:
            self.dir_var.set(path)

    def set_progress(self, value):
        self.progress["value"] = value
        self.root.update_idletasks()

    def start_install(self):
        install_dir = self.dir_var.get().strip()
        if not install_dir:
            messagebox.showerror("错误", "请选择安装位置。")
            return
        if os.path.exists(install_dir) and os.listdir(install_dir) and \
                not os.path.exists(os.path.join(install_dir, APP_EXE)):
            if not messagebox.askyesno("提示", "目标文件夹不是空的，仍要安装到这里吗？"):
                return
        self.install_btn.configure(state="disabled")
        self.status.set("正在安装…")
        self.progress["value"] = 0

        def work():
            try:
                install(install_dir, self.desktop_var.get(), self.set_progress)
                self.root.after(0, lambda: self.finish(install_dir))
            except Exception as exc:
                self.root.after(0, lambda: self.fail(exc))

        threading.Thread(target=work, daemon=True).start()

    def finish(self, install_dir):
        self.progress["value"] = 100
        self.status.set("安装完成")
        if messagebox.askyesno("安装完成", f"{APP_NAME} 已安装完成。\n\n是否立即运行？"):
            try:
                os.startfile(os.path.join(install_dir, APP_EXE))
            except Exception:
                pass
        self.root.destroy()

    def fail(self, exc):
        self.install_btn.configure(state="normal")
        self.status.set("安装失败")
        messagebox.showerror("安装失败", str(exc))


def silent_install(install_dir, desktop=False):
    debug_log("silent_install")
    warnings = install(install_dir, desktop)
    debug_log("install finished")
    for w in warnings:
        print("warning:", w)
    print("install ok:", install_dir)


def main():
    if "--silent" in sys.argv:
        install_dir = default_dir()
        if "--dir" in sys.argv:
            install_dir = sys.argv[sys.argv.index("--dir") + 1]
        desktop = "--desktop" in sys.argv
        silent_install(install_dir, desktop)
        return
    root = tk.Tk()
    SetupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
