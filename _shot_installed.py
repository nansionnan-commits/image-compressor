# -*- coding: utf-8 -*-
"""_shot_installed.py — 启动"已安装的 exe", 把它的主窗口原样截下来

为什么必须截真 exe 而不是跑源码:
  源码界面绿了不代表装到用户机器上的那个 exe 是新的。所以这里只认一个证据:
  启动 %LOCALAPPDATA%\\图瘦身\\PicShrink.exe, 把它的窗口抓下来给人眼看。

不 import 项目源码 —— 一行都不碰, 免得"截的是源码界面"自欺欺人。

用法:
    python _shot_installed.py                  # 默认 v17_installed_presets.png
    python _shot_installed.py v18_installed.png  # 指定输出文件名
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

EXE = Path.home() / "AppData" / "Local" / "图瘦身" / "PicShrink.exe"
# 输出名可传参: 每次验收都硬编码一个文件名的话, 下次改版本就得改代码
_NAME = sys.argv[1] if len(sys.argv) > 1 else "v17_installed_presets.png"
if not _NAME.endswith(".png"):
    _NAME += ".png"
OUT = Path(__file__).resolve().parent / "_shots" / _NAME

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def pid_image(pid: int) -> str:
    """取进程的可执行文件真实路径。

    PyInstaller onefile 会先起一个 bootloader 父进程, 真正的 GUI 跑在子进程里,
    所以窗口所在 PID 跟 Popen 给的 pid 不是一回事 —— 只能靠 exe 路径认亲。
    """
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def find_pid_window(pid: int, timeout: float = 25.0):
    """等主窗口出现, 返回 (hwnd, title)。找不到就 None。"""
    want = str(EXE).lower()
    t0 = time.time()
    found = []

    def cb(hwnd, _):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        img = pid_image(wpid.value).lower()
        # 认亲条件: 进程就是我们要启动的那个 exe(兼容 onefile 的父子两个 PID)
        if wpid.value == pid or img == want:
            found.append((hwnd, buf.value))
        return True

    while time.time() - t0 < timeout:
        found.clear()
        user32.EnumWindows(EnumWindowsProc(cb), 0)
        if found:
            return found[0]
        time.sleep(0.3)
    return None


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
    # 2 = PW_RENDERFULLCONTENT, 普通 BitBlt 抓不到无边框窗口的阴影/圆角
    user32.PrintWindow(hwnd, memdc, 2)

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
    bi.biWidth = w
    bi.biHeight = -h          # 负数 = 自上而下
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)
    return w, h


if not EXE.is_file():
    print(f"❌ 已安装 exe 不存在: {EXE}")
    sys.exit(1)

print(f"启动: {EXE}")
p = subprocess.Popen([str(EXE)])
try:
    hit = find_pid_window(p.pid)
    if not hit:
        print("❌ 25 秒内没等到主窗口")
        sys.exit(1)
    hwnd, title = hit
    print(f"主窗口: hwnd={hwnd} 标题={title!r}")

    user32.SetForegroundWindow(hwnd)
    user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    time.sleep(1.2)

    w, h = shot(hwnd, OUT)
    print(f"已截图: {OUT}  {w}x{h}  {OUT.stat().st_size} 字节")
finally:
    p.terminate()
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()