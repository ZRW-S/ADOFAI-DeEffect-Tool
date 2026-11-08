# -*- coding: utf-8 -*-
"""去特效工具 UI — 基于 Tkinter 的重构版界面。

数据文件（与 UI.exe 同目录）：
  events.txt      每行 "英文事件名 中文名"
  levelsset.txt   过滤器配置
  options.txt     杂项设置（两行 on/off）
  ui_state.json   窗口位置/尺寸记录

打包内资源（PyInstaller 单文件）：
  icons/          事件图标
  categories/     分类图标
  categories.json 游戏编辑器分类与事件顺序
"""
import os
import re
import sys
import json
import time
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk

APP_NAME = "ADOFAI 去特效工具"
APP_VERSION = "2.0.0"
DEV_NAME = "Zrw"
TITLE = f"{APP_NAME} v{APP_VERSION}"

BG = "#eef2f7"
CARD = "#ffffff"
BORDER = "#d8e1ec"
ACCENT = "#3a6ea5"
ACCENT_HOVER = "#2f5a86"
TEXT = "#243447"
MUTED = "#7b8a9a"
DANGER = "#b04a4a"
GREEN = "#2e8b57"
HILITE_BG = "#eaf2fc"
CONSOLE_BG = "#1b2430"
CONSOLE_FG = "#d8e1ea"

FONT = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_TINY = ("Microsoft YaHei UI", 8)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_CAT = ("Microsoft YaHei UI", 9)
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_SUB = ("Microsoft YaHei UI", 9)

TILE_W = 98
TILE_H = 120

# 轨道消失动画统一设置
TRACK_ANIM_MODES = ["不修改", "无", "收缩", "暗淡"]
TRACK_ANIM_MAP = {"无": "None", "收缩": "Shrink", "暗淡": "Fade"}
TRACK_HELP_TEXT = "如果游玩时发现打过的轨道炸的到处都是，建议配置此项"


class Tooltip:
    """简单的鼠标悬停提示。"""

    def __init__(self, widget, text, wrap=280):
        self.widget = widget
        self.text = text
        self.wrap = wrap
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, event=None):
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        tk.Label(self.tip, text=self.text, font=FONT_SMALL, bg="#1b2430",
                 fg="#e8eef6", padx=10, pady=6, wraplength=self.wrap,
                 justify="left").pack()
        self.tip.geometry(f"+{x}+{y}")

    def hide(self, event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


# ---------------------------------------------------------------- base paths
def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = base_dir()
RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
ICON_DIR = os.path.join(RESOURCE_DIR, "icons")
CAT_ICON_DIR = os.path.join(RESOURCE_DIR, "categories")
CATEGORIES_FILE = os.path.join(RESOURCE_DIR, "categories.json")
STATE_FILE = os.path.join(BASE_DIR, "ui_state.json")
EVENTS_FILE = os.path.join(BASE_DIR, "events.txt")
CONFIG_FILE = os.path.join(BASE_DIR, "levelsset.txt")
OPTIONS_FILE = os.path.join(BASE_DIR, "options.txt")


# ---------------------------------------------------------------- file io
def read_text(path, default=""):
    if not os.path.exists(path):
        return default
    data = open(path, "rb").read()
    for enc in ("utf-8-sig", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def load_events():
    """返回 [(英文, 中文)]，保持文件中的顺序。"""
    text = read_text(EVENTS_FILE)
    result = []
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        if " " in line:
            en, zh = line.split(" ", 1)
        else:
            en, zh = line, line
        result.append((en.strip(), zh.strip()))
    return result


def load_categories(event_names):
    """读取游戏编辑器分类数据，并补上未收录事件。"""
    try:
        raw = json.loads(read_text(CATEGORIES_FILE, '{"categories": []}'))
        cats = raw.get("categories", [])
    except Exception:
        cats = []
    known = set()
    result = []
    for c in cats:
        events = [e for e in c.get("events", []) if e in event_names]
        if not events and c.get("key") != "Gameplay":
            continue
        result.append({"key": c["key"], "zh": c.get("zh", c["key"]),
                       "events": events, "taroDLC": c.get("taroDLC", False)})
        known.update(events)
    # 未收录的事件按最接近的分类补进去
    fallback = {"AddParticle": "DecorationFx", "ShieldPlayer": "Gameplay",
                "SetGameSound": "Gameplay", "PlayCustomSound": "Gameplay", "ChangeTrack": "TrackFx"}
    extra_by_cat = {}
    extra = [e for e in event_names if e not in known]
    for ev in extra:
        key = fallback.get(ev, "Gameplay")
        extra_by_cat.setdefault(key, []).append(ev)
    for c in result:
        add = extra_by_cat.pop(c["key"], [])
        if add:
            c["events"].extend(add)
    if extra_by_cat:
        if result:
            result[0]["events"].extend([e for v in extra_by_cat.values() for e in v])
        else:
            result.append({"key": "Gameplay", "zh": "玩法",
                           "events": [e for v in extra_by_cat.values() for e in v],
                           "taroDLC": False})
    return result


def build_category_maps(categories):
    event_cat = {}
    event_order = {}
    for ci, c in enumerate(categories):
        for ei, ev in enumerate(c["events"]):
            event_cat[ev] = c["key"]
            event_order[ev] = ci * 1000 + ei
    return event_cat, event_order


# ---------------------------------------------------------------- configs
class FilterConfig:
    def __init__(self, name, keep=None, delete=None):
        self.name = name
        self.keep = set(keep or ())
        self.delete = set(delete or ())

    def unedited(self, all_events):
        return [e for e in all_events if e not in self.keep and e not in self.delete]


def load_configs(all_events):
    text = read_text(CONFIG_FILE)
    configs = []
    name = None
    keep, delete = set(), set()
    block_mode = "c"
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if name is not None:
                _append_config(configs, name, keep, delete, all_events, block_mode)
            parts = line.split(">", 2)
            if len(parts) == 3 and parts[0] == "":
                block_mode = parts[1].strip() or "c"
                name = parts[2].strip() or "未命名配置"
            else:
                name = None
            keep, delete = set(), set()
            continue
        if line == "<":
            if name is not None:
                _append_config(configs, name, keep, delete, all_events, block_mode)
            name, keep, delete = None, set(), set()
            block_mode = "c"
            continue
        if name is None:
            continue
        if line.startswith("+ ") or line.startswith("- "):
            ev = line[2:].strip()
            if line[0] == "+":
                keep.add(ev)
            else:
                delete.add(ev)
        elif block_mode in ("b", "w"):
            if block_mode == "b":
                delete.add(line)
            else:
                keep.add(line)
    if name is not None:
        _append_config(configs, name, keep, delete, all_events, block_mode)
    return configs


def _append_config(configs, name, keep, delete, all_events, block_mode):
    if block_mode == "w" and not delete:
        delete = {e for e in all_events if e not in keep}
    configs.append(FilterConfig(name, keep, delete))


def save_configs(path, configs):
    lines = []
    for cfg in configs:
        lines.append(f">c>{cfg.name}")
        for ev in sorted(cfg.keep):
            lines.append(f"+ {ev}")
        for ev in sorted(cfg.delete):
            lines.append(f"- {ev}")
        lines.append("<")
    atomic_write(path, ("\r\n".join(lines) + "\r\n").encode("gbk", "replace"))


# ---------------------------------------------------------------- 输出谱面后处理
TRACK_DISAPPEAR_RE = re.compile(r'("trackDisappearAnimation"\s*:\s*")([^"]*)(")')


def apply_track_disappear_animation(path, target):
    """把输出谱面里所有开启了消失动画的 AnimateTrack 统一改成 target。

    采用纯文本替换，不重新解析整个 JSON，能兼容 level.exe 少数情况下产生的
    多余逗号等格式问题，也不会改动文件其它内容的格式。
    原本是 None 或没有 trackDisappearAnimation 字段的事件保持不动。
    返回 (修改数量, 跳过数量, 是否修复了格式问题)。
    """
    raw = open(path, "rb").read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig", "replace")

    # 1) 修复 level.exe 偶尔留下的多余逗号（如 "...,}]" 或 ",,"）
    repaired = text
    for _ in range(3):
        new_repaired = re.sub(r",(\s*[\]\}])", r"\1", repaired)
        new_repaired = re.sub(r",(\s*,)", r"\1", new_repaired)
        if new_repaired == repaired:
            break
        repaired = new_repaired

    changed = 0
    skipped = 0

    def repl(match):
        nonlocal changed, skipped
        value = match.group(2)
        if value == "None":
            skipped += 1
            return match.group(0)
        if value == target:
            skipped += 1
            return match.group(0)
        changed += 1
        return match.group(1) + target + match.group(3)

    matched = len(TRACK_DISAPPEAR_RE.findall(repaired))
    total_anim = len(re.findall(r'"eventType"\s*:\s*"AnimateTrack"', repaired))
    new_text = TRACK_DISAPPEAR_RE.sub(repl, repaired)
    skipped += max(0, total_anim - matched)
    fixed = repaired != text
    if changed or fixed:
        data = new_text.encode("utf-8")
        if has_bom:
            data = b"\xef\xbb\xbf" + data
        with open(path, "wb") as f:
            f.write(data)
    return changed, skipped, fixed


def find_output_file(path, config_name):
    """定位 level.exe 生成的输出文件：<原名>_<配置名>.adofai。"""
    folder = os.path.dirname(os.path.abspath(path))
    stem = os.path.splitext(os.path.basename(path))[0]
    expected = os.path.join(folder, f"{stem}_{config_name}.adofai")
    if os.path.exists(expected):
        return expected
    candidates = []
    try:
        for fn in os.listdir(folder):
            low = fn.lower()
            if low.startswith(stem.lower() + "_") and low.endswith(".adofai"):
                p = os.path.join(folder, fn)
                candidates.append((os.path.getmtime(p), p))
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


# ---------------------------------------------------------------- options
def load_options():
    vals = read_text(OPTIONS_FILE, "on\r\non\r\n").replace("\r", "").split("\n")
    vals = [v.strip() for v in vals if v.strip()]
    translator = vals[0] if len(vals) > 0 else "on"
    autoclose = vals[1] if len(vals) > 1 else "on"
    return translator == "on", autoclose == "on"


def save_options(translator, autoclose):
    text = ("on" if translator else "off") + "\r\n" + ("on" if autoclose else "off") + "\r\n"
    atomic_write(OPTIONS_FILE, text.encode("gbk"))


# ---------------------------------------------------------------- window state
def load_state():
    try:
        return json.loads(read_text(STATE_FILE, "{}") or "{}")
    except Exception:
        return {}


def save_state(state):
    try:
        atomic_write(STATE_FILE, json.dumps(state, ensure_ascii=False, indent=1).encode("utf-8"))
    except Exception:
        pass


GEOM_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


def parse_geometry(geo):
    m = GEOM_RE.match(geo or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))


def screen_size(win):
    return win.winfo_screenwidth(), win.winfo_screenheight()


def clamp_rect(w, h, x, y, win):
    sw, sh = screen_size(win)
    w = max(200, min(w, sw))
    h = max(150, min(h, sh))
    x = max(0, min(x, sw - w))
    y = max(0, min(y, sh - h))
    return w, h, x, y


def center_rect(w, h, win):
    sw, sh = screen_size(win)
    return w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 2)


def apply_main_geometry(root, state, default=(900, 640)):
    entry = state.get("main", "")
    rect = parse_geometry(entry) if entry else None
    if rect:
        w, h, x, y = clamp_rect(*rect, root)
    else:
        w, h = default
        w, h, x, y = center_rect(w, h, root)
    root.geometry(f"{w}x{h}+{x}+{y}")


class ChildWindowMixin:
    def init_child_geometry(self, parent, key, default_size):
        st = self.app.state.get(key, {})
        size = st.get("size") or list(default_size)
        w, h = int(size[0]), int(size[1])
        sw, sh = screen_size(parent)
        w = max(380, min(w, sw))
        h = max(260, min(h, sh))
        self._child_parent = parent
        self._child_key = key
        self._child_size = (w, h)
        self.minsize(380, 260)
        self._state_key = key
        self.bind("<Configure>", self._remember_size)
        self._place_center()
        self.after(80, self._place_center)

    def _place_center(self):
        parent = getattr(self, "_child_parent", None)
        if parent is None or not parent.winfo_exists():
            return
        w, h = self._child_size
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        if pw <= 1 or ph <= 1:
            return
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        w, h, x, y = clamp_rect(w, h, x, y, parent)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _remember_size(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self.winfo_width() > 1 and self.winfo_height() > 1:
            self.app.state[self._state_key] = {
                "size": [self.winfo_width(), self.winfo_height()]
            }


# ---------------------------------------------------------------- icons
class IconManager:
    def __init__(self):
        self.cache = {}
        self.cat_cache = {}

    def get(self, event_name):
        if event_name in self.cache:
            return self.cache[event_name]
        path = os.path.join(ICON_DIR, f"{event_name}.png")
        if not os.path.exists(path):
            path = os.path.join(ICON_DIR, "_placeholder.png")
        photo = self._load(path, 72)
        self.cache[event_name] = photo
        return photo

    def get_category(self, key):
        if key in self.cat_cache:
            return self.cat_cache[key]
        path = os.path.join(CAT_ICON_DIR, f"{key}.png")
        if not os.path.exists(path):
            path = os.path.join(ICON_DIR, "_placeholder.png")
        photo = self._load(path, 18)
        self.cat_cache[key] = photo
        return photo

    @staticmethod
    def _load(path, size):
        try:
            img = Image.open(path).convert("RGBA")
            if size and (img.width > size or img.height > size):
                img.thumbnail((size, size), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None


# ---------------------------------------------------------------- widgets
def accent_button(parent, text, command, big=False, **kw):
    return tk.Button(parent, text=text, command=command, font=FONT_BOLD,
                     bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
                     activeforeground="white", disabledforeground="#c7d4e2",
                     relief="flat", bd=0, padx=18 if big else 12,
                     pady=8 if big else 5, cursor="hand2", **kw)


def danger_button(parent, text, command, **kw):
    return tk.Button(parent, text=text, command=command, font=FONT,
                     bg=CARD, fg=DANGER, activebackground="#fbeaea",
                     activeforeground=DANGER, relief="flat", bd=0,
                     padx=12, pady=5, cursor="hand2",
                     highlightbackground=BORDER, highlightthickness=1, **kw)


# ---------------------------------------------------------------- categorized panel
class CategorizedPanel(tk.Frame):
    """带分类按钮的事件图标面板。

    vertical=True   ：上下滑动的网格（留下/删除）
    vertical=False  ：单行左右滑动（未编辑）
    """

    def __init__(self, master, app, title, accent=ACCENT, vertical=True,
                 draggable=False, on_press=None, on_double=None,
                 filter_mode=False, header_buttons=(), hint=False,
                 bg=CARD, min_height=140):
        super().__init__(master, bg=bg, highlightbackground=BORDER,
                         highlightthickness=1, bd=0)
        self.app = app
        self.accent = accent
        self.vertical = vertical
        self.draggable = draggable
        self.on_press = on_press
        self.on_double = on_double
        self.filter_mode = filter_mode
        self._all_events = []
        self._events = []
        self._tile_widgets = []          # list of (frame, img_lbl, txt_lbl, event)
        self._after_id = None
        self._last_layout_key = None
        self._active_cat = (app.categories[0]["key"]
                            if filter_mode and app.categories else None)
        self._cat_buttons = {}
        self._hint_after = None
        self._last_press = None
        self._title_base = title

        # header
        header = tk.Frame(self, bg=bg)
        header.pack(fill="x", padx=10, pady=(7, 3))
        self.dot = tk.Frame(header, bg=accent, width=8, height=8)
        self.dot.pack(side="left", padx=(0, 6))
        self.title_label = tk.Label(header, text=title, font=FONT_BOLD,
                                    bg=bg, fg=TEXT, anchor="w")
        self.title_label.pack(side="left")
        self.count_label = tk.Label(header, text="0", font=FONT_BOLD,
                                    bg=bg, fg=accent)
        self.count_label.pack(side="left", padx=(6, 0))
        self.hint_label = None
        if hint:
            self.hint_label = tk.Label(header, text="", font=FONT_SMALL,
                                       bg=bg, fg=MUTED, anchor="w")
        for text, cmd in header_buttons:
            btn = tk.Button(header, text=text, command=cmd, font=FONT_SMALL,
                            bg=bg, fg=ACCENT, activebackground=bg,
                            activeforeground=ACCENT_HOVER, relief="flat",
                            bd=0, padx=6, pady=0, cursor="hand2")
            btn.pack(side="right", padx=(4, 0))
        if self.hint_label is not None:
            self.hint_label.pack(side="left", fill="x", expand=True, padx=(10, 0))

        # category bar
        self.catbar = tk.Frame(self, bg=bg)
        self.catbar.pack(fill="x", padx=8, pady=(0, 4))
        for c in app.categories:
            btn = self._make_cat_button(c)
            btn.pack(side="left", padx=(0, 3))
            self._cat_buttons[c["key"]] = btn

        # body
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(self.body, bg=bg, highlightthickness=0,
                                height=TILE_H + 8)
        if vertical:
            self.canvas.pack(side="left", fill="both", expand=True)
            self.vscroll = ttk.Scrollbar(self.body, orient="vertical",
                                         command=self.canvas.yview)
            self.vscroll.pack(side="right", fill="y")
            self.canvas.configure(yscrollcommand=self.vscroll.set)
        else:
            self.canvas.pack(side="top", fill="both", expand=True)
            self.hscroll = ttk.Scrollbar(self.body, orient="horizontal",
                                         command=self.canvas.xview)
            self.hscroll.pack(side="bottom", fill="x")
            self.canvas.configure(xscrollcommand=self.hscroll.set)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)
        self.bind("<Enter>", lambda e: self._bind_wheel(True))
        self.bind("<Leave>", lambda e: self._bind_wheel(False))

    # ---- category buttons
    def _make_cat_button(self, cat):
        key = cat["key"]
        frame = tk.Frame(self.catbar, bg=CARD, highlightbackground=BORDER,
                         highlightthickness=1, bd=0, cursor="hand2")
        photo = self.app.icons.get_category(key)
        img = tk.Label(frame, image=photo, bg=CARD)
        img.image = photo
        img.pack(side="left", padx=(3, 1), pady=2)
        txt = tk.Label(frame, text=cat["zh"], font=FONT_TINY, bg=CARD, fg=TEXT)
        txt.pack(side="left", padx=(0, 3), pady=2)
        for w in (frame, img, txt):
            w.bind("<Button-1>", lambda e, k=key: self.toggle_category(k))
        return frame

    def _set_cat_button_state(self, key, state):
        frame = self._cat_buttons.get(key)
        if frame is None:
            return
        if state == "empty":
            frame.configure(highlightbackground=DANGER, highlightthickness=2)
        elif state == "active":
            frame.configure(highlightbackground=ACCENT, highlightthickness=2)
        else:
            frame.configure(highlightbackground=BORDER, highlightthickness=1)

    # ---- scrolling
    def _bind_wheel(self, on):
        if on:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        else:
            self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        try:
            if self.vertical:
                self.canvas.yview_scroll(int(-event.delta / 120), "units")
            else:
                self.canvas.xview_scroll(int(-event.delta / 120), "units")
        except Exception:
            pass

    def _on_inner_config(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_config(self, event=None):
        if self.vertical:
            self.canvas.itemconfigure(self._win, width=self.canvas.winfo_width())
        self._relayout()

    # ---- data
    def set_events(self, events):
        self._all_events = list(dict.fromkeys(events))
        self._all_events.sort(key=lambda e: (self.app.event_order.get(e, 99999), e))
        self._events = self._visible_events()
        self._last_layout_key = None
        self._relayout()
        self._update_alert()

    def _visible_events(self):
        if self.filter_mode and self._active_cat:
            return [e for e in self._all_events
                    if self.app.event_cat.get(e) == self._active_cat]
        return list(self._all_events)

    def events(self):
        return list(self._all_events)

    def visible_events(self):
        return list(self._events)

    def set_title(self, title):
        self._title_base = title
        self.title_label.configure(text=title)

    def set_hint(self, text, clear_after=8000):
        if self.hint_label is None:
            return
        self.hint_label.configure(text=text)
        if self._hint_after:
            self.after_cancel(self._hint_after)
        if clear_after:
            self._hint_after = self.after(clear_after, lambda: self.hint_label.configure(text=""))

    def _update_alert(self):
        counts = {}
        for ev in self._all_events:
            cat = self.app.event_cat.get(ev, "")
            counts[cat] = counts.get(cat, 0) + 1
        for c in self.app.categories:
            key = c["key"]
            self._set_cat_button_state(
                key,
                "empty" if counts.get(key, 0) == 0 else
                ("active" if self._active_cat == key else "normal"))

    # ---- layout
    def _relayout(self):
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(20, self._do_relayout)

    def _do_relayout(self):
        self._after_id = None
        self._events = self._visible_events()
        width = max(1, self.canvas.winfo_width())
        if self.vertical:
            cols = max(1, (width - 10) // TILE_W)
            key = ("v", cols, tuple(self._events))
        else:
            cols = len(self._events) or 1
            key = ("h", tuple(self._events))
        if key == self._last_layout_key and self._tile_widgets:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            return
        self._last_layout_key = key
        for item in self._tile_widgets:
            item[0].destroy()
        self._tile_widgets = []
        for i, ev in enumerate(self._events):
            if self.vertical:
                r, c = divmod(i, cols)
            else:
                r, c = 0, i
            frame, img_lbl, txt_lbl = self._make_tile(ev)
            frame.grid(row=r, column=c, padx=4, pady=4)
            self._tile_widgets.append((frame, img_lbl, txt_lbl, ev))
        self.count_label.configure(text=str(len(self._all_events)))
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self._active_cat and not self.filter_mode:
            self._apply_highlight(self._active_cat)
        self._update_alert()

    def _make_tile(self, ev):
        label = self.app.event_label(ev) if self.app.translator else ev
        frame = tk.Frame(self.inner, bg=CARD, width=TILE_W - 8, height=TILE_H - 8,
                         highlightbackground=BORDER, highlightthickness=1, bd=0)
        frame.pack_propagate(False)
        frame.grid_propagate(False)
        photo = self.app.icons.get(ev)
        img_lbl = tk.Label(frame, image=photo, bg=CARD)
        img_lbl.image = photo
        img_lbl.pack(pady=(7, 0))
        txt_lbl = tk.Label(frame, text=label, font=FONT_SMALL, bg=CARD, fg=TEXT,
                           wraplength=TILE_W - 22, justify="center")
        txt_lbl.pack(pady=(3, 4))
        widgets = (frame, img_lbl, txt_lbl)
        if self.draggable and self.on_press is not None:
            for w in widgets:
                w.bind("<ButtonPress-1>", lambda e, ev=ev: self._tile_press(ev, e))
        for w in widgets:
            w.bind("<Enter>", lambda e, f=frame: f.configure(highlightbackground=self.accent))
            w.bind("<Leave>", lambda e, f=frame, ev=ev: self._tile_leave(f, ev))
        return frame, img_lbl, txt_lbl

    def _tile_leave(self, frame, ev):
        if self._active_cat and self.app.event_cat.get(ev) == self._active_cat:
            frame.configure(highlightbackground=ACCENT, bg=HILITE_BG)
        else:
            frame.configure(highlightbackground=BORDER)

    def _tile_press(self, ev, event):
        now = time.time()
        if (self._last_press is not None and self._last_press[0] == ev
                and now - self._last_press[1] < 0.5):
            self._last_press = None
            if self.on_double is not None:
                self.on_double(ev)
            return
        self._last_press = (ev, now)
        if self.on_press is not None:
            self.on_press(ev, self, event)

    def highlight(self, on):
        self.configure(highlightbackground=self.accent if on else BORDER,
                       highlightthickness=2 if on else 1)

    # ---- category highlight / locate
    def toggle_category(self, key):
        if self.filter_mode:
            # 过滤模式：始终选中一个分类，只显示该分类的图标
            if self._active_cat == key:
                return
            self._active_cat = key
            self._last_layout_key = None
            self._relayout()
            self._update_alert()
            self.after(30, lambda: self.canvas.xview_moveto(0))
            return
        if self._active_cat == key:
            self._active_cat = None
            self._apply_highlight(None)
            self._update_alert()
            return
        self._active_cat = key
        self._apply_highlight(key)
        self._update_alert()
        self._scroll_to_category(key)

    def _apply_highlight(self, key):
        for frame, img_lbl, txt_lbl, ev in self._tile_widgets:
            hit = key is not None and self.app.event_cat.get(ev) == key
            if hit:
                frame.configure(highlightbackground=ACCENT, bg=HILITE_BG)
                img_lbl.configure(bg=HILITE_BG)
                txt_lbl.configure(bg=HILITE_BG, fg=ACCENT)
            else:
                frame.configure(highlightbackground=BORDER, bg=CARD)
                img_lbl.configure(bg=CARD)
                txt_lbl.configure(bg=CARD, fg=TEXT)

    def _scroll_to_category(self, key):
        """该类图标不在可视区域时再滚动；可视就不动。"""
        targets = [it for it in self._tile_widgets if self.app.event_cat.get(it[3]) == key]
        if not targets:
            return
        first = targets[0][0]
        self.canvas.update_idletasks()
        if self.vertical:
            inner_h = max(1, self.inner.winfo_height())
            view_h = max(1, self.canvas.winfo_height())
            top_frac, bottom_frac = self.canvas.yview()
            vis_top = top_frac * inner_h
            vis_bottom = bottom_frac * inner_h
            ty = first.winfo_y()
            if vis_top - 1 <= ty <= vis_bottom - TILE_H:
                return
            total = max(inner_h, view_h)
            self.canvas.yview_moveto(max(0.0, min(1.0, ty / total)))
        else:
            inner_w = max(1, self.inner.winfo_width())
            view_w = max(1, self.canvas.winfo_width())
            left_frac, right_frac = self.canvas.xview()
            vis_left = left_frac * inner_w
            vis_right = right_frac * inner_w
            tx = first.winfo_x()
            if vis_left - 1 <= tx <= vis_right - TILE_W:
                return
            total = max(inner_w, view_w)
            self.canvas.xview_moveto(max(0.0, min(1.0, tx / total)))


# ---------------------------------------------------------------- editor window
class EditorWindow(tk.Toplevel, ChildWindowMixin):
    def __init__(self, app, config, on_saved):
        super().__init__(app.root)
        self.app = app
        self.on_saved = on_saved
        self.config = config
        self.is_new = config.name == ""
        self.keep = set(config.keep)
        self.delete = set(config.delete)
        self._drag = None
        self._float = None

        self.title("新建过滤器配置" if self.is_new else f"编辑过滤器配置 - {config.name}")
        self.configure(bg=BG)
        self.transient(app.root)
        self.init_child_geometry(app.root, "editor_window", (1280, 900))
        self.minsize(980, 660)

        self._build()
        self.refresh()

    def _build(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=14, pady=12)

        top = tk.Frame(outer, bg=BG)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="配置名称：", font=FONT, bg=BG, fg=TEXT).pack(side="left")
        self.name_var = tk.StringVar(value=self.config.name if not self.is_new else "")
        self.name_entry = ttk.Entry(top, textvariable=self.name_var, font=FONT, width=26)
        self.name_entry.pack(side="left")
        self.name_entry.focus_set()
        tk.Label(top, text="拖动图标到「留下」或「删除」；双击已归档图标可挪回未编辑；未编辑的事件默认保留。",
                 font=FONT_SMALL, bg=BG, fg=MUTED).pack(side="left", padx=14)

        grid = tk.Frame(outer, bg=BG)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")
        grid.rowconfigure(0, weight=1)

        self.keep_panel = CategorizedPanel(
            grid, self.app, "留下", accent=GREEN, vertical=True, draggable=True,
            on_press=self._on_tile_press, on_double=lambda ev: self.return_event(ev, "留下"),
            header_buttons=(("全部挪回", lambda: self.return_all("留下")),))
        self.keep_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))

        self.delete_panel = CategorizedPanel(
            grid, self.app, "删除", accent=DANGER, vertical=True, draggable=True,
            on_press=self._on_tile_press, on_double=lambda ev: self.return_event(ev, "删除"),
            header_buttons=(("全部挪回", lambda: self.return_all("删除")),))
        self.delete_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))

        self.other_panel = CategorizedPanel(
            grid, self.app, "未编辑", accent=ACCENT, vertical=False, draggable=True,
            on_press=self._on_tile_press, filter_mode=True, hint=True)
        self.other_panel.grid(row=1, column=0, columnspan=2, sticky="nsew")

        footer = tk.Frame(outer, bg=BG)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="手动添加事件…", command=self._manual_add).pack(side="left")
        ttk.Button(footer, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        accent_button(footer, "保存配置", self.save).pack(side="right")

    # ---- data
    def _all_events(self):
        known = [e for e, _z in self.app.events]
        extra = [e for e in sorted(self.keep | self.delete) if e not in known]
        return known + extra

    def refresh(self):
        all_ev = self._all_events()
        unedited = [e for e in all_ev if e not in self.keep and e not in self.delete]
        self.keep_panel.set_title("留下")
        self.delete_panel.set_title("删除")
        self.other_panel.set_title("未编辑")
        self.keep_panel.set_events(sorted(self.keep))
        self.delete_panel.set_events(sorted(self.delete))
        self.other_panel.set_events(unedited)

    def move_event(self, ev, target):
        if target is self.keep_panel:
            self.keep.add(ev)
            self.delete.discard(ev)
        elif target is self.delete_panel:
            self.delete.add(ev)
            self.keep.discard(ev)
        else:
            self.keep.discard(ev)
            self.delete.discard(ev)
        self.refresh()

    def return_event(self, ev, source_name):
        self.keep.discard(ev)
        self.delete.discard(ev)
        self.refresh()
        self.other_panel.set_hint(f"{self.app.event_label(ev)} 从「{source_name}」挪回")

    def return_all(self, source_name):
        if source_name == "留下":
            n = len(self.keep)
            self.keep.clear()
        else:
            n = len(self.delete)
            self.delete.clear()
        self.refresh()
        self.other_panel.set_hint(f"已全部从「{source_name}」挪回（{n} 个）")

    # ---- drag and drop
    def _on_tile_press(self, ev, panel, event):
        self._drag = {"ev": ev, "from": panel}
        self._float = tk.Toplevel(self)
        self._float.overrideredirect(True)
        self._float.attributes("-topmost", True)
        frame = tk.Frame(self._float, bg=CARD, highlightbackground=ACCENT,
                         highlightthickness=1)
        frame.pack()
        photo = self.app.icons.get(ev)
        tk.Label(frame, image=photo, bg=CARD).pack(padx=8, pady=(6, 0))
        tk.Label(frame, text=self.app.event_label(ev) if self.app.translator else ev,
                 font=FONT_SMALL, bg=CARD, fg=TEXT).pack(padx=8, pady=(0, 6))
        self._float.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
        self.bind_all("<B1-Motion>", self._on_drag_motion)
        self.bind_all("<ButtonRelease-1>", self._on_drag_release)

    def _on_drag_motion(self, event):
        if self._float is not None:
            try:
                self._float.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
            except Exception:
                pass
        target = self._panel_at(event.x_root, event.y_root)
        for p in (self.keep_panel, self.delete_panel, self.other_panel):
            p.highlight(p is target)

    def _panel_at(self, x, y):
        for p in (self.keep_panel, self.delete_panel, self.other_panel):
            px, py = p.winfo_rootx(), p.winfo_rooty()
            pw, ph = p.winfo_width(), p.winfo_height()
            if px <= x <= px + pw and py <= y <= py + ph:
                return p
        return None

    def _on_drag_release(self, event):
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")
        target = self._panel_at(event.x_root, event.y_root)
        drag = self._drag
        if self._float is not None:
            self._float.destroy()
            self._float = None
        for p in (self.keep_panel, self.delete_panel, self.other_panel):
            p.highlight(False)
        if drag and target is not None and target is not drag["from"]:
            self.move_event(drag["ev"], target)
        self._drag = None

    def _manual_add(self):
        name = simpledialog.askstring("手动添加事件", "输入事件英文名（如新版本事件）：", parent=self)
        if not name:
            return
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            messagebox.showerror("错误", "事件名只能包含字母、数字和下划线。", parent=self)
            return
        if name in self.keep or name in self.delete:
            messagebox.showinfo("提示", "该事件已经在列表里了。", parent=self)
            return
        if name not in self.app.extra_events:
            self.app.extra_events.add(name)
            self.app.categories = load_categories(self._all_events())
            self.app.event_cat, self.app.event_order = build_category_maps(self.app.categories)
        self.refresh()

    # ---- save
    def save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("错误", "请填写配置名称。", parent=self)
            return
        if "/" in name or "\\" in name:
            messagebox.showerror("错误", "配置名称不能包含 / 或 \\。", parent=self)
            return
        for cfg in self.app.configs:
            if cfg is not self.config and cfg.name == name:
                messagebox.showerror("错误", "已经存在同名配置！", parent=self)
                return
        self.config.name = name
        self.config.keep = set(self.keep)
        self.config.delete = set(self.delete)
        if self.config not in self.app.configs:
            self.app.configs.append(self.config)
        self.app.save_configs()
        if self.on_saved:
            self.on_saved(self.config)
        self.destroy()


# ---------------------------------------------------------------- config manager
class ConfigManagerWindow(tk.Toplevel, ChildWindowMixin):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("过滤器配置")
        self.configure(bg=BG)
        self.transient(app.root)
        self.init_child_geometry(app.root, "config_window", (1400, 900))
        self.minsize(1100, 680)
        self._build()
        self.refresh_list()
        self.after(100, self._set_sash)

    def _set_sash(self):
        try:
            self.paned.sashpos(0, 340)
        except Exception:
            pass

    def _build(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=14, pady=12)

        self.paned = ttk.Panedwindow(outer, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        left = tk.Frame(self.paned, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.paned.add(left, weight=1)
        tk.Label(left, text="已保存的配置", font=FONT_BOLD, bg=CARD, fg=TEXT,
                 anchor="w").pack(fill="x", padx=12, pady=(10, 6))
        list_wrap = tk.Frame(left, bg=CARD)
        list_wrap.pack(fill="both", expand=True, padx=10)
        self.listbox = tk.Listbox(list_wrap, font=FONT, bg="#fbfcfe", fg=TEXT,
                                  selectbackground=ACCENT, selectforeground="white",
                                  activestyle="none", highlightthickness=0, bd=0,
                                  exportselection=False)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Double-Button-1>", lambda e: self.edit_selected())

        buttons = tk.Frame(left, bg=CARD)
        buttons.pack(fill="x", padx=10, pady=10)
        buttons.columnconfigure(0, weight=1, uniform="btn")
        buttons.columnconfigure(1, weight=1, uniform="btn")
        accent_button(buttons, "新建配置", self.new_config).grid(
            row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        ttk.Button(buttons, text="编辑配置", command=self.edit_selected).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))
        ttk.Button(buttons, text="重命名", command=self.rename_selected).grid(
            row=1, column=0, sticky="ew", padx=(0, 4))
        danger_button(buttons, "删除选中项", self.delete_selected).grid(
            row=1, column=1, sticky="ew", padx=(4, 0))

        right = tk.Frame(self.paned, bg=BG)
        self.paned.add(right, weight=3)

        self.preview_title = tk.Label(right, text="", font=FONT_BOLD, bg=BG, fg=TEXT, anchor="w")
        self.preview_title.pack(fill="x", padx=2)
        self.preview_summary = tk.Label(right, text="", font=FONT_SMALL, bg=BG, fg=MUTED, anchor="w")
        self.preview_summary.pack(fill="x", padx=2, pady=(0, 6))

        self.preview = tk.Frame(right, bg=BG)
        self.preview.pack(fill="both", expand=True)
        self.preview.columnconfigure(0, weight=1, uniform="pcol")
        self.preview.columnconfigure(1, weight=1, uniform="pcol")
        self.preview.rowconfigure(0, weight=1)

        self.keep_panel = CategorizedPanel(self.preview, self.app, "留下的事件 · 0",
                                           accent=GREEN, vertical=True, min_height=100)
        self.keep_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        self.delete_panel = CategorizedPanel(self.preview, self.app, "删除的事件 · 0",
                                             accent=DANGER, vertical=True, min_height=100)
        self.delete_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        self.other_panel = CategorizedPanel(self.preview, self.app, "未编辑的事件 · 0",
                                            accent=ACCENT, vertical=False, filter_mode=True,
                                            hint=True, min_height=100)
        self.other_panel.grid(row=1, column=0, columnspan=2, sticky="nsew")

        bottom = tk.Frame(outer, bg=BG)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="关闭", command=self.destroy).pack(side="right")

    def refresh_list(self, select=None):
        self.listbox.delete(0, "end")
        for cfg in self.app.configs:
            self.listbox.insert("end", cfg.name)
        if not self.app.configs:
            self._show_preview(None)
            return
        idx = 0
        if select is not None and select in self.app.configs:
            idx = self.app.configs.index(select)
        idx = max(0, min(idx, len(self.app.configs) - 1))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)
        self._show_preview(self.app.configs[idx])

    def _on_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.app.configs):
            self._show_preview(self.app.configs[idx])

    def selected_index(self):
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _show_preview(self, cfg):
        if cfg is None:
            self.preview_title.configure(text="没有配置")
            self.preview_summary.configure(text="点击「新建配置」创建一个过滤器配置。")
            self.keep_panel.set_events([])
            self.delete_panel.set_events([])
            self.other_panel.set_events([])
            return
        self.preview_title.configure(text=cfg.name)
        known = {x for x, _z in self.app.events}
        all_ev = [e for e, _z in self.app.events] + sorted(
            e for e in (cfg.keep | cfg.delete) if e not in known)
        unedited = cfg.unedited(all_ev)
        self.preview_summary.configure(
            text=f"共 {len(all_ev)} 个事件：留下 {len(cfg.keep)} · 删除 {len(cfg.delete)} · "
                 f"未编辑 {len(unedited)}（未编辑默认保留）")
        self.keep_panel.set_title("留下的事件")
        self.delete_panel.set_title("删除的事件")
        self.other_panel.set_title("未编辑的事件")
        self.keep_panel.set_events(sorted(cfg.keep))
        self.delete_panel.set_events(sorted(cfg.delete))
        self.other_panel.set_events(unedited)

    def selected_config(self):
        idx = self.selected_index()
        if idx is None or idx >= len(self.app.configs):
            return None
        return self.app.configs[idx]

    def new_config(self):
        cfg = FilterConfig("")
        EditorWindow(self.app, cfg, on_saved=self._config_saved)

    def edit_selected(self):
        cfg = self.selected_config()
        if cfg is None:
            messagebox.showinfo("提示", "请先选择一个配置。", parent=self)
            return
        EditorWindow(self.app, cfg, on_saved=self._config_saved)

    def rename_selected(self):
        cfg = self.selected_config()
        if cfg is None:
            messagebox.showinfo("提示", "请先选择一个配置。", parent=self)
            return
        name = simpledialog.askstring("重命名配置", "新的配置名称：", initialvalue=cfg.name, parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if any(c is not cfg and c.name == name for c in self.app.configs):
            messagebox.showerror("错误", "已经存在同名配置！", parent=self)
            return
        cfg.name = name
        self.app.save_configs()
        self.refresh_list(select=cfg)
        self.app.refresh_config_combo()

    def delete_selected(self):
        cfg = self.selected_config()
        if cfg is None:
            messagebox.showinfo("提示", "请先选择一个配置。", parent=self)
            return
        if len(self.app.configs) <= 1:
            messagebox.showerror("错误", "无法删除！您必须保留至少一项配置！", parent=self)
            return
        if not messagebox.askokcancel("确认", "删除后无法撤回，确定要删除吗？", parent=self):
            return
        self.app.configs.remove(cfg)
        self.app.save_configs()
        self.refresh_list()
        self.app.refresh_config_combo()

    def _config_saved(self, cfg):
        self.app.save_configs()
        self.refresh_list(select=cfg)
        self.app.refresh_config_combo()


# ---------------------------------------------------------------- about window
class AboutWindow(tk.Toplevel, ChildWindowMixin):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("关于 " + APP_NAME)
        self.configure(bg=BG)
        self.transient(app.root)
        self.init_child_geometry(app.root, "about_window", (640, 560))
        self.minsize(560, 500)
        self.resizable(True, True)
        self._build()

    def _build(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=BG)
        title_box.pack(side="left")
        tk.Label(title_box, text=APP_NAME, font=("Microsoft YaHei UI", 20, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(title_box, text=f"版本 v{APP_VERSION}", font=FONT_SUB,
                 bg=BG, fg=MUTED).pack(anchor="w")
        tk.Label(header, text=f"作者：{DEV_NAME}", font=FONT, bg=BG, fg=MUTED).pack(side="right", pady=(8, 0))

        card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, pady=(14, 12))
        wrap = tk.Frame(card, bg=CARD)
        wrap.pack(fill="both", expand=True, padx=18, pady=16)

        lines = [
            ("软件简介", None),
            ("用于清理《冰与火之舞》(A Dance of Fire and Ice) 谱面中的装饰、滤镜、"
             "粒子等视觉特效事件，降低游玩卡顿，同时保留玩法判定与输入事件。", "body"),
            ("主要功能", None),
            ("· 一键去除装饰 / 滤镜 / 粒子 / 屏幕特效，支持自定义过滤配置", "body"),
            ("· 事件图标化选择，分类与游戏编辑器一致，支持拖拽、双击挪回", "body"),
            ("· 支持游戏 3.4 版本新增事件（预设高级滤镜、粒子、输入事件等）", "body"),
            ("· 可统一调整「设置轨道动画」的轨道消失动画", "body"),
            ("说明", None),
            ("本工具为非官方第三方工具，与 7th Beat Games 无关联。事件图标与名称来源于游戏，"
             "版权归原权利人所有。处理前建议备份原谱面文件。", "body"),
            ("配置文件", None),
            ("events.txt（事件列表）、levelsset.txt（过滤器配置）、options.txt（程序设置）。", "body"),
        ]
        for text, kind in lines:
            if kind is None:
                tk.Label(wrap, text=text, font=FONT_BOLD, bg=CARD, fg=TEXT,
                         anchor="w").pack(fill="x", pady=(6, 2))
            else:
                tk.Label(wrap, text=text, font=FONT_SMALL, bg=CARD, fg=TEXT,
                         anchor="w", justify="left", wraplength=560).pack(fill="x")

        bottom = tk.Frame(outer, bg=BG)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="关闭", command=self.destroy).pack(side="right")


# ---------------------------------------------------------------- misc window
class MiscWindow(tk.Toplevel, ChildWindowMixin):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("杂项设置")
        self.configure(bg=BG)
        self.transient(app.root)
        self.init_child_geometry(app.root, "misc_window", (460, 300))
        self.minsize(400, 240)
        self._build()

    def _build(self):
        outer = tk.Frame(self, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(outer, text="界面与运行", font=FONT_BOLD, bg=CARD, fg=TEXT,
                 anchor="w").pack(fill="x", padx=14, pady=(12, 2))

        self.trans_var = tk.BooleanVar(value=self.app.translator)
        self.close_var = tk.BooleanVar(value=self.app.autoclose)

        tk.Checkbutton(outer, text="显示中文事件名", variable=self.trans_var,
                       font=FONT, bg=CARD, fg=TEXT, anchor="w",
                       activebackground=CARD, selectcolor="white",
                       command=self._on_translate).pack(fill="x", padx=14, pady=(8, 4))
        tk.Checkbutton(outer, text="运行结束后自动关闭程序", variable=self.close_var,
                       font=FONT, bg=CARD, fg=TEXT, anchor="w",
                       activebackground=CARD, selectcolor="white",
                       command=self._on_autoclose).pack(fill="x", padx=14, pady=(4, 8))

        tk.Label(outer, text="提示：新版本事件可在「编辑配置」里手动输入英文名添加。",
                 font=FONT_SMALL, bg=CARD, fg=MUTED, anchor="w", wraplength=400,
                 justify="left").pack(fill="x", padx=14, pady=(0, 12))

        ttk.Button(outer, text="关闭", command=self.destroy).pack(side="right", padx=14, pady=(0, 12))

    def _on_translate(self):
        self.app.translator = self.trans_var.get()
        save_options(self.app.translator, self.app.autoclose)
        self.app.on_options_changed()

    def _on_autoclose(self):
        self.app.autoclose = self.close_var.get()
        save_options(self.app.translator, self.app.autoclose)


# ---------------------------------------------------------------- main app
class App:
    def __init__(self, root):
        self.root = root
        self.icons = IconManager()
        self.state = load_state()
        self.events = load_events()
        self.extra_events = set()
        self.translator, self.autoclose = load_options()
        event_names = [e for e, _z in self.events]
        self.categories = load_categories(event_names)
        self.event_cat, self.event_order = build_category_maps(self.categories)
        self.configs = load_configs(event_names)
        self.output_queue = queue.Queue()
        self.running = False
        self.config_manager = None
        self.misc_window = None
        self.about_window = None
        self.last_output_dir = None

        root.title(TITLE)
        root.configure(bg=BG)
        try:
            ico = os.path.join(RESOURCE_DIR, "app.ico")
            if os.path.exists(ico):
                root.iconbitmap(default=ico)
        except Exception:
            pass
        self._setup_style()
        apply_main_geometry(root, self.state)
        root.minsize(800, 540)
        self._build()
        self._poll_output()
        root.protocol("WM_DELETE_WINDOW", self.close_app)

    def _setup_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except Exception:
            style.theme_use("clam")
        style.configure(".", font=FONT)
        style.configure("TButton", padding=(10, 5), font=FONT)
        style.configure("TEntry", padding=4)

    def event_label(self, ev):
        for e, zh in self.events:
            if e == ev:
                return zh
        return ev

    def save_configs(self):
        save_configs(CONFIG_FILE, self.configs)

    # ---- main layout
    def _build(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=14)

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        title_box = tk.Frame(head, bg=BG)
        title_box.pack(side="left")
        tk.Label(title_box, text=APP_NAME, font=FONT_TITLE, bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(title_box, text=f"版本 v{APP_VERSION}  ·  支持游戏 3.4+ 事件  ·  {DEV_NAME}",
                 font=FONT_SUB, bg=BG, fg=MUTED).pack(anchor="w")

        card1 = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card1.pack(fill="x", pady=(14, 8))
        row1 = tk.Frame(card1, bg=CARD)
        row1.pack(fill="x", padx=14, pady=12)
        tk.Label(row1, text="谱面文件", font=FONT_BOLD, bg=CARD, fg=TEXT).pack(side="left")
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(row1, textvariable=self.path_var, font=FONT)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=12)
        ttk.Button(row1, text="浏览…", command=self.browse_file).pack(side="left")

        card2 = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card2.pack(fill="x", pady=(0, 10))
        row2 = tk.Frame(card2, bg=CARD)
        row2.pack(fill="x", padx=14, pady=12)
        tk.Label(row2, text="过滤器配置", font=FONT_BOLD, bg=CARD, fg=TEXT).pack(side="left")
        self.config_var = tk.StringVar()
        self.config_combo = ttk.Combobox(row2, textvariable=self.config_var,
                                         state="readonly", font=FONT, width=32)
        self.config_combo.pack(side="left", padx=12)
        self.config_combo.bind("<<ComboboxSelected>>",
                               lambda e: self.update_track_option_state())
        ttk.Button(row2, text="管理配置…", command=self.open_config_manager).pack(side="left")
        ttk.Button(row2, text="设置…", command=self.open_misc).pack(side="left", padx=8)
        ttk.Button(row2, text="关于", command=self.open_about).pack(side="left")

        action = tk.Frame(outer, bg=BG)
        action.pack(fill="x", pady=(0, 10))
        self.start_btn = accent_button(action, "开始处理", self.start, big=True)
        self.start_btn.pack(side="left")

        tk.Label(action, text="轨道消失动画：", font=FONT, bg=BG,
                 fg=TEXT).pack(side="left", padx=(16, 4))
        self.track_anim_var = tk.StringVar(value=TRACK_ANIM_MODES[0])
        self.track_combo = ttk.Combobox(action, textvariable=self.track_anim_var,
                                        values=TRACK_ANIM_MODES, state="disabled",
                                        font=FONT, width=7)
        self.track_combo.pack(side="left")
        self.track_help = tk.Canvas(action, width=20, height=20, bg=BG,
                                    highlightthickness=0, cursor="hand2")
        self.track_help.create_oval(2, 2, 18, 18, fill=ACCENT, outline="")
        self.track_help.create_text(10, 10, text="?", fill="white",
                                    font=("Microsoft YaHei UI", 10, "bold"))
        self.track_help.pack(side="left", padx=(6, 0))
        Tooltip(self.track_help, TRACK_HELP_TEXT)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(action, textvariable=self.status_var, font=FONT, bg=BG,
                 fg=MUTED).pack(side="left", padx=14)
        self.open_output_btn = ttk.Button(action, text="打开输出目录",
                                          command=self.open_output_dir)
        self.open_output_btn.pack(side="right")

        out_card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        out_card.pack(fill="both", expand=True)
        wrap = tk.Frame(out_card, bg=CONSOLE_BG)
        wrap.pack(fill="both", expand=True, padx=1, pady=1)
        self.output = tk.Text(wrap, height=10, wrap="word", bg=CONSOLE_BG, fg=CONSOLE_FG,
                              insertbackground="white", font=("Consolas", 10),
                              relief="flat", bd=0)
        self.output.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        out_sb = ttk.Scrollbar(wrap, orient="vertical", command=self.output.yview)
        out_sb.pack(side="right", fill="y")
        self.output.configure(yscrollcommand=out_sb.set)
        self.output.configure(state="disabled")

        self.refresh_config_combo()

    def refresh_config_combo(self, select_index=None):
        names = [c.name for c in self.configs]
        self.config_combo.configure(values=names)
        if not names:
            self.config_var.set("")
            self.update_track_option_state()
            return
        if select_index is None:
            idx = 0
            cur = self.config_var.get()
            if cur in names:
                idx = names.index(cur)
        else:
            idx = max(0, min(select_index, len(names) - 1))
        self.config_combo.current(idx)
        self.update_track_option_state()

    # ---- 轨道消失动画选项
    def selected_config(self):
        if not self.configs:
            return None
        idx = self.config_combo.current()
        if 0 <= idx < len(self.configs):
            return self.configs[idx]
        return self.configs[0]

    def track_option_enabled(self):
        cfg = self.selected_config()
        return bool(cfg is not None and "AnimateTrack" in cfg.keep)

    def update_track_option_state(self):
        enabled = self.track_option_enabled()
        if enabled:
            self.track_combo.configure(state="readonly")
        else:
            self.track_anim_var.set(TRACK_ANIM_MODES[0])
            self.track_combo.configure(state="disabled")
        try:
            self.track_help.configure(bg=BG)
        except Exception:
            pass

    # ---- events
    def browse_file(self):
        path = filedialog.askopenfilename(
            title="选择谱面文件",
            filetypes=[("ADOFAI 谱面", "*.adofai"), ("所有文件", "*.*")],
            parent=self.root)
        if path:
            self.path_var.set(path)

    def open_config_manager(self):
        if self.config_manager is not None and self.config_manager.winfo_exists():
            self.config_manager.lift()
            self.config_manager.focus_force()
            return
        self.config_manager = ConfigManagerWindow(self)

    def open_about(self):
        if self.about_window is not None and self.about_window.winfo_exists():
            self.about_window.lift()
            self.about_window.focus_force()
            return
        self.about_window = AboutWindow(self)

    def open_misc(self):
        if self.misc_window is not None and self.misc_window.winfo_exists():
            self.misc_window.lift()
            self.misc_window.focus_force()
            return
        self.misc_window = MiscWindow(self)

    def on_options_changed(self):
        if self.config_manager is not None and self.config_manager.winfo_exists():
            cfg = self.config_manager.selected_config()
            self.config_manager.refresh_list(select=cfg)

    # ---- output
    def _append_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _poll_output(self):
        try:
            while True:
                kind, payload = self.output_queue.get_nowait()
                if kind == "line":
                    self._append_output(payload)
                elif kind == "done":
                    self._on_run_done(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_output)

    # ---- run
    def _resolve_mode(self, cfg):
        all_ev = [e for e, _z in self.events] + sorted(
            e for e in (cfg.keep | cfg.delete) if e not in {x for x, _z in self.events})
        unedited = [e for e in all_ev if e not in cfg.keep and e not in cfg.delete]
        if not unedited and cfg.keep:
            return "w", sorted(cfg.keep)
        if cfg.delete:
            return "b", sorted(cfg.delete)
        return None, None

    def start(self):
        if self.running:
            return
        path = self.path_var.get().strip().strip('"')
        if not path or not os.path.isfile(path):
            messagebox.showerror("错误", "该路径不存在或无法读取，请重新选择", parent=self.root)
            return
        if not self.configs:
            messagebox.showerror("错误", "未定义选项，请尝试重新选择", parent=self.root)
            return
        idx = self.config_combo.current()
        cfg = self.configs[idx] if 0 <= idx < len(self.configs) else self.configs[0]
        mode, evs = self._resolve_mode(cfg)
        if mode is None:
            messagebox.showerror(
                "错误",
                "这个配置没有设置任何事件。请在「管理配置…」里把要删除的事件拖到「删除」，"
                "或把要保留的事件拖到「留下」。",
                parent=self.root)
            return
        if not messagebox.askokcancel("confirm", "确认要开始执行吗？", parent=self.root):
            return
        track_label = None
        if self.track_option_enabled():
            label = self.track_anim_var.get()
            if label in TRACK_ANIM_MAP:
                track_label = label
        self.running = True
        self.start_btn.configure(state="disabled")
        self.status_var.set("正在处理…")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        threading.Thread(target=self._run_level_exe,
                         args=(path, mode, cfg.name, evs, track_label),
                         daemon=True).start()

    def _run_level_exe(self, path, mode, name, evs, track_label=None):
        log = []
        self._last_output_path = None
        try:
            proc = subprocess.Popen(
                ["level.exe"], cwd=BASE_DIR, shell=True,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="gbk", errors="replace")
            lines = [path, mode, name] + list(evs) + ["/end"]
            out, err = proc.communicate("\n".join(lines) + "\n")
            for line in (out or "").replace("\r\n", "\n").split("\n"):
                if line.strip():
                    log.append(line)
            for line in (err or "").replace("\r\n", "\n").split("\n"):
                if line.strip():
                    log.append("[stderr] " + line)
            rc = proc.returncode
            if rc == 0:
                self._last_output_path = find_output_file(path, name)
            if rc == 0 and track_label in TRACK_ANIM_MAP:
                target = TRACK_ANIM_MAP[track_label]
                outfile = self._last_output_path
                if outfile is None:
                    log.append("[提示] 没有找到输出文件，轨道消失动画未调整。")
                else:
                    try:
                        changed, skipped, fixed = apply_track_disappear_animation(outfile, target)
                        msg = (f"[轨道消失动画] 已统一为「{track_label}」：修改 {changed} 处，"
                               f"跳过 {skipped} 处（未开启消失动画、已是目标值或无此字段）。")
                        if fixed:
                            msg += "（同时修复了输出文件的格式问题）"
                        log.append(msg)
                    except Exception as exc:
                        log.append(f"[提示] 轨道消失动画调整失败：{exc}")
        except Exception as exc:
            log.append(f"[错误] {exc}")
            rc = -1
        for line in log:
            self.output_queue.put(("line", line + "\n"))
        self.output_queue.put(("done", rc))

    def _on_run_done(self, rc):
        self.running = False
        self.start_btn.configure(state="normal")
        if rc == 0:
            self.status_var.set("处理完成")
            outfile = getattr(self, "_last_output_path", None)
            if outfile:
                self.last_output_dir = os.path.dirname(os.path.abspath(outfile))
            if self.autoclose:
                self.root.after(1200, self.close_app)
        else:
            self.status_var.set("处理失败")

    def open_output_dir(self):
        if self.last_output_dir and os.path.isdir(self.last_output_dir):
            try:
                os.startfile(self.last_output_dir)
                return
            except Exception:
                pass
        messagebox.showinfo("提示", "还没有生成过输出文件。\n先处理一张谱面后，这里可以直接打开输出文件夹。",
                            parent=self.root)

    def close_app(self):
        try:
            self.state["main"] = self.root.geometry()
            save_state(self.state)
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    root = tk.Tk()
    _app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
