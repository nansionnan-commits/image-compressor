# -*- coding: utf-8 -*-
"""_shot_custom_presets.py — 真机截 v11.4「自定义预设」界面

截的是**源码真跑起来的窗口** (不是画出来的图), 所以界面上看到的一切
都是真的: 按钮、顺序、文案、位置。

要证明三件事:
  1. 主界面多出「★ 我的自定义预设」区, 排在内置预设下面
  2. 高级参数区底部有「预设名称 + 💾 保存为自定义预设」
  3. 自定义预设区的每一行都有 ✎ / 🗑

跑法:
    C:\\Python314\\python.exe -X utf8 _shot_custom_presets.py
"""
import ctypes
import importlib.util
import os
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "compress_images_gui.py"
SHOTS = ROOT / "_shots"
OUT = SHOTS / "v114_custom_presets.png"

# ---- 把预设目录指到临时目录, 绝不动用户真的 %APPDATA% ----
TMP = Path(tempfile.mkdtemp(prefix="picshrink_shot_"))
os.environ["PICSHINK_CUSTOM_PRESETS_DIR"] = str(TMP / "presets")
# settings.json 也得隔离: 截图里会调 apply_preset(), 它会把选中的预设记成
# "右键默认预设" 写进 settings.json —— 不隔离的话, 用户的右键默认就被
# 这张截图改掉了, 而且截图一删预设, 那个引用就成了空名字。
os.environ["LOCALAPPDATA"] = str(TMP / "LocalAppData")
os.environ["APPDATA"] = str(TMP / "AppData")
(TMP / "LocalAppData").mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("cig_shot", SRC)
M = importlib.util.module_from_spec(spec)
sys.modules["cig_shot"] = M
spec.loader.exec_module(M)

# 造两个自定义预设, 让截图里有东西可看
M.save_custom_presets({
    "我的主图 300KB": {
        "mode": "target", "quality": 90, "target_kb": 300,
        "format": "jpg", "max_side": 2000, "keep_exif": False,
    },
    "A+ 超清 PNG": {
        "mode": "balanced", "quality": 92, "target_kb": 0,
        "format": "png", "max_side": 0, "keep_exif": False,
    },
})

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def shot(hwnd, path: Path):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise RuntimeError(f"窗口尺寸异常: {w}x{h}")
    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(memdc, bmp)
    user32.PrintWindow(hwnd, memdc, 2)      # 2 = PW_RENDERFULLCONTENT

    from PIL import Image

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -h        # 负数 = 自上而下
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)
    return w, h


import tkinter as tk

root = tk.Tk()
app = M.App(root)
# 展开高级参数区 (用户勾「显示自定义参数」之后的样子)
app.show_custom.set(True)
app._toggle_custom()
# 选中一个自定义预设, 让上面那行"已选: xxx"也有内容
app.apply_preset("我的主图 300KB")
app._refresh_custom_presets()
root.update_idletasks()
root.update()
root.deiconify()
root.lift()
user32.SetForegroundWindow(user32.GetAncestor(root.winfo_id(), 2))
time.sleep(1.2)
root.update()

# 窗口可能比内容高, 按内容撑一下, 免得截图下半截被切掉
root.geometry("1000x880")
root.update_idletasks()
time.sleep(0.8)
root.update()

hwnd = user32.GetAncestor(root.winfo_id(), 2)
SHOTS.mkdir(exist_ok=True)
w, h = shot(hwnd, OUT)
print(f"✅ 已截图: {OUT}  {w}x{h}  {OUT.stat().st_size} 字节")
print(f"   自定义预文件: {M._custom_presets_path()}")
print(f"   预设条目: {list(M.load_custom_presets())}")
root.destroy()
