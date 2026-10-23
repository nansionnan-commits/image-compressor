# -*- coding: utf-8 -*-
"""_shot_queue.py — 真机验收 v11.3「加入压缩队列」

为什么单独写一个: `_shot_installed.py` 只截"主窗口空着"的样子,
证明不了新功能。v11.3 的卖点是右键点「加入压缩队列」之后,
路径会跑进**已经开着**的主窗口, 而且不再多开第二个窗口 ——
这一条只有把整条链在真机 exe 上跑一遍才算数。

这里刻意不 import 项目源码, 一个字都不碰:
截的必须是装到用户机器上的那个 exe, 不能是源码界面。

跑法:
    python _shot_queue.py            # 用已注册表里的那条命令原样投递
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

EXE = Path.home() / "AppData" / "Local" / "图瘦身" / "PicShrink.exe"
SHOTS = Path(__file__).resolve().parent / "_shots"
OUT = SHOTS / "v113_queue.png"
WORK = Path.home() / "AppData" / "Local" / "Temp" / "picshrink_v113_shot"

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def pid_image(pid: int) -> str:
    """取进程 exe 真实路径。PyInstaller onefile 的 GUI 跑在子进程里,
    窗口 PID 跟 Popen 给的不是一个, 只能靠 exe 路径认亲。"""
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
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


def all_windows():
    res = []

    def cb(hwnd, _):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                res.append((hwnd, wpid.value, buf.value, pid_image(wpid.value)))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return res


def main_windows():
    """主窗口的标题不是「图瘦身 (PicShrink) v11」——那是结果窗的标题。
    主窗口真实标题是「图瘦身 v11 (拖图片/文件夹进窗口, ...)」。
    写死错标题的教训: 等 25 秒找不到窗口, 一度以为 --gui 坏了。
    这里只认前缀「图瘦身」+ 进程是装的这个 exe, 标题改了也不会再踩。"""
    want = str(EXE).lower()
    out = []
    for h, _p, t, img in all_windows():
        if not img or img.lower() != want:
            continue
        if t.startswith("图瘦身") or t.startswith("图瘦身 v"):
            out.append((h, t))
    return out


def wait_main(timeout=25.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = main_windows()
        if m:
            return m[0]
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


def make_pics(n=4):
    WORK.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    out = []
    for i in range(n):
        w, h = 1400 + i * 90, 1000 + i * 70
        im = Image.new("RGB", (w, h))
        px = im.load()
        for y in range(0, h, 3):
            for x in range(0, w, 3):
                px[x, y] = ((x * 7 + i * 40) % 256, (y * 5) % 256,
                            ((x + y) * 3 + i * 60) % 256)
        p = WORK / f"验收图_{i + 1}.jpg"
        im.save(p, quality=95)
        out.append(p)
    return out


def kill_all():
    subprocess.run(["taskkill", "/F", "/IM", "PicShrink.exe"],
                   capture_output=True, creationflags=0x08000000)
    time.sleep(1.5)


if not EXE.is_file():
    print(f"❌ 已安装 exe 不存在: {EXE}")
    sys.exit(1)

kill_all()
pics = make_pics()
print(f"造了 {len(pics)} 张验收图:")
for p in pics:
    print(f"  {p}")

# ---- 1) 起主窗口 (模拟用户先双击桌面图标) ----
print("\n[1] 启动主窗口 (无参数)")
main = subprocess.Popen([str(EXE), "--gui"])
hit = wait_main()
if not hit:
    print("❌ 25 秒内没等到主窗口")
    main.kill()
    sys.exit(1)
hwnd, title = hit
print(f"    主窗口已开: hwnd={hwnd} 标题={title!r}")

user32.SetForegroundWindow(hwnd)
user32.ShowWindow(hwnd, 9)
time.sleep(1.0)
before = len(main_windows())
print(f"    当前 PicShrink 主窗口数 = {before}")

# ---- 2) 用「加入压缩队列」那条注册表命令原样投递 ----
# 注册表里就是这个: "<exe>" --gui "%1" / --gui "%V"
print("\n[2] 按注册表里的命令投递 (exe --gui <4 张图>)")
rc = subprocess.run([str(EXE), "--gui"] + [str(p) for p in pics],
                    capture_output=True, creationflags=0x08000000)
print(f"    投递进程退出码 = {rc.returncode}  (0 = 已投递给主窗口后自行退出)")

time.sleep(2.5)                      # 主窗口每 400ms 收一次, 给它两轮
user32.SetForegroundWindow(hwnd)
user32.ShowWindow(hwnd, 9)
time.sleep(0.8)

after = main_windows()
print(f"    投递后主窗口数 = {len(after)}  (必须还是 1, 没多开窗口)")
hwnd2 = after[0][0] if after else hwnd

w, h = shot(hwnd2, OUT)
print(f"\n✅ 已截图: {OUT}  {w}x{h}  {OUT.stat().st_size} 字节")

if len(after) != 1:
    print(f"❌ 投递后主窗口变成了 {len(after)} 个, 单实例没守住")
    sys.exit(1)

kill_all()
print("\n主窗口已关闭")