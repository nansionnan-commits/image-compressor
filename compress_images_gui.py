"""
图瘦身 (PicShrink) — 单文件 GUI 入口 (压缩引擎 + Tkinter + tkinterdnd2 OS 拖拽).

品牌: 中文名「图瘦身」/ 英文名 PicShrink / exe 名「图瘦身.exe」.
版本: v11.4 (用户自定义预设: 自己存档, 卸载重装都还在).

核心能力 (相对早期 v3/v4):
  - 10 个预设 (按"画质损失程度"分层):
      两个无损 / 三个有损 / 五个目标体积 (📦 限边长 200KB / 120KB, 📐 尺寸不变 200KB / 500KB / 900KB).
  - 真实 OS 拖拽 (tkinterdnd2 + tkdnd 2.10+) — 不只是 Listbox, 整个窗口都能拖.
  - 目标体积模式: 长边限位 + 质量二分搜索, 选择能达标的最高质量 (下限 q18).
  - 输出撞原图时自动加 _compressed 后缀; 重复运行覆盖旧压缩输出, 原图永不覆盖.
  - 像素零差异验证: ImageChops.difference(a,b).getbbox() is None.
  - 单文件 PyInstaller 打包, 内置 Python + Pillow + tkdnd 资源.
"""

import ctypes
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

# v6: 加 tkinterdnd2 接 OS 文件拖拽, 缺失就降级到按钮选文件
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False
    TkinterDnD = None  # type: ignore
    DND_FILES = None  # type: ignore

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image

# 集成纯 Python jpeg 优化器 (替代 jpegoptim, 剥 EXIF 真 0 损失)
try:
    from _jpeg_strip import optimize_jpeg
    HAS_JPEG_STRIP = True
except ImportError:
    HAS_JPEG_STRIP = False

SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

# ===== 预设: 按"画质损失程度"分层, 共 10 个 =====
#   lossless    = 纯 Python 剥 EXIF (真 0 损失) + PIL PNG optimize
#   balanced    = q=85 重编码 (业界甜点)
#   aggressive  = q=80 重编码 (省最多)
#   amazon      = jpg 2000px q=85
#   target      = 先限长边, 再二分搜索质量, 一直压到目标字节数以内
PRESETS = {
    "🎯 无损压缩": {"mode": "lossless", "keep_exif": False, "max_side": 0,
                  "desc": "剥 EXIF 真 0 损失, JPG 省 5-20%"},
    "💎 极致保真": {"mode": "lossless", "keep_exif": True,  "max_side": 0,
                  "desc": "无损+保留 EXIF, 跟上面一样省"},
    "⚡ 推荐压缩": {"mode": "balanced", "keep_exif": False, "max_side": 0,
                  "quality": 85, "desc": "q=85 业界甜点, 省 25% 肉眼难辨"},
    "💾 压最小":   {"mode": "aggressive", "keep_exif": False, "max_side": 0,
                  "quality": 80, "desc": "q=80 重编码, 省最多"},
    "🛒 亚马逊主图": {"mode": "balanced", "format": "jpg", "max_side": 2000,
                  "quality": 85, "keep_exif": False,
                  "desc": "2000px JPG 符合 Amazon 主图要求"},
    # --- 📦 这一类: 会限制边长 (长宽比不变, 但像素会被缩小) ---
    "📦 限边长1280 ≤200KB": {"mode": "target", "format": "jpg", "max_side": 1280,
                  "target_kb": 200, "quality": 90, "keep_exif": False,
                  "desc": "长边缩到 1280 + 自动降质量, 压到 ≤200KB"},
    "📦 限边长1100 ≤120KB": {"mode": "target", "format": "jpg", "max_side": 1100,
                  "target_kb": 120, "quality": 90, "keep_exif": False,
                  "desc": "长边缩到 1100 + 自动降质量, 压到 ≤120KB"},
    # --- 📐 这一类: 尺寸 / 比例 / 边长一个像素都不动, 只自动降质量 ---
    # max_side=0 是关键, 千万别填数字:
    #   A+ 各模块的像素尺寸是亚马逊硬性要求(970×300 / 1400×300 / 1920×600 ...),
    #   缩了就直接不合规。而压体积只需要降质量就够了, 所以这几个预设
    #   "只降质量, 一个像素都不动" —— 长宽比也天然保持不变, 不裁不补。
    "📐 尺寸不变 ≤500KB": {"mode": "target", "format": "jpg", "max_side": 0,
                  "target_kb": 500, "quality": 90, "keep_exif": False,
                  "desc": "A+模块通用(限500KB), 尺寸/比例/边长完全不动, 只自动降质量"},
    "📐 尺寸不变 ≤900KB": {"mode": "target", "format": "jpg", "max_side": 0,
                  "target_kb": 900, "quality": 90, "keep_exif": False,
                  "desc": "大图模块通用(限900KB), 尺寸/比例/边长完全不动, 只自动降质量"},
    # ⚠ 新增的档位必须追加在 PRESETS 末尾, 不能插在中间!
    #   --preset N 是按 PRESETS 的插入顺序编号的, 插中间会把后面所有序号
    #   顶掉一位 —— 老快捷方式/脚本里的 "9"(900KB) 会静默变成 500KB。
    #   界面上的显示顺序由下面的 PRESET_ROWS 决定, 跟这里的顺序解耦。
    "📐 尺寸不变 ≤200KB": {"mode": "target", "format": "jpg", "max_side": 0,
                  "target_kb": 200, "quality": 90, "keep_exif": False,
                  "desc": "小体积档(限200KB), 尺寸/比例/边长完全不动, 只自动降质量"},
}

# 预设改过名。旧名 -> 新名, 只为把老配置里的值搬过来, 不做两套名字并存
# (并存的话 --preset 全名 和界面下拉框会各出现一份, 用户根本分不清哪个是哪个)。
# ⚠ 以后任何改名都必须在这里补一行。否则用户 settings.json / quick.json 里
#   存的旧名会在 _load_settings 里被判为非法, 静默回落到默认预设 —— 用户会发现
#   自己选的 A+900 突然变成推荐压缩, 而且完全不知道为什么。
PRESET_RENAMES = {
    "📦 主图≤200KB": "📦 限边长1280 ≤200KB",
    "📦 主图≤120KB": "📦 限边长1100 ≤120KB",
    "📐 A+图≤500KB": "📐 尺寸不变 ≤500KB",
    "📐 A+图≤900KB": "📐 尺寸不变 ≤900KB",
}

# 预设分三行显示 (一行塞不下 4 个以上按钮会被截断)
PRESET_ROWS = [
    ["🎯 无损压缩", "💎 极致保真", "⚡ 推荐压缩", "💾 压最小"],
    ["🛒 亚马逊主图", "📦 限边长1280 ≤200KB", "📦 限边长1100 ≤120KB"],
    ["📐 尺寸不变 ≤200KB", "📐 尺寸不变 ≤500KB", "📐 尺寸不变 ≤900KB"],
]

MODE_LABELS = {
    "lossless": "无损 (不重编码 quality)",
    "balanced": "均衡 (肉眼难辨)",
    "aggressive": "激进 (细看能看)",
    "target": "🎯 目标大小 (自动降质量)",
}
MODE_LABELS_REV = {v: k for k, v in MODE_LABELS.items()}

MIN_SIZE_SKIP = 50 * 1024
KEEP_IF_LARGER_RATIO = 0.95
TARGET_MIN_Q = 18  # 目标大小模式下允许降到的最低质量 (再低就真的没法看了)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _same_path(a: Path, b: Path) -> bool:
    """两个路径是不是同一个文件 (Windows 上大小写不敏感)."""
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _safe_out_path(src: Path, out_dir: Path, ext: str) -> Path:
    """算输出路径, 永远不可能等于原图本身.

    踩过的坑: 输出目录选了原图的上级文件夹时, 程序会在输出目录下再拼一层
    原文件夹名, 结果输出的就是原图自己 -> 旧版本直接报"目标已存在,跳过".
    这里遇到自撞就自动加 _compressed 后缀.
    """
    plain = out_dir / f"{src.stem}.{ext}"
    if not _same_path(plain, src):
        return plain
    for i in range(1, 1000):
        stem = f"{src.stem}_compressed" if i == 1 else f"{src.stem}_compressed{i}"
        cand = out_dir / f"{stem}.{ext}"
        if not _same_path(cand, src):
            return cand
    return out_dir / f"{src.stem}_compressed_x.{ext}"


def pick_output_format(src: Path, fmt_arg: str) -> tuple[str, str]:
    """返回 (Pillow 保存格式, 输出扩展名). 'keep' = 保持原格式.

    v11: 'keep' 改成"看真实内容, 不看后缀".
      后缀只说明文件叫什么, 内容才决定 Pillow 能不能写.
      之前只看后缀 -> 一张后缀 .png 内容其实是 TIFF 的图,
      按 PNG 存就会撞上 "cannot write mode PA as PNG"。
      现在优先用 Image.open(src).format, 读不出来才退回后缀。
    """
    if fmt_arg == "keep":
        ext = src.suffix.lower().lstrip(".")
        if ext == "tif":
            ext = "tiff"
        content = _sniff_format(src)
        if content:
            return content, _EXT_FOR_FORMAT.get(content, ext or "jpg")
        return _FMT_FOR_EXT.get(ext, "JPEG"), ext or "jpg"
    if fmt_arg == "auto":
        return pick_output_format(src, "keep")
    if fmt_arg == "jpg":
        return "JPEG", "jpg"
    return fmt_arg.upper(), "jpg" if fmt_arg == "jpg" else fmt_arg


# 后缀 -> Pillow 格式
_FMT_FOR_EXT = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG",
                "webp": "WEBP", "bmp": "BMP", "tif": "TIFF", "tiff": "TIFF"}
# Pillow 格式 -> 输出扩展名
_EXT_FOR_FORMAT = {"JPEG": "jpg", "JPEG2000": "jp2", "PNG": "png",
                   "WEBP": "webp", "BMP": "bmp", "TIFF": "tiff",
                   "GIF": "gif", "PPM": "ppm", "ICO": "ico", "TGA": "tga"}


def _sniff_format(src: Path) -> str:
    """读文件头判断真实格式. 读不出来返回 "" (调用方退回后缀)."""
    try:
        with Image.open(src) as im:
            return (im.format or "").upper()
    except Exception:
        return ""


# ===== 各格式真正能写的 mode (Pillow 12.3 逐个试出来的, 不要凭感觉改) =====
#   来源: _t_probe_modes.py, 对每个 mode × 格式 实测 save + 回读.
#   这张表是 _fit_for_format 的唯一依据.
_SAVE_MODES: dict[str, set[str]] = {
    # PA / RGBa / La / F / CMYK / YCbCr / HSV 存不进来
    "PNG":  {"1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"},
    # 完全不收 alpha
    "JPEG": {"L", "RGB", "CMYK", "YCbCr"},
    "WEBP": {"1", "L", "LA", "P", "PA", "I", "I;16", "F",
             "RGB", "RGBA", "CMYK", "YCbCr", "HSV"},
    # BMP 写 RGBA 会丢 alpha, 所以带 alpha 的统一转 RGB
    "BMP":  {"1", "L", "P", "RGB", "RGBA"},
    # TIFF 最宽松, 基本原样透传
    "TIFF": {"1", "L", "LA", "P", "PA", "I", "I;16", "F",
             "RGB", "RGBA", "CMYK", "YCbCr"},
}


def _has_alpha(im: Image.Image) -> bool:
    """这张图带不带透明通道 (含调色板里的 tRNS)."""
    if im.mode in ("RGBA", "RGBa", "LA", "La", "PA"):
        return True
    return im.mode == "P" and "transparency" in im.info


def _flatten_on_white(im: Image.Image) -> Image.Image:
    """把透明区域铺成白底 (JPEG / BMP 不支持透明时的唯一出路)."""
    bg = Image.new("RGB", im.size, (255, 255, 255))
    rgba = im.convert("RGBA")
    bg.paste(rgba, mask=rgba.getchannel("A"))
    return bg


def _fit_for_format(im: Image.Image, fmt: str) -> Image.Image:
    """保证 im 一定能被 save(fmt) 写出去, 而且绝不静默丢 alpha.

    v11 新增。之前没这一层, 两个地方会炸:
      1) TIFF/JPEG2000 的调色板+alpha (mode=PA) 直接存 PNG -> OSError
      2) 量化后调 putalpha() 把 P 变成 PA, 再存 PNG -> 同一个 OSError
         这条让 ⚡推荐压缩 / 💾压最小 压任何透明 PNG 都失败.
    """
    fmt = (fmt or "PNG").upper()
    allowed = _SAVE_MODES.get(fmt)
    if allowed is None or im.mode in allowed:
        return im                       # 未知格式交给 Pillow 自己报错

    alpha = _has_alpha(im)
    if alpha:
        if "RGBA" in allowed:
            return im.convert("RGBA")   # PA / RGBa / La 都能无损保住透明
        if fmt == "JPEG":
            return _flatten_on_white(im)
        if "LA" in allowed:
            return im.convert("LA")
    # 没 alpha, 或者目标格式不收 alpha 但又不是 JPEG: 一律降到 RGB
    if "RGB" in allowed:
        return im.convert("RGB")
    if "L" in allowed:
        return im.convert("L")
    return im


def _encode_bytes(im: Image.Image, fmt: str, **kw) -> bytes:
    """把 im 编码成目标格式的字节流, 编码不出来就降级重试一次.

    三层保险:
      1) _fit_for_format 按实测表先把 mode 掰到目标格式能写的形态
      2) 真的还抛 OSError -> 强制转 RGB / RGBA 再试
      3) 还不行才让异常冒出去 (留给上层记失败)

    所有 save 调用都必须走这里, 别再直接 im.save(buf, fmt)。
    """
    fmt = (fmt or "PNG").upper()
    im = _fit_for_format(im, fmt)
    buf = io.BytesIO()
    try:
        im.save(buf, fmt, **kw)
        return buf.getvalue()
    except OSError:
        pass
    alpha = _has_alpha(im)
    fallback = im.convert("RGBA" if alpha and fmt in ("PNG", "WEBP") else "RGB")
    buf = io.BytesIO()
    fallback.save(buf, fmt, **kw)
    return buf.getvalue()


def _apply_mode(im: Image.Image, mode: str, fmt: str, quality: int) -> Image.Image:
    """根据 mode 调整图像 (量化等) + 保证 mode 能存进目标格式.

    v11 修掉一个全预设通杀的老 bug:
      透明 PNG 原来走的是"拆 alpha + RGB 量化 + putalpha 合并",
      而 putalpha() 作用在 P 图上会把 mode 变成 PA,
      PA 根本存不进 PNG -> ⚡推荐压缩 / 💾压最小 压任何透明 PNG 都失败。
      现在带 alpha 的图一律不做调色板量化 (量化会改颜色, 对商品图是灾难),
      只靠 zlib optimize 压 —— 实测未 optimize 的 RGBA PNG 能省 68.7%,
      本来就 optimize 过的会由 compress_one 的智能回退判定"跳过"。
    """
    fmt = (fmt or "PNG").upper()

    if fmt in ("JPEG", "BMP") and _has_alpha(im):
        im = _flatten_on_white(im)
    elif fmt in ("JPEG", "WEBP") and im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if _has_alpha(im) else "RGB")

    if fmt == "PNG" and mode in ("balanced", "aggressive"):
        colors = 256 if mode == "balanced" else 128
        if _has_alpha(im):
            pass                    # 带透明 -> 不量化, 保持 RGBA (见上面说明)
        elif im.mode not in ("P", "L", "1"):
            im = im.convert("RGB").quantize(colors=colors,
                                            method=Image.Quantize.MEDIANCUT)
    return _fit_for_format(im, fmt)


def _save_kwargs(mode: str, fmt: str, quality: int, keep_exif: bool, src: Image.Image) -> dict:
    """根据 mode 计算 save 参数."""
    kw: dict = {"optimize": True}
    if keep_exif and "exif" in src.info:
        kw["exif"] = src.info["exif"]
    if fmt in ("JPEG", "WEBP"):
        if mode == "lossless":
            # 不传 quality -> Pillow 用原图的 quality, 这就是真无损
            pass
        else:
            kw["quality"] = quality
        if fmt == "WEBP" and mode != "lossless":
            kw["method"] = 4
    return kw


def _encode_to_target(im: Image.Image, fmt: str, target_bytes: int,
                      keep_exif: bool, src: Image.Image,
                      hi_q: int = 92) -> tuple[bytes | None, int, int, bool]:
    """二分搜索质量, 编码到 target_bytes 以内.

    返回 (数据, 实际质量, 实际字节数, 是否达标).
    达标 = 在目标以内; 不达标时返回的是最低质量(TARGET_MIN_Q)的结果, 尽力而为.
    """
    kw_exif = {"exif": src.info["exif"]} if (keep_exif and "exif" in src.info) else {}

    def enc(q: int) -> bytes:
        return _encode_bytes(im, fmt, quality=q, optimize=True, **kw_exif)

    # 先用最高允许质量试一次, 达标就直接用 (画质最好)
    top = enc(hi_q)
    if len(top) <= target_bytes:
        return top, hi_q, len(top), True

    lo, hi, best = TARGET_MIN_Q, hi_q - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        data = enc(mid)
        if len(data) <= target_bytes:
            best = (mid, data, len(data))
            lo = mid + 1        # 还能再往上提质量
        else:
            hi = mid - 1

    if best is not None:
        return best[1], best[0], best[2], True
    # 降到 TARGET_MIN_Q 还是超 -> 尽力输出最低质量, 由调用方在日志里明说没达标
    floor = enc(TARGET_MIN_Q)
    return floor, TARGET_MIN_Q, len(floor), False

def _write_bytes(out_path: Path, data: bytes) -> bool:
    """原子写入并覆盖旧输出. 先写 .tmp 再 os.replace, 崩了也不会留半截文件.

    只覆盖"我们生成的输出文件", 永远不会碰到原图 (调用方已用 _safe_out_path 挡掉).
    """
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(out_path)   # os.replace 原子覆盖, Windows 也支持
        return True
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _fit_side(im: Image.Image, max_side: int) -> Image.Image:
    """按长边上限缩放 (LANCZOS), max_side=0 表示不动."""
    if not max_side:
        return im
    w, h = im.size
    if max(w, h) <= max_side:
        return im
    if w >= h:
        nw, nh = max_side, int(h * max_side / w)
    else:
        nw, nh = int(w * max_side / h), max_side
    return im.resize((nw, nh), Image.LANCZOS)


def _commit_output(out_path: Path, data: bytes, out_mode: str) -> bool:
    """写最终输出。覆盖模式下先备份原图 —— 覆盖原图唯一能接受的前提。"""
    if out_mode == "overwrite" and out_path.is_file():
        bak = _backup_original(out_path)
        if bak:
            _v9_log(f"  [备份] {out_path.name} -> {bak}")
    return _write_bytes(out_path, data)


_OUT_OWNER: dict[str, str] = {}   # 本进程内: 目标路径(小写) -> 写出它的源文件


def _pick_free(dst: Path, src: Path) -> Path | None:
    """判断某个目标路径这次能不能用. 返回 None = 这个位置已经被别的图占了."""
    if _same_path(dst, src):
        return None                                   # 绝不能写到原图头上
    key = str(dst).lower()
    if _OUT_OWNER.get(key) == str(src):
        return dst                                    # 本轮同一张图 → 幂等重写
    if dst.exists():
        return None                                    # 别的图已经占了
    return dst


def _fixed_out_path(src: Path, out_dir: Path, ext: str) -> Path:
    """固定目录: 不同来源的同名图不互相覆盖, 但同一张图重复压可以幂等重写.

    踩过的坑: 之前直接 out_root/<原名>.ext, 两个文件夹里的"主图.jpg"会被压缩到
    同一个地方, 后压的那张悄悄顶掉前一张 —— 用户以为两张都导出了, 实际只剩一张.
    """
    for cand in ([out_dir / f"{src.stem}.{ext}"]
                 + [out_dir / f"{src.stem}_{i}.{ext}" for i in range(1, 10000)]):
        free = _pick_free(cand, src)
        if free is not None:
            _OUT_OWNER[str(free).lower()] = str(src)
            return free
    raise RuntimeError(f"固定目录里找不到可用文件名: {src.name}")


def _suffixed_out_path(src: Path, out_dir: Path, ext: str) -> Path:
    """原文件夹导出, 名字后加 _compressed 区分. 撞名再自动加序号.

    这里不用 _safe_out_path 的"自撞才加后缀"逻辑: 用户明确要求原文件夹导出,
    所以后缀是默认行为而不是兜底行为.
    """
    for i in range(1, 1000):
        stem = f"{src.stem}_compressed" if i == 1 else f"{src.stem}_compressed{i}"
        cand = out_dir / f"{stem}.{ext}"
        if not _same_path(cand, src):
            return cand
    return out_dir / f"{src.stem}_compressed_x.{ext}"


def _resolve_out_path(src: Path, out_root: Path, ext: str,
                      out_mode: str) -> tuple[Path, Path]:
    """按输出模式算出最终落到哪. 返回 (输出文件路径, 输出目录).

      suffix   (默认) 原文件夹/<原名>_compressed.ext  —— 原图永不覆盖
      fixed    指定文件夹/<原名>.ext                  —— 全部堆一个文件夹
      overwrite src 本身                              —— 先备份再覆盖

    注意 suffix/fixed 都不该把 out_root 再拼一层源文件夹名:
    那是 v9 老行为, 用户要的是"原文件夹导出"和"固定位置导出".
    """
    if out_mode == "overwrite":
        return src, src.parent
    if out_mode == "fixed":
        return _fixed_out_path(src, out_root, ext), out_root
    out_dir = src.parent if src.parent != Path(".") else Path(".")
    return _suffixed_out_path(src, out_dir, ext), out_dir


def compress_one(src: Path, out_root: Path, mode: str, quality: int,
                 fmt: str, ext: str, max_side: int, keep_exif: bool,
                 skip_if_larger: bool = True,
                 target_kb: int = 0,
                 out_mode: str = "suffix") -> tuple[Path, int, int, str]:
    """压缩单张. mode: lossless / balanced / aggressive / target.

    安全策略 (v7, v11 扩展):
      - 输出路径永远不可能等于原图, 撞车自动加 _compressed 后缀
        (唯一例外是用户显式选的 out_mode="overwrite", 那种会先备份)
      - out_mode="suffix"/"fixed" 时原图只读, 任何分支都不覆盖原图
      - 上一轮生成的压缩结果会被直接覆盖重写 -> 重复点"开始压缩"不再一堆"跳过"

    返回 (输出路径, 原图字节, 输出字节, 状态消息)
      状态 "ok" 或 "ok|..." = 成功; 含"跳过" = 没压; 其余 = 失败
    """
    out_path, out_dir = _resolve_out_path(src, out_root, ext, out_mode)
    out_dir.mkdir(parents=True, exist_ok=True)
    src_bytes = src.stat().st_size

    if src_bytes < MIN_SIZE_SKIP:
        return (out_path, src_bytes, src_bytes,
                f"跳过 (原图 < 50KB, {human_size(src_bytes)})")

    # ============== 目标大小模式: 二分搜索质量压到目标以内 ==============
    if mode == "target" and target_kb > 0:
        target_bytes = target_kb * 1024
        # 原图本来就比目标还小, 再压只会白白掉画质
        if src_bytes <= target_bytes and skip_if_larger:
            return (src, src_bytes, src_bytes,
                    f"跳过 (原图 {human_size(src_bytes)} 已小于目标 {target_kb}KB, 不压)")
        try:
            with Image.open(src) as im:
                im2 = _fit_side(_apply_mode(im, "balanced", fmt, quality), max_side)
                data, used_q, got, hit = _encode_to_target(
                    im2, fmt, target_bytes, keep_exif, im, hi_q=max(quality, 60))
        except Exception as e:
            return (out_path, src_bytes, 0, f"失败:{e}")
        # 目标模式下质量对 PNG/BMP/TIFF 几乎无效, 二分搜索只能一路压到 q18 仍然超标.
        # 结果就是"为了压到 200KB, 反而给用户一个比原图更大的文件" —— 违背"永不越压越大"
        # 这条底线, 所以这里跟其它分支一样走智能回退: 没变小就原样保留.
        # 达不到目标但确实变小的图仍然照常写出 (上面 _t_v7 的"极难目标"用例就靠这条).
        if skip_if_larger and got >= src_bytes:
            return (src, src_bytes, got,
                    f"跳过 (压到最低q{TARGET_MIN_Q}后仍 {human_size(got)} "
                    f"> 原图 {human_size(src_bytes)}, 保留原图)")
        if not _commit_output(out_path, data, out_mode):
            return (out_path, src_bytes, 0, "写入失败(可能被占用)")
        if hit:
            return (out_path, src_bytes, got, f"ok|质量q={used_q}")
        # 关键词"未达标"被 GUI 用来统计告警, 改文案时务必同步
        return (out_path, src_bytes, got,
                f"ok|质量q={used_q}|未达标(已降到最低q{TARGET_MIN_Q}仍超目标, "
                f"实得{human_size(got)})")

    # ============== lossless 模式: 真 0 损失 ==============
    if mode == "lossless":
        # JPG 走纯 Python 剥 EXIF (真 0 损失)
        if fmt == "JPEG" and HAS_JPEG_STRIP and max_side == 0:
            tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
            ok, ib, ob = optimize_jpeg(src, tmp_path, strip_all=not keep_exif, keep_jfif=True)
            if not ok:
                try: tmp_path.unlink(missing_ok=True)
                except OSError: pass
                return (out_path, src_bytes, 0, "lossless 失败")
            # 无损: 像素一模一样, 省一字节是一字节, 不该被 95% 门槛卡掉
            # (95% 那条规矩是给"有损重编码"用的 — 那种才需要权衡画质)
            # 但为了省几十字节去复制一个几 MB 的文件也不划算, 所以设了 1KB 绝对下限
            saved = src_bytes - ob
            if skip_if_larger and saved < 1024:
                try: tmp_path.unlink(missing_ok=True)
                except OSError: pass
                return (src, src_bytes, src_bytes,
                        f"跳过 (可剥的元数据只有 {saved}B, 不值得再存一个 "
                        f"{human_size(src_bytes)} 的文件, 原样保留)")
            if out_mode == "overwrite" and out_path.is_file():
                bak = _backup_original(out_path)
                if bak:
                    _v9_log(f"  [备份] {out_path.name} -> {bak}")
            try:
                tmp_path.replace(out_path)   # 覆盖上一轮的压缩结果
            except OSError:
                return (out_path, src_bytes, 0, "写入失败(可能被占用)")
            return (out_path, src_bytes, ob, "ok")
        # PNG 走 PIL optimize (真 0 损失); 其他情况降级到 balanced
        mode = "balanced" if fmt == "JPEG" else "lossless_fallback"

    try:
        with Image.open(src) as im:
            im2 = _fit_side(_apply_mode(im, mode, fmt, quality), max_side)
            kw = _save_kwargs(mode, fmt, quality, keep_exif, im)
            data = _encode_bytes(im2, fmt, **kw)

            if skip_if_larger and len(data) >= src_bytes * KEEP_IF_LARGER_RATIO:
                return (src, src_bytes, src_bytes,
                        f"跳过 (压完 {human_size(len(data))} ≥ 原图 {human_size(src_bytes)}, 保留原图)")

            if not _commit_output(out_path, data, out_mode):
                return (out_path, src_bytes, 0, "写入失败(可能被占用)")
            return (out_path, src_bytes, len(data), "ok")

    except Exception as e:
        return (out_path, src_bytes, 0, f"失败:{e}")


def compress_to_bytes(src: Path, mode: str, quality: int,
                      fmt: str, max_side: int, keep_exif: bool,
                      target_kb: int = 0) -> tuple[int, str]:
    """预览: 内存压缩. 返回 (预估字节数, 错误信息)."""
    src_bytes = src.stat().st_size
    if src_bytes < MIN_SIZE_SKIP:
        return (src_bytes, "原图 < 50KB, 不压")

    # 目标大小模式
    if mode == "target" and target_kb > 0:
        target_bytes = target_kb * 1024
        if src_bytes <= target_bytes:
            return (src_bytes, "")
        try:
            with Image.open(src) as im:
                im2 = _fit_side(_apply_mode(im, "balanced", fmt, quality), max_side)
                data, _q, got, _hit = _encode_to_target(
                    im2, fmt, target_bytes, keep_exif, im, hi_q=max(quality, 60))
            # 跟 compress_one 的智能回退保持一致: 预览别报一个"压完反而更大"的数字
            return (src_bytes if got >= src_bytes else got, "")
        except Exception as e:
            return (0, f"预览失败:{e}")

    # lossless 走临时文件 + 剥 EXIF
    if mode == "lossless" and fmt == "JPEG" and HAS_JPEG_STRIP and max_side == 0:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            ok, _, ob = optimize_jpeg(src, tmp_path, strip_all=not keep_exif, keep_jfif=True)
            tmp_path.unlink(missing_ok=True)
            if ok:
                return (ob, "")
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            return (0, f"预览失败:{e}")
    try:
        with Image.open(src) as im:
            im2 = _fit_side(_apply_mode(im, mode, fmt, quality), max_side)
            kw = _save_kwargs(mode, fmt, quality, keep_exif, im)
            return (len(_encode_bytes(im2, fmt, **kw)), "")
    except Exception as e:
        return (0, f"预览失败:{e}")


class App:
    def report_callback_exception(self, exc, val, tb):
        """回调里出错时给用户看, 别悄悄死掉.

        exe 是 console=False 打的, 没有控制台, sys.stderr 是 None, Tk 默认的
        报错路径什么也打印不出来。后果就是某个控件建到一半抛异常 → 窗口半截
        停在中间, 用户看不到任何提示(设置窗口就因此丢过「保存」按钮),
        只能理解成"这软件坏了"。所以这里必须弹框 + 落盘日志。
        """
        text = "".join(traceback.format_exception(exc, val, tb))
        _v9_log(f"\n=== GUI 回调异常 ===\n{text}")
        try:
            messagebox.showerror(
                "图瘦身 — 出错了",
                f"这一步没能完成:\n\n{exc.__name__}: {val}\n\n"
                f"详情已写到日志:\n"
                f"{Path(os.environ.get('TEMP', '.')) / V9_LOG_NAME}",
                parent=self.root)
        except Exception:
            pass

    def __init__(self, root):
        self.root = root
        # 标题里的预设数量必须动态取 —— 写死过一次("7 预设"), 加了档位之后
        # 用户在标题栏看到的还是旧数字, 会以为预设没加上去。
        # 自定义预设的数量会变, 单独标出来, 让人一眼知道"我自己存了几个"。
        _n_custom = len(load_custom_presets())
        _title = (f"图瘦身 v11.4 (拖图片/文件夹进窗口, "
                  f"{len(PRESETS)} 预设 + 按目标体积压)")
        if _n_custom:
            _title += f" · 我的预设 {_n_custom}"
        root.title(_title)
        root.geometry("1000x880")
        # 窗口图标 (含任务栏图标). 兼容 PyInstaller 单文件 (sys._MEIPASS).
        try:
            from pathlib import Path as _Path
            _ico = _Path(getattr(sys, "_MEIPASS", str(_Path(__file__).resolve().parent))) / "app.ico"
            if _ico.is_file():
                root.iconbitmap(default=str(_ico))
        except Exception:
            pass
        root.minsize(920, 720)

        self.files: list[Path] = []
        self.out_dir: Path = Path("compressed").resolve()
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.preview_job: str | None = None
        self.preview_poll_job: str | None = None
        self.preview_q: queue.Queue = queue.Queue()

        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # ===== 左侧: 操作区 =====
        left = ttk.Frame(paned)
        paned.add(left, weight=3)

        top = ttk.Frame(left)
        top.pack(fill="x", pady=(0, 4))
        ttk.Button(top, text="选文件", width=10, command=self.pick_files).pack(side="left", padx=2)
        ttk.Button(top, text="选文件夹", width=10, command=self.pick_dir).pack(side="left", padx=2)
        ttk.Button(top, text="清空列表", width=10, command=self.clear_files).pack(side="left", padx=2)
        self.file_label = ttk.Label(top, text="已选 0 张图", foreground="#666")
        self.file_label.pack(side="right")

        list_frame = ttk.LabelFrame(left, text="待压缩文件 (可拖图片/文件夹进窗口, 也可多次按钮选, 累加)", padding=4)
        list_frame.pack(fill="x", pady=4)
        self.listbox = tk.Listbox(list_frame, height=4, font=("Consolas", 9))
        self.listbox.pack(fill="x")
        # v6: 接 OS 文件拖拽, 整个根窗口都能拖进来
        if HAS_DND:
            try:
                self.listbox.drop_target_register(DND_FILES)
                self.listbox.dnd_bind("<<Drop>>", self._on_drop)
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

        preset_frame = ttk.LabelFrame(left, text="★ 一键预设 (默认=推荐压缩 q=85)", padding=6)
        preset_frame.pack(fill="x", pady=4)
        # 预设按 PRESET_ROWS 分 3 行显示 (行宽上限 4, 再多 Tk 会挤到截断)
        for row_names in PRESET_ROWS:
            row = ttk.Frame(preset_frame)
            row.pack(fill="x")
            # ⚠ 绝对不要在这里写死 width=15。
            #   ttk 的 width 是"固定多少个字符宽", 不是"至少多少"。预设名一旦
            #   超宽, ttk 既不撑宽按钮也不换行, 而是直接把尾部**截断** ——
            #   实测 133px 的名字塞在 115px 的按钮里, 结尾的 "≤200KB" 被切掉,
            #   用户看到的是 "📦 限边长1280·", 根本看不出是多少 KB 的档位。
            #   这里不传 width, 让 Tk 按文字精确自适应, 再用 grid 的 uniform
            #   让同一行的格子等宽(取本行最宽那个): 既不截断, 也不宽窄不齐。
            for i, name in enumerate(row_names):
                ttk.Button(row, text=name,
                           command=lambda n=name: self.apply_preset(n)
                           ).grid(row=0, column=i, padx=2, pady=2, sticky="ew")
                row.columnconfigure(i, weight=0, uniform="preset")
        self.preset_hint = ttk.Label(preset_frame, text="默认: ⚡ 推荐压缩 (q=85 业界甜点)",
                                      foreground="#06c", wraplength=380)
        self.preset_hint.pack(anchor="w", padx=4, pady=2)
        # 这两行图例必须独立成控件, 不能拼进 preset_hint:
        # apply_preset() 会把 preset_hint 的文字整个换成 "已选/已保存 xxx",
        # 写在 hint 里的话窗口一开就被冲掉了, 用户永远看不到。
        # 讲清楚两类预设的区别, 是让用户不点错的关键 —— 名字再短也不够。
        self.preset_legend = ttk.Label(
            preset_frame,
            text="📦 限边长xxx = 会缩小长边像素, 主图/缩略图用\n"
                 "📐 尺寸不变 = 像素/比例/边长全不动, 只压体积, A+ 各模块用",
            foreground="#c80", wraplength=380)
        self.preset_legend.pack(anchor="w", padx=4, pady=(0, 2))

        self.show_custom = tk.BooleanVar(value=False)
        self.show_custom_cb = ttk.Checkbutton(left, text="显示自定义参数 (高级用户)",
                                             variable=self.show_custom,
                                             command=self._toggle_custom)
        self.show_custom_cb.pack(anchor="w", padx=4)

        # ===== v11.4: 我的自定义预设 =====
        # 单独开一块, 不跟内置预设混在同一排按钮里:
        #   内置档位是产品定的, 用户自己存的另起一块, 一眼分得清谁是谁;
        #   内置按钮的行列是写死的(PRESET_ROWS), 插用户预设进去会把
        #   那套布局和 --preset 序号一起搞坏。
        # 一个自定义预设都没有的时候整块收起来, 不在主界面上留空框。
        self.custom_preset_frame = ttk.LabelFrame(
            left, text="★ 我的自定义预设 (自己存的, 卸载重装都在)", padding=6)
        self.custom_preset_box = ttk.Frame(self.custom_preset_frame)
        self.custom_preset_box.pack(fill="x")
        self.custom_preset_hint = ttk.Label(self.custom_preset_frame, text="",
                                             foreground="#888", wraplength=380)
        self.custom_preset_hint.pack(anchor="w", padx=4, pady=(2, 0))

        self.custom_frame = ttk.LabelFrame(left, text="自定义 (留空 = 用预设)", padding=6)
        mf = ttk.Frame(self.custom_frame)
        mf.pack(fill="x", pady=2)
        ttk.Label(mf, text="压缩模式:", width=10).pack(side="left")
        self.mode_var = tk.StringVar(value=MODE_LABELS["lossless"])
        self.mode_combo = ttk.Combobox(mf, textvariable=self.mode_var, state="readonly",
                                       values=list(MODE_LABELS.values()),
                                       width=32)
        self.mode_combo.pack(side="left", padx=4)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_param_change())

        qf = ttk.Frame(self.custom_frame)
        qf.pack(fill="x", pady=2)
        ttk.Label(qf, text="质量:", width=10).pack(side="left")
        self.quality_var = tk.IntVar(value=85)
        ttk.Scale(qf, from_=40, to=95, orient="horizontal", variable=self.quality_var,
                  command=self._on_q_change).pack(side="left", fill="x", expand=True, padx=4)
        self.q_label = ttk.Label(qf, text="85", width=4)
        self.q_label.pack(side="left")

        tf = ttk.Frame(self.custom_frame)
        tf.pack(fill="x", pady=2)
        ttk.Label(tf, text="目标体积:", width=10).pack(side="left")
        self.target_var = tk.StringVar(value="0")
        self.target_entry = ttk.Entry(tf, textvariable=self.target_var, width=8)
        self.target_entry.pack(side="left", padx=4)
        self.target_entry.bind("<KeyRelease>", lambda e: self._on_param_change())
        self.target_unit = ttk.Label(tf, text="KB (0=不限制, 只按质量压)")
        self.target_unit.pack(side="left")

        ff = ttk.Frame(self.custom_frame)
        ff.pack(fill="x", pady=2)
        ttk.Label(ff, text="输出格式:", width=10).pack(side="left")
        self.fmt_var = tk.StringVar(value="保持原格式 (推荐)")
        self.fmt_combo = ttk.Combobox(ff, textvariable=self.fmt_var, state="readonly",
                                      values=["保持原格式 (推荐)", "JPG", "PNG", "WebP"],
                                      width=18)
        self.fmt_combo.pack(side="left", padx=4)
        self.fmt_combo.bind("<<ComboboxSelected>>", lambda e: self._on_param_change())

        sf = ttk.Frame(self.custom_frame)
        sf.pack(fill="x", pady=2)
        ttk.Label(sf, text="长边限制:", width=10).pack(side="left")
        self.side_var = tk.StringVar(value="原图")
        self.side_combo = ttk.Combobox(sf, textvariable=self.side_var, state="readonly",
                                       values=["原图", "2560", "2048", "1600", "1280", "1100", "1080"],
                                       width=18)
        self.side_combo.pack(side="left", padx=4)
        self.side_combo.bind("<<ComboboxSelected>>", lambda e: self._on_param_change())

        self.exif_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.custom_frame, text="保留拍摄参数 (EXIF)",
                        variable=self.exif_var, command=self._on_param_change).pack(anchor="w")

        # ===== v11.4: 把眼前这套参数存成自己的预设 =====
        # 位置放在高级参数区的最下面: 用户一定是先调完参数才想存,
        # 存完就能在上面的「我的自定义预设」里一键复用。
        ttk.Separator(self.custom_frame).pack(fill="x", pady=(10, 6))
        savef = ttk.Frame(self.custom_frame)
        savef.pack(fill="x")
        ttk.Label(savef, text="预设名称:", width=10).pack(side="left")
        self.custom_name_var = tk.StringVar(value="")
        self.custom_name_entry = ttk.Entry(savef, textvariable=self.custom_name_var,
                                            width=18, font=("Microsoft YaHei UI", 9))
        self.custom_name_entry.pack(side="left", padx=4)
        ttk.Button(savef, text="💾 保存为自定义预设",
                   command=self.save_custom_preset).pack(side="left", padx=4)
        ttk.Label(self.custom_frame,
                  text=f"💡 存在 {_custom_presets_path()}\n"
                       f"   不在安装目录里 —— 卸载重装、换版本都还在。",
                  foreground="#888", wraplength=380, justify="left").pack(
                      anchor="w", padx=4, pady=(4, 0))

        outf = ttk.Frame(left, padding=(0, 6, 0, 0))
        outf.pack(fill="x")
        self.out_frame = outf  # 记住, 自定义面板要插在它前面
        ttk.Label(outf, text="输出:").pack(side="left")
        self.out_var = tk.StringVar(value=str(self.out_dir))
        ttk.Entry(outf, textvariable=self.out_var, font=("Consolas", 9)).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(outf, text="更改", width=6, command=self.pick_outdir).pack(side="left")

        self.start_btn = tk.Button(
            left, text="▶  开始压缩", font=("Microsoft YaHei", 12, "bold"),
            bg="#2d8cf0", fg="white", activebackground="#1e7bd9", activeforeground="white",
            relief="flat", height=2, command=self.start,
        )
        self.start_btn.pack(fill="x", pady=6)

        # v11: 设置入口 + 备份入口
        srow = ttk.Frame(left)
        srow.pack(fill="x", pady=(0, 2))
        ttk.Button(srow, text="⚙ 设置",
                   command=self.open_settings).pack(side="left")
        ttk.Button(srow, text="↩︎ 备份/还原",
                   command=lambda: self.restore_window(self.root)).pack(side="left", padx=6)
        self._settings_hint = ttk.Label(srow, text="", font=("Microsoft YaHei", 8),
                                        foreground="#888")
        self._settings_hint.pack(side="left", padx=4)
        self._refresh_settings_hint()

        prog = ttk.Frame(left)
        prog.pack(fill="x")
        self.progress = ttk.Progressbar(prog, mode="determinate")
        self.progress.pack(fill="x")
        self.prog_label = ttk.Label(prog, text="")
        self.prog_label.pack(anchor="e")

        log_frame = ttk.LabelFrame(left, text="处理日志", padding=4)
        log_frame.pack(fill="both", expand=True, pady=4)
        self.log = tk.Text(log_frame, height=8, font=("Consolas", 9), wrap="none")
        scroll_y = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll_y.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        # ===== 右侧: 预览 =====
        right = ttk.Frame(paned, padding=(8, 0, 0, 0))
        paned.add(right, weight=4)

        ttk.Label(right, text="🔍 实时参数预览", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", pady=(0, 4))

        prev_info = ttk.LabelFrame(right, text="样本图信息", padding=8)
        prev_info.pack(fill="x", pady=4)
        self.prev_sample_name = ttk.Label(prev_info, text="(未选图)", foreground="#666", wraplength=240)
        self.prev_sample_name.pack(anchor="w")
        self.prev_sample_size = ttk.Label(prev_info, text="", font=("Consolas", 9),
                                          wraplength=250)
        self.prev_sample_size.pack(anchor="w", pady=(2, 0))

        prev_size_frame = ttk.LabelFrame(right, text="按当前参数预估", padding=8)
        prev_size_frame.pack(fill="x", pady=4)
        self.prev_arrow = ttk.Label(prev_size_frame, text="", font=("Consolas", 10))
        self.prev_arrow.pack(anchor="w")
        self.prev_new = ttk.Label(prev_size_frame, text="", font=("Consolas", 14, "bold"), foreground="#06c")
        self.prev_new.pack(anchor="w", pady=(2, 0))
        self.prev_ratio = ttk.Label(prev_size_frame, text="", font=("Consolas", 11))
        self.prev_ratio.pack(anchor="w", pady=(2, 0))
        self.prev_note = ttk.Label(prev_size_frame, text="", foreground="#999", wraplength=240)
        self.prev_note.pack(anchor="w", pady=(4, 0))

        prev_settings_frame = ttk.LabelFrame(right, text="当前参数", padding=8)
        prev_settings_frame.pack(fill="x", pady=4)
        self.prev_settings = ttk.Label(prev_settings_frame, text="", font=("Consolas", 9),
                                           justify="left", wraplength=260)
        self.prev_settings.pack(anchor="w")

        ttk.Label(
            right,
            text="💡 默认=推荐压缩 (q=85 业界甜点).\n"
                 "   目标体积档自动二分搜索最高能达标的质量:\n"
                 "     📦 会把长边缩到 1280/1100; 📐 尺寸比例边长一个像素都不动.\n"
                 "   原图只读, 永不覆盖; 输出同名会自动加 _compressed 后缀.\n"
                 "   预览用内存压缩, 不写盘不污染输出.",
            foreground="#999", wraplength=240, justify="left",
        ).pack(anchor="w", pady=8)

        self.status = ttk.Label(root, text="就绪", relief="sunken", anchor="w", padding=(8, 2))
        self.status.pack(fill="x", side="bottom")

        # 默认应用 - 用户选定 q=85 甜点
        # 用索引找避免中文名在 GBK 环境出问题
        default_preset = next((k for k in PRESETS if "推荐" in k), "⚡ 推荐压缩")
        self.apply_preset(default_preset, silent=True)
        self._refresh_custom_presets()
        self._refresh_preview()

    def _toggle_custom(self):
        if self.show_custom.get():
            # 插到输出目录栏前面 (靠 self.out_frame 定位, 别用 out_var.master)
            self.custom_frame.pack(fill="x", padx=0, pady=4, before=self.out_frame)
        else:
            self.custom_frame.pack_forget()

    def _on_q_change(self, _evt=None):
        if hasattr(self, "q_label"):
            self.q_label.config(text=str(int(self.quality_var.get())))
        self._refresh_preview()

    def _on_param_change(self, *_):
        self._refresh_preview()

    # ------------------------------------------------------------
    #  v11.4 自定义预设: 存 / 改名 / 删 / 应用
    # ------------------------------------------------------------
    def _refresh_custom_presets(self):
        """重建「我的自定义预设」区. 增删改之后都要调一次."""
        for w in self.custom_preset_box.winfo_children():
            w.destroy()
        items = load_custom_presets()
        if not items:
            # 一个都没有就把整块收起来, 别在主界面上留个空框
            self.custom_preset_frame.pack_forget()
            return
        for name, spec in items.items():
            row = ttk.Frame(self.custom_preset_box)
            row.pack(fill="x", pady=1)
            ttk.Button(row, text=name,
                       command=lambda n=name: self.apply_preset(n)
                       ).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="✎", width=3,
                       command=lambda n=name: self.rename_custom_preset(n)
                       ).pack(side="left", padx=2)
            ttk.Button(row, text="🗑", width=3,
                       command=lambda n=name: self.delete_custom_preset(n)
                       ).pack(side="left")
        self.custom_preset_hint.config(
            text=f"共 {len(items)} 个 · 存在 {_custom_presets_path()}")
        # 必须带 before=show_custom_cb: pack 不带 before 就是"排到最后",
        # 重新显示时会掉到窗口最底下, 位置跟第一次进来时不一样。
        self.custom_preset_frame.pack(fill="x", pady=4,
                                      before=self.show_custom_cb)

    def save_custom_preset(self):
        """把当前高级参数存成一个具名预设."""
        name = str(self.custom_name_var.get() or "").strip()
        if not name:
            messagebox.showwarning("图瘦身", "先给这个预设起个名字。", parent=self.root)
            return
        if len(name) > 24:
            messagebox.showwarning("图瘦身",
                                   "名字太长了 (最多 24 个字), 换个短一点的。",
                                   parent=self.root)
            return
        if name in PRESETS:
            messagebox.showwarning(
                "图瘦身",
                f"“{name}” 是内置预设的名字, 不能覆盖。\n换个名字就行。",
                parent=self.root)
            return
        items = load_custom_presets()
        if name in items:
            if not messagebox.askyesno(
                    "图瘦身",
                    f"已经有一个叫 “{name}” 的自定义预设了。\n"
                    f"要用现在的参数覆盖它吗?",
                    parent=self.root):
                return
        mode, quality, fmt, max_side, keep_exif, target_kb = self._resolve_params()
        spec = {"mode": mode, "quality": quality, "target_kb": target_kb,
                "format": fmt, "max_side": max_side, "keep_exif": keep_exif}
        items[name] = spec
        if not save_custom_presets(items):
            messagebox.showerror(
                "图瘦身",
                f"预设保存失败, 权限不足?\n\n{_custom_presets_path()}",
                parent=self.root)
            return
        self.custom_name_var.set("")
        self._refresh_custom_presets()
        self.apply_preset(name)
        self._log(f">>> 已保存自定义预设: {name}  ({describe_preset(spec)})\n"
                  f"    存在 {_custom_presets_path()}\n")

    def rename_custom_preset(self, name: str):
        items = load_custom_presets()
        if name not in items:
            return
        new = simpledialog.askstring("重命名预设", "新名字:",
                                      initialvalue=name, parent=self.root)
        if not new:
            return
        new = str(new).strip()
        if not new or new == name:
            return
        if len(new) > 24:
            messagebox.showwarning("图瘦身", "名字太长了 (最多 24 个字)。",
                                   parent=self.root)
            return
        if new in PRESETS:
            messagebox.showwarning("图瘦身",
                                   f"“{new}” 是内置预设的名字, 换个名字。",
                                   parent=self.root)
            return
        if new in items:
            messagebox.showwarning("图瘦身",
                                   f"已经有叫 “{new}” 的了, 换个名字。",
                                   parent=self.root)
            return
        items[new] = items.pop(name)
        # ⚠ 顺序很重要: 必须**先**判断"设置里是不是指向它", 再改磁盘。
        #   改完磁盘旧名就没了, 这时候 _load_settings() 读到旧名会判非法
        #   并静默回落成默认档, 于是引用断了, 右键默认悄悄变回「推荐压缩」。
        #   _raw_settings() 绕开回落, 拿到的才是真正的旧值。
        raw = _raw_settings()
        was_default = (raw.get("preset") == name)
        if not save_custom_presets(items):
            messagebox.showerror("图瘦身", "改名失败, 权限不足?", parent=self.root)
            return
        if was_default:
            try:
                s = _load_settings()
                s["preset"] = new
                _save_settings(s)
                self._refresh_settings_hint()
            except Exception:
                pass
        self._refresh_custom_presets()
        self._log(f">>> 自定义预设已改名: {name} → {new}\n")

    def delete_custom_preset(self, name: str):
        if not messagebox.askyesno("图瘦身", f"删掉自定义预设 “{name}”?",
                                   parent=self.root):
            return
        items = load_custom_presets()
        if name not in items:
            return
        # 同上: 先用原始值判断, 再改磁盘
        raw = _raw_settings()
        was_default = (raw.get("preset") == name)
        items.pop(name, None)
        if not save_custom_presets(items):
            messagebox.showerror("图瘦身", "删除失败, 权限不足?", parent=self.root)
            return
        # 正好是右键默认预设的话, 退回内置默认, 不留一个指向空名字的引用
        if was_default:
            try:
                s = _load_settings()
                s["preset"] = V9_FALLBACK_PRESET
                _save_settings(s)
                self._refresh_settings_hint()
            except Exception:
                pass
        self._refresh_custom_presets()
        self._log(f">>> 已删除自定义预设: {name}\n")

    def apply_preset(self, name: str, silent: bool = False):
        # all_presets() = 内置 + 用户自定义。内置的 10 个是常量表,
        # 自定义的在磁盘上, 所以这里必须走合并后的表。
        p = all_presets().get(name)
        if not p:
            return
        self.mode_var.set(MODE_LABELS[p["mode"]])
        self.quality_var.set(p.get("quality", 85))
        self.q_label.config(text=str(self.quality_var.get()))
        fmt_label = {"keep": "保持原格式 (推荐)", "jpg": "JPG",
                     "png": "PNG", "webp": "WebP"}.get(p.get("format", "keep"),
                                                       "保持原格式 (推荐)")
        self.fmt_var.set(fmt_label)
        side_label = "原图" if p.get("max_side", 0) == 0 else str(p["max_side"])
        if side_label not in self.side_combo["values"]:
            self.side_combo["values"] = list(self.side_combo["values"]) + [side_label]
        self.side_var.set(side_label)
        self.exif_var.set(p.get("keep_exif", False))
        self.target_var.set(str(p.get("target_kb", 0)))
        self.preset_hint.config(text=f"已选: {name}  ({p['desc']})")
        if not silent:
            # v9: 手动换预设时记一笔, 右键快捷入口下次就直接用这个
            _v9_save_preset(name)
            # 保存后必须刷新那行"右键菜单默认"。不刷新的话它永远停在旧值,
            # 用户点了预设、文件也写了, 但界面上看不出任何变化 —— 会被当成
            # "没保存", 每次都以为是默认值。
            self._refresh_settings_hint()
            self.preset_hint.config(
                text=f"✓ 已保存为右键默认: {name}  ({p['desc']})")
            self._log(f">>> 预设: {name}  ({p['desc']})"
                      f" —— 已保存, 右键菜单下次就用它\n")
        self._refresh_preview()

    def pick_files(self):
        paths = filedialog.askopenfilenames(
            title="选图片 (可多选)",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"), ("全部", "*.*")],
        )
        if not paths:
            return
        self._add_paths([Path(p) for p in paths])

    def _add_paths(self, paths: list[Path]):
        """把一批路径加进队列, 文件夹会递归展平. 拖拽也走这里."""
        added = 0
        for p in paths:
            if p.is_dir():
                for sub in sorted(p.rglob("*")):
                    if sub.is_file() and sub.suffix.lower() in SUPPORTED and sub not in self.files:
                        self.files.append(sub)
                        added += 1
            elif p.is_file() and p.suffix.lower() in SUPPORTED and p not in self.files:
                self.files.append(p)
                added += 1
        if added:
            self._refresh_list()
            self._refresh_preview()
            self.status.config(text=f"已选 {len(self.files)} 张图 (+{added})")
        elif self.files:
            self.status.config(text=f"已选 {len(self.files)} 张图 (拖入无新文件)")

    def _raise_to_front(self):
        """把主窗口顶到最前面。右键加了图, 用户得马上看见。"""
        try:
            self.root.lift()
            self.root.focus_force()
            # Windows 上光靠 focus_force 常常抢不到前台, 要 topmost 闪一下
            self.root.attributes("-topmost", True)
            self.root.after(200, lambda: self.root.attributes("-topmost", False))
        except Exception:
            _v9_log("[inbox] 置前失败\n" + traceback.format_exc())

    def _poll_inbox(self):
        """收右键"加入压缩队列"投递过来的路径, 然后把自己排上下一轮。"""
        try:
            got = _v9_drain_inbox()
            if got:
                paths = _v9_expand(got)
                if paths:
                    self._add_paths(paths)
                    self._raise_to_front()
        except Exception:
            # 轮询里任何异常都必须吞掉, 否则 Tk 的 after 链断掉,
            # 右键投递就从此静默失效 —— 正好是这个功能最不能出的错。
            _v9_log("[inbox] 轮询异常\n" + traceback.format_exc())
        self.root.after(V9_INBOX_POLL_MS, self._poll_inbox)

    def _on_drop(self, event):
        """tkinterdnd2 <<Drop>> 回调.

        tkdnd 在 Windows 上送来的 data 是 Tcl 列表字面量:
        带空格的路径会用花括号包起来, 如 '{C:/My Pictures/a b.jpg} {C:/x.png}'.
        用 tk.splitlist 解析最稳 (同时处理花括号、反斜杠转义、无空格裸路径);
        万一 tkdnd 送的不是合法 Tcl 列表, 再退回正则兜底.
        """
        if not HAS_DND:
            return None
        raw = getattr(event, "data", "") or ""
        paths: list[Path] = []
        try:
            paths = [Path(p) for p in self.root.tk.splitlist(raw) if p]
        except Exception:
            paths = []
        if not paths:
            import re
            parts = re.findall(r"\{([^}]+)\}|(\S+)", raw)
            paths = [Path(a or b) for a, b in parts if (a or b)]
        # 过滤掉不存在的路径 (虚拟文件 .lnk / 拖拽残留)
        paths = [p for p in paths if p.exists()]
        # 兜底: 万一送来的就是一条裸路径 (带空格却没加花括号), 上面会被切碎成几段垃圾.
        # 这时把整串当一个路径再试一次, 存在就认.
        if not paths and raw.strip():
            whole = Path(raw.strip())
            if whole.exists():
                paths = [whole]
        if paths:
            self._add_paths(paths)
        return "copy"

    def pick_dir(self):
        d = filedialog.askdirectory(title="选文件夹 (递归压所有图片)")
        if not d:
            return
        added = 0
        for p in sorted(Path(d).rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED and p not in self.files:
                self.files.append(p)
                added += 1
        self._refresh_list()
        self._refresh_preview()
        self.status.config(text=f"已选 {len(self.files)} 张图 (+{added})")

    def clear_files(self):
        self.files.clear()
        self._refresh_list()
        self._refresh_preview()
        self.status.config(text="已清空")

    def pick_outdir(self):
        d = filedialog.askdirectory(title="选输出文件夹", initialdir=str(self.out_dir))
        if d:
            self.out_dir = Path(d).resolve()
            self.out_var.set(str(self.out_dir))

    # ===== v11: 设置 + 备份 =====
    def _refresh_settings_hint(self):
        """在主界面提示当前默认设置, 免得用户忘了自己设成什么了."""
        try:
            cfg = _load_settings()
            txt = OUTPUT_MODE_LABELS.get(cfg["output_mode"], "")
            if cfg["output_mode"] == "fixed" and cfg.get("output_dir"):
                txt += f" → {Path(cfg['output_dir']).name}"
            self._settings_hint.config(text=f"右键菜单默认: {cfg['preset']} · {txt}")
        except Exception:
            pass

    def open_settings(self):
        """设置对话框: 记住默认值, 让右键菜单按你的习惯干活."""
        top = tk.Toplevel(self.root)
        top.title("图瘦身 — 设置")
        top.transient(self.root)
        top.resizable(False, False)
        try:
            top.iconbitmap(str(getattr(sys, "_MEIPASS", "") and
                               Path(getattr(sys, "_MEIPASS", "")) / "app.ico"
                               or ""))
        except Exception:
            pass

        cfg = _load_settings()
        f = ("Microsoft YaHei UI", 9)

        # ⚠ 必须记住的 Tk 8.6 坑: ttk::radiobutton 和 ttk::checkbutton 跟别的
        # ttk 控件不一样, 它们不接受 -font 参数, 直接 font= 会抛
        # "TclError: unknown option \"-font\"", 而这个异常发生在建控件阶段,
        # 整个 open_settings 当场死掉 —— 窗口开不起来, 用户永远看不到保存按钮,
        # 于是"选了预设没保存、每次都是默认值"。字体只能通过 Style 传。
        _st = ttk.Style(top)
        _st.configure("CfgRadio.TRadiobutton", font=f)
        _st.configure("CfgCheck.TCheckbutton", font=f)

        pad = ttk.Frame(top, padding=16)
        pad.pack(fill="both", expand=True)

        # --- 0. 顶部工具栏 (先占位, 内容在 save() 定义之后填) ---
        # 这个窗口内容很长(预设+格式+输出+备份), 在小屏/125%·150% 缩放下底部会被
        # 切到屏幕外, 保存按钮正好在最下面 = 用户根本点不到。所以顶部也放一份,
        # 并且明确写"改完要保存", 免得以为选了就生效。
        topbar = ttk.Frame(pad)
        topbar.pack(fill="x", pady=(0, 10))

        # --- 1. 右键菜单默认预设 ---
        ttk.Label(pad, text="右键菜单默认压缩到", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        ttk.Label(pad, text="在资源管理器里右键选图 →「立即压缩」时用的档位",
                  font=f, foreground="#666").pack(anchor="w", pady=(0, 4))
        # 内置 10 个在前, 用户自定义的在后面 —— 下拉里能直接选自己存的档位
        preset_names = list(PRESETS.keys()) + list(load_custom_presets().keys())
        pv = tk.StringVar(value=cfg["preset"] if cfg["preset"] in preset_names
                          else V9_FALLBACK_PRESET)
        ttk.Combobox(pad, textvariable=pv, values=preset_names,
                     state="readonly", font=f).pack(fill="x")
        ph = ttk.Label(pad, text="", font=f, foreground="#06c", wraplength=430)
        ph.pack(anchor="w", pady=(3, 0))

        def show_desc(*_):
            p = all_presets().get(pv.get())
            if p:
                ph.config(text=p.get("desc", describe_preset(p)))
        pv.trace_add("write", show_desc)
        show_desc()

        # --- 2. 默认输出格式 ---
        ttk.Separator(pad).pack(fill="x", pady=12)
        ttk.Label(pad, text="默认输出格式", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        fv = tk.StringVar(value=FORMAT_LABELS.get(cfg["format"], FORMAT_LABELS["keep"]))
        ttk.Combobox(pad, textvariable=fv, values=list(FORMAT_LABELS.values()),
                     state="readonly", font=f).pack(fill="x", pady=(4, 0))

        # --- 3. 默认输出位置 ---
        ttk.Separator(pad).pack(fill="x", pady=12)
        ttk.Label(pad, text="默认输出位置", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        ov = tk.StringVar(value=cfg["output_mode"])
        notes = {
            "suffix": "原文件夹导出，文件名加 _compressed（最安全，不动原图）",
            "overwrite": "直接覆盖原图片（覆盖前自动备份，可还原）",
            "fixed": "统一导出到你指定的固定目录",
        }
        # 三个输出模式单选框: 一律永远可点(见 on_mode 里的说明)。
        # 互斥由共享的 variable=ov 自动完成, 不需要、也不允许在这里 disable 任何一个。
        for key in OUTPUT_MODES:
            ttk.Radiobutton(pad, text=OUTPUT_MODE_LABELS[key], value=key,
                            variable=ov, style="CfgRadio.TRadiobutton").pack(
                anchor="w", fill="x")

        dirf = ttk.Frame(pad)
        dirf.pack(fill="x", pady=(4, 0))
        dv = tk.StringVar(value=str(cfg.get("output_dir") or ""))
        ttk.Label(dirf, text="固定目录:").pack(side="left")
        ttk.Entry(dirf, textvariable=dv, font=("Consolas", 9)).pack(
            side="left", fill="x", expand=True, padx=4)

        def browse_fixed():
            d = filedialog.askdirectory(title="选固定输出目录",
                                        initialdir=dv.get() or str(Path.home()))
            if d:
                dv.set(d)

        ttk.Button(dirf, text="浏览", width=6, command=browse_fixed).pack(side="left")
        warn = ttk.Label(pad, text="", font=f, foreground="#c0392b", wraplength=430)
        warn.pack(anchor="w", pady=(4, 0))

        ackv = tk.BooleanVar(value=bool(cfg.get("overwrite_ack")))
        ackb = ttk.Checkbutton(
            pad, text="我知道「覆盖原图」有风险（覆盖前会自动备份，出问题能还原）",
            variable=ackv, style="CfgCheck.TCheckbutton")
        ackb.pack(anchor="w", pady=(6, 0))

        def on_mode(*_):
            # ⚠ 这里绝对不要再去 disable 三个单选框中的"非选中项"。
            # 踩过的坑: 旧代码在 m == "fixed" 时把另外两个单选框 state(["disabled"]),
            # 想着"固定目录模式是排他选择"——结果用户自己的设置停在 fixed 时,
            # 一打开设置窗口「原文件夹导出」「覆盖原图」就是灰的, 点不动,
            # 整个输出模式看起来"没法选"(tkinter 的禁用态是灰字, 不是消失,
            # 所以用户报的是"没有这个选项/不能选")。
            # 单选互斥本来就由共享的 variable=ov 自动完成, 三个框必须永远可点。
            # 真正该跟着模式开关的是下面的"固定目录"输入框和覆盖确认勾选框。
            m = ov.get()
            dirf.state(["disabled"] if m != "fixed" else ["!disabled"])
            warn.config(text=notes.get(m, ""))
            if m == "overwrite":
                ackb.state(["!disabled"])
            else:
                ackb.state(["disabled"])

        ov.trace_add("write", on_mode)
        on_mode()

        # --- 4. 备份 ---
        ttk.Separator(pad).pack(fill="x", pady=12)
        sessions = _backup_sessions()
        bcount = sum(len(it) for _, it in sessions)
        ttk.Label(pad, text="备份", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        ttk.Label(pad, text=f"共 {len(sessions)} 批 · {bcount} 个文件 · 位置 {_backup_root()}",
                  font=f, foreground="#666", wraplength=430).pack(anchor="w", pady=(0, 4))
        bframe = ttk.Frame(pad)
        bframe.pack(fill="x")

        def open_bak():
            d = _backup_root()
            d.mkdir(parents=True, exist_ok=True)
            try:
                os.startfile(str(d))
            except Exception as e:
                messagebox.showerror("图瘦身", f"打不开: {e}", parent=top)

        ttk.Button(bframe, text="📂 打开备份目录", command=open_bak).pack(side="left")
        ttk.Button(bframe, text="↩︎ 从备份还原…",
                   command=lambda: self.restore_window(top)).pack(side="left", padx=8)

        # --- 保存 ---
        ttk.Separator(pad).pack(fill="x", pady=12)
        btns = ttk.Frame(pad)
        btns.pack(fill="x")

        def save():
            mode = ov.get()
            fdir = dv.get().strip()
            if mode == "fixed" and not fdir:
                messagebox.showwarning("图瘦身", "选了「固定目录」但没填目录。", parent=top)
                return
            if mode == "fixed":
                try:
                    Path(fdir).expanduser().mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("图瘦身", f"这个目录建不了: {e}", parent=top)
                    return
            new = {
                "preset": pv.get(),
                "format": {v: k for k, v in FORMAT_LABELS.items()}.get(fv.get(), "keep"),
                "output_mode": mode,
                "output_dir": fdir,
                "overwrite_ack": bool(ackv.get()),
            }
            if _save_settings(new):
                self._log(f">>> 设置已保存: 预设={new['preset']} 格式={new['format']} "
                          f"输出={OUTPUT_MODE_LABELS[new['output_mode']]}\n")
                # 主界面那行"右键菜单默认"要跟着刷新, 否则关了设置窗口后
                # 它还显示旧值, 用户会以为没保存
                self._refresh_settings_hint()
                messagebox.showinfo(
                    "图瘦身",
                    f"已保存。\n\n"
                    f"右键菜单默认预设: {new['preset']}\n"
                    f"输出位置: {OUTPUT_MODE_LABELS[new['output_mode']]}\n\n"
                    f"以后在资源管理器里右键选图, 就按这个来。",
                    parent=top)
                top.destroy()
            else:
                messagebox.showerror("图瘦身", "设置保存失败，权限不足？", parent=top)

        ttk.Button(btns, text="保存", command=save).pack(side="right")
        ttk.Button(btns, text="取消", command=top.destroy).pack(side="right", padx=6)

        # 顶部那份(见前面 topbar 的说明): 底部那个在矮屏幕上会被切出屏幕外
        ttk.Button(topbar, text="💾 保存并关闭", command=save).pack(side="right")
        ttk.Button(topbar, text="取消", command=top.destroy).pack(side="right", padx=6)
        ttk.Label(topbar, text="⚠ 这里改的是「右键菜单」的默认行为, 改完要点保存才生效",
                  font=("Microsoft YaHei UI", 8), foreground="#c0392b"
                  ).pack(side="left")

        top.bind("<Escape>", lambda e: top.destroy())
        top.update_idletasks()
        w = top.winfo_reqwidth()
        h = top.winfo_reqheight()
        top.geometry(f"{max(w, 480)}x{h}")

    def restore_window(self, parent):
        """挑一个备份批次还原回去."""
        sessions = _backup_sessions()
        if not sessions:
            messagebox.showinfo(
                "图瘦身",
                "还没有任何备份。\n\n"
                "只有当你把默认输出位置设成「覆盖原图」并真的覆盖过时，\n"
                "这里才会有可还原的东西。", parent=parent)
            return

        top = tk.Toplevel(self.root)
        top.title("图瘦身 — 从备份还原")
        top.transient(parent)
        top.geometry("620x380")
        f = ("Microsoft YaHei UI", 9)

        ttk.Label(top, text="选一个批次还原回原位置",
                  font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        ttk.Label(top, text="还原前会再存一份当前版本，所以还原本身也可以反悔。",
                  font=f, foreground="#666").pack(anchor="w", padx=12)

        lb = tk.Listbox(top, font=("Consolas", 9), activestyle="dotbox")
        lb.pack(fill="both", expand=True, padx=12, pady=8)
        for d, items in sessions:
            total = sum(int(i.get("backup_size") or 0) for i in items)
            lb.insert("end", f"{d.name}    {len(items)} 个文件    {human_size(total)}")
        lb.selection_set(0)

        detail = ttk.Label(top, text="", font=f, foreground="#666",
                           wraplength=580, justify="left")
        detail.pack(anchor="w", padx=12)

        def show_detail(*_):
            sel = lb.curselection()
            if not sel:
                return
            d, items = sessions[sel[0]]
            if items and items[0].get("legacy"):
                detail.config(text=f"（这一批没有清单文件，还原需要你手动指定原位置）")
            else:
                detail.config(text="\n".join(
                    f"  {i.get('backup')}  ←  {i.get('original')}" for i in items[:6])
                    + ("\n  …" if len(items) > 6 else ""))
        lb.bind("<<ListboxSelect>>", show_detail)
        lb.bind("<<Listbox>>", lambda e: detail.config(text=""))
        show_detail()

        def do_restore():
            sel = lb.curselection()
            if not sel:
                return
            d, items = sessions[sel[0]]
            if any(i.get("legacy") for i in items):
                messagebox.showwarning(
                    "图瘦身", "这一批没有还原清单，只能自己从备份目录里拷文件。\n\n"
                              "已为你打开备份目录。", parent=top)
                try:
                    os.startfile(str(d))
                except Exception:
                    pass
                return
            if not messagebox.askyesno(
                    "确认还原",
                    f"把 {len(items)} 个文件还原回原位置？\n\n"
                    "原图会被覆盖回压缩前的样子。\n"
                    "还原前会自动再存一份当前版本。", parent=top):
                return
            ok, bad = _restore_backup(d, items)
            self._log(f">>> 还原: 成功 {ok} · 失败 {bad}  (批次 {d.name})\n")
            messagebox.showinfo("图瘦身",
                                f"还原完成。\n成功 {ok} 个 · 失败 {bad} 个", parent=top)
            top.destroy()

        btns = ttk.Frame(top)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="↩︎ 还原这一批", command=do_restore).pack(side="left")
        ttk.Button(btns, text="打开这个备份目录", command=lambda: os.startfile(
            str(sessions[lb.curselection()[0]][0])) if lb.curselection() else None
        ).pack(side="left", padx=8)
        ttk.Button(btns, text="关闭", command=top.destroy).pack(side="right")

    def _open_backup_dir(self):
        d = _backup_root()
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(d))
        except Exception as e:
            messagebox.showerror("图瘦身", f"打不开备份目录: {e}", parent=self.root)

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for f in self.files:
            try:
                sz = human_size(f.stat().st_size)
            except OSError:
                sz = "?"
            self.listbox.insert("end", f"  {f.name}    ({sz})")
        total = sum(f.stat().st_size for f in self.files if f.exists())
        self.file_label.config(text=f"已选 {len(self.files)} 张  ·  共 {human_size(total)}")

    def _resolve_params(self):
        mode = MODE_LABELS_REV.get(self.mode_var.get(), "lossless")
        q = int(self.quality_var.get())
        fmt = {"保持原格式 (推荐)": "keep", "JPG": "jpg",
               "PNG": "png", "WebP": "webp"}.get(self.fmt_var.get(), "keep")
        side = {"原图": 0, "2560": 2560, "2048": 2048, "1600": 1600,
                "1280": 1280, "1100": 1100, "1080": 1080}.get(self.side_var.get(), 0)
        try:
            target_kb = max(0, int(str(self.target_var.get()).strip() or 0))
        except ValueError:
            target_kb = 0
        # 目标体积 > 0 就自动切到"目标大小"模式 (手动填了也别忘了生效)
        if target_kb > 0 and mode != "target":
            mode = "target"
        return mode, q, fmt, side, self.exif_var.get(), target_kb

    def _refresh_preview(self):
        # 取消"防抖"定时器和"轮询"定时器 — 少了后者, 快速切参数会攒出一堆
        # 互相抢同一个 queue 的 _poll_preview 循环, 永远停不下来
        for attr in ("preview_job", "preview_poll_job"):
            job = getattr(self, attr, None)
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)
        self.preview_job = self.root.after(300, self._run_preview)

    def _run_preview(self):
        self.preview_job = None
        sample = next((f for f in self.files if f.exists() and f.stat().st_size > 0), None)
        if not sample:
            self.prev_sample_name.config(text="(未选图)", foreground="#666")
            self.prev_sample_size.config(text="")
            self.prev_arrow.config(text="")
            self.prev_new.config(text="(空)", foreground="#666")
            self.prev_ratio.config(text="")
            self.prev_note.config(text="")
            self.prev_settings.config(text="")
            return

        mode, quality, fmt_arg, max_side, keep_exif, target_kb = self._resolve_params()
        save_fmt, _ = pick_output_format(sample, fmt_arg)
        src_bytes = sample.stat().st_size
        try:
            with Image.open(sample) as im:
                w, h = im.size
        except Exception:
            w, h = 0, 0

        self.prev_sample_name.config(
            text=f"{sample.name[:30]}{'...' if len(sample.name) > 30 else ''}",
            foreground="#000")
        self.prev_sample_size.config(
            text=f"原: {human_size(src_bytes)}  ·  {w}×{h}px")
        self.prev_arrow.config(text="  按当前参数预估 →")
        self.prev_new.config(text="  压缩中...", foreground="#999")
        self.prev_ratio.config(text="")
        self.prev_note.config(text="")

        if mode == "target":
            mode_text = f"目标体积 ≤ {target_kb}KB (自动降质量)"
        elif mode == "lossless":
            mode_text = "无损 (不重编码 quality)"
        else:
            mode_text = f"{'均衡' if mode == 'balanced' else '激进'} q={quality}"
        self.prev_settings.config(
            text=f"  模式: {mode_text}\n"
                 f"  格式: {fmt_arg}  (保存为 {save_fmt})\n"
                 f"  长边: {max_side or '原图'}\n"
                 f"  EXIF: {'保留' if keep_exif else '丢弃'}\n"
                 f"  原图只读, 输出同名不覆盖原图"
        )

        sample_path = sample

        def work():
            new_size, err = compress_to_bytes(
                sample_path, mode, quality, save_fmt, max_side, keep_exif, target_kb)
            self.preview_q.put((new_size, err, src_bytes, mode, target_kb))

        threading.Thread(target=work, daemon=True).start()
        self.preview_poll_job = self.root.after(50, self._poll_preview)

    def _poll_preview(self):
        self.preview_poll_job = None
        try:
            new_size, err, src_bytes, mode, target_kb = self.preview_q.get_nowait()
        except queue.Empty:
            self.preview_poll_job = self.root.after(50, self._poll_preview)
            return

        if err:
            self.prev_new.config(text=f"  {err}", foreground="#c00")
            self.prev_ratio.config(text="")
            return

        if mode == "target" and target_kb > 0:
            hit = new_size <= target_kb * 1024
            self.prev_new.config(
                text=f"  ~ {human_size(new_size)}  /  目标 {target_kb}KB",
                foreground="#0a0" if hit else "#c80")
            if new_size >= src_bytes:
                self.prev_ratio.config(text="")
                self.prev_note.config(text="原图本来就小于目标, 不会压 (免得白掉画质)")
            elif hit:
                self.prev_ratio.config(text="  ✓ 已压进目标以内")
                self.prev_note.config(text="程序会自动二分搜索最高能达标的质量")
            else:
                self.prev_ratio.config(text="  ✗ 降到底仍超标")
                self.prev_note.config(
                    text=f"已用最低质量(q{TARGET_MIN_Q})尽力压到 {human_size(new_size)}, "
                         f"想更小就手动调小长边")
            return

        ratio = (1 - new_size / src_bytes) * 100 if src_bytes else 0
        if new_size < src_bytes * 0.95:
            color, note = "#0a0", "压完比原图小, 会被采用 (质量几乎不损)"
        elif new_size < src_bytes:
            color, note = "#c80", "压完差不多, 智能回退会保留原图"
        else:
            color, note = "#c00", "压完反而大, 智能回退保留原图"

        self.prev_new.config(text=f"  ~ {human_size(new_size)}", foreground=color)
        sign = "-" if ratio >= 0 else "+"
        self.prev_ratio.config(text=f"  变化: {sign}{abs(ratio):.1f}%")
        self.prev_note.config(text=note)

    def start(self):
        if not self.files:
            messagebox.showwarning("没图", "请先 [选文件] 或 [选文件夹]")
            return
        if self.worker and self.worker.is_alive():
            return

        mode, quality, fmt_arg, max_side, keep_exif, target_kb = self._resolve_params()
        out_root = Path(self.out_var.get()).resolve()
        out_root.mkdir(parents=True, exist_ok=True)

        self.log.delete("1.0", "end")
        if mode == "target":
            mode_text = f"目标体积 ≤ {target_kb}KB (自动二分降质量)"
        elif mode == "lossless":
            mode_text = "无损 (不重编码 quality)"
        else:
            mode_text = f"{'均衡' if mode == 'balanced' else '激进'} q={quality}"
        self._log(f">>> 输出目录: {out_root}\n")
        self._log(f">>> 模式: {mode_text}  格式: {fmt_arg}  长边: {max_side or '原图'}  EXIF: {keep_exif}\n")
        self._log(f">>> 安全: 原图只读永不覆盖; 输出同名则自动加 _compressed 后缀\n")
        if mode != "target":
            self._log(f">>> 智能回退: 压完 < 原图 95% 才写文件, 否则保留原图\n")
        self._log("-" * 60 + "\n")

        self.progress["maximum"] = len(self.files)
        self.progress["value"] = 0
        self.prog_label.config(text=f"0 / {len(self.files)}")
        self.start_btn.config(state="disabled", text="⏳ 压缩中...")
        self.status.config(text="正在压缩...")

        def work():
            total_in = total_out = ok = skip = fail = 0
            missed_target = 0
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {}
                for src in self.files:
                    save_fmt, ext = pick_output_format(src, fmt_arg)
                    futures[ex.submit(
                        compress_one, src, out_root, mode, quality,
                        save_fmt, ext, max_side, keep_exif, True, target_kb
                    )] = src
                for fut in as_completed(futures):
                    src = futures[fut]
                    out_path, ib, ob, msg = fut.result()
                    if msg.startswith("ok"):
                        ratio = (1 - ob / ib) * 100 if ib else 0
                        extra = msg[2:].lstrip("|")
                        tail = f"  {extra}" if extra else ""
                        line = (f"  [OK]   {src.name}\n"
                                f"         {human_size(ib)} -> {human_size(ob)}  (-{ratio:.1f}%)"
                                f"  ->  {out_path.name}{tail}\n")
                        total_in += ib; total_out += ob; ok += 1
                        if "未达标" in msg:
                            missed_target += 1
                    elif "跳过" in msg:
                        line = f"  [跳过] {src.name}    {msg}\n"
                        skip += 1
                    else:
                        line = f"  [失败] {src.name}    {msg}\n"
                        fail += 1
                    self.q.put(("log", line))
                    self.q.put(("progress", ok + skip + fail))
            self.q.put(("done", (ok, skip, fail, total_in, total_out, missed_target)))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.root.after(100, self._poll)

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                    self.prog_label.config(text=f"{payload} / {len(self.files)}")
                elif kind == "done":
                    ok, skip, fail, ti, to, missed = payload
                    self._log("-" * 60 + "\n")
                    if ti:
                        saved = ((ti - to) / ti * 100)
                        self._log(f"完成: ✓压缩{ok}  ↷跳过{skip}  ✗失败{fail}\n"
                                  f"      总原大小 {human_size(ti)} -> 压后 {human_size(to)}  (净省 {saved:.1f}%)\n")
                    else:
                        self._log(f"完成: ✓压缩0  ↷跳过{skip}  ✗失败{fail}\n"
                                  f"      这批图都没动 — 太小, 或剥元数据后没省下空间, 原样保留\n")
                    if missed:
                        self._log(f"      ⚠ {missed} 张降到最低质量仍未达目标体积, 建议手动调小长边\n")
                    self.start_btn.config(state="normal", text="▶  开始压缩")
                    if fail == 0 and (ok + skip) > 0:
                        if ok == 0:
                            self.status.config(text=f"全部跳过 ({skip} 张压不动)")
                            messagebox.showinfo(
                                "没压",
                                f"{skip} 张全部原样保留:\n"
                                f"· 小于 50KB 的不压\n"
                                f"· 无损预设: 这批图没 EXIF 可剥, 省不下空间\n\n"
                                f"想真压, 换 ⚡ 推荐压缩 或 📦 限边长1280 ≤200KB")
                        else:
                            self.status.config(text=f"搞定! 压缩 {ok}, 跳过 {skip}")
                            extra = (f"\n⚠ {missed} 张没压到目标体积 (已用最低质量), "
                                     f"想更小就手动调小长边." if missed else "")
                            messagebox.showinfo(
                                "搞定",
                                f"压缩 {ok} 张, 跳过 {skip} 张 (太小或压完更大).\n\n"
                                f"净省: {saved:.1f}%\n输出: {self.out_var.get()}{extra}")
                    elif fail > 0:
                        self.status.config(text=f"完成 (部分失败): ✓{ok} ↷{skip} ✗{fail}")
                        messagebox.showwarning("部分失败", f"成功 {ok}, 跳过 {skip}, 失败 {fail}")
                    else:
                        self.status.config(text="没有可压缩的图")
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _log(self, text: str):
        self.log.insert("end", text)
        self.log.see("end")


# ============================================================
#  V9 快捷入口 (资源管理器右键 / 发送到 / 拖到 exe 图标)
# ============================================================
#  行为约定:
#    不带参数            → 打开完整 GUI
#    带图片/文件夹路径    → 直接压缩 (走上面同一套预设引擎), 弹结果窗
#    --gui               → 打开 GUI 并把文件预载进待压缩列表 (不直接压)
#    --preset N|全名     → 指定预设 (1-10 或全名), 默认沿用 GUI 里手动选过的那个
#    --out DIR           → 输出根目录, 默认 %USERPROFILE%\picshrink_out
#    --format keep|jpg|png|webp → 覆盖预设里的输出格式
#    --no-notify         → 不弹任何窗 (给脚本 / 自动化测试用)
#    --list-presets      → 列出全部预设后退出
#
#  两个必须记住的前提:
#    1) exe 是 console=False 打包的, 没有控制台 -> 进度/结果/错误全靠自绘窗口,
#       另外落一份日志到 %TEMP%\picshrink_v9.log 方便事后查。
#    2) 输出目录 = out_root/<源文件夹名>/, 跟 GUI 里 compress_one 的策略一致,
#       不同源文件夹的同名图不会互相覆盖; 原图永远不动。
V9_DEFAULT_OUT = "picshrink_out"
V9_LOG_NAME = "picshrink_v11.log"
V9_FALLBACK_PRESET = "⚡ 推荐压缩"


def _v9_log(msg: str = "") -> None:
    """快捷入口排错日志. windowed 打包下没有 stderr, 只能落盘."""
    try:
        p = Path(os.environ.get("TEMP", ".")) / V9_LOG_NAME
        with open(p, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


def _v9_print(msg: str = "") -> None:
    """windowed 打包下 sys.stdout 可能是 None, 打印一律包起来."""
    try:
        print(msg)
    except Exception:
        pass


def _v9_config_path() -> Path:
    r"""设置文件: %LOCALAPPDATA%\图瘦身\settings.json

    v11 从 quick.json 迁过来的, 老配置会自动读进来, 不用用户重设。
    """
    return _pic_root() / "settings.json"


def _pic_root() -> Path:
    """安装目录 (%LOCALAPPDATA%\\图瘦身) —— 偏好/备份都放这儿."""
    base = os.environ.get("LOCALAPPDATA") or ""
    return (Path(base) if base else Path.home()) / "图瘦身"


def _backup_root() -> Path:
    """覆盖原图前的备份目录."""
    return _pic_root() / "备份"


# ===== 输出位置 3 种模式 =====
OUTPUT_MODES = ("suffix", "overwrite", "fixed")
OUTPUT_MODE_LABELS = {
    "suffix":    "原文件夹导出, 名字后加 _compressed (最安全)",
    "overwrite": "直接覆盖原图 (覆盖前自动备份, 可还原)",
    "fixed":     "统一导出到指定文件夹",
}

# ===== 默认输出格式 (None = 跟随预设/保持原格式) =====
FORMAT_CHOICES = ("keep", "jpg", "png", "webp")
FORMAT_LABELS = {
    "keep": "保持原格式 (推荐)",
    "jpg": "JPG — 体积最小, 丢透明",
    "png": "PNG — 无损, 支持透明",
    "webp": "WebP — 比 JPG 还小, 支持透明",
}


def _default_settings() -> dict:
    return {
        "version": 1,
        "preset": V9_FALLBACK_PRESET,
        "format": "keep",
        "output_mode": "suffix",
        "output_dir": "",
        "overwrite_ack": False,   # 用户是否已确认过"覆盖原图有风险"
    }


def _load_settings() -> dict:
    """读设置。坏了就退回默认, 绝不因为配置问题让程序起不来。"""
    s = _default_settings()
    for name in ("settings.json", "quick.json"):     # quick.json = v9 老文件
        p = _pic_root() / name
        if not p.is_file():
            continue
        try:
            import json
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            for k, v in raw.items():
                if k in s:
                    s[k] = v
            break
        except Exception:
            continue
    # 预设改名迁移: 必须先换名, 再校验。
    # 顺序反了就会出事 —— 旧名在 PRESETS 里查不到, 直接被判非法, 静默
    # 回落到默认预设, 用户会发现"我明明选的 A+900, 怎么变成推荐压缩了",
    # 而且完全不知道为什么。
    if s.get("preset") in PRESET_RENAMES:
        s["preset"] = PRESET_RENAMES[s["preset"]]
    # 逐字段校验, 配置文件是人手改的, 不能直接信
    # 注意: all_presets() = 内置 + 用户自定义。自定义预设被删了以后,
    # 这里会把它判成非法并回落到默认 —— 这是对的, 总比右键压出一个
    # 用户以为存在、其实已经没了的档位强。
    if s.get("preset") not in all_presets():
        s["preset"] = V9_FALLBACK_PRESET
    if s.get("format") not in FORMAT_CHOICES:
        s["format"] = "keep"
    if s.get("output_mode") not in OUTPUT_MODES:
        s["output_mode"] = "suffix"
    s["output_dir"] = str(s.get("output_dir") or "")
    s["overwrite_ack"] = bool(s.get("overwrite_ack"))
    return s


def _save_settings(s: dict) -> bool:
    try:
        import json
        p = _v9_config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        merged = _default_settings()
        merged.update({k: v for k, v in s.items() if k in merged})
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception:
        return False


# ============================================================
#  v11.4 用户自定义预设
#
#  为什么单独存一份, 而不是往 PRESETS 里塞:
#    PRESETS 是内置档位的常量表, 有三处硬依赖它"恰好 10 个 / 顺序固定":
#      - --preset N 按插入顺序编号, 内置档位必须永远是 1..10
#      - 界面预设按钮按 PRESET_ROWS 铺, 行列是写死的
#      - 打包后的 exe 回归会断言 len(PRESETS)==10 且名字顺序一致
#    用户自己存的档位数量会变, 塞进去会把上面三条全部搞坏。
#    所以内置表一动不动, 自定义档位单独存、单独读, 用的时候再合并。
#
#  为什么存在 %APPDATA% 而不是安装目录 (%LOCALAPPDATA%\图瘦身):
#    安装目录 = Inno 的 {app}。卸载时 Inno 会删掉自己装进去的文件;
#    更狠的是 v9_uninstall() 里那一行 shutil.rmtree(dest) ——
#    用户在卸载时点"是"的话, 整个目录连同 settings.json 一起没了。
#    用户的要求是"卸载后再装新版本, 预设还在", 所以自定义预设必须放在
#    安装器和卸载器永远碰不到的地方。
#    %APPDATA%\图瘦身\presets.json 正好满足: 安装器只写 {app},
#    卸载只删 {app} 和注册表, AppData\Roaming 下的东西一概不动。
# ============================================================

# 测试钩子: 指到临时目录, 免得测试往用户真的 %APPDATA%\图瘦身 里写东西。
# (_t_run_all.py 会把它指到临时目录, 跟 LOCALAPPDATA 隔离一个道理)
CUSTOM_PRESETS_ENV = "PICSHINK_CUSTOM_PRESETS_DIR"
CUSTOM_PRESETS_FILE = "presets.json"


def _user_data_root() -> Path:
    """用户数据目录 (%APPDATA%\\图瘦身) —— 自定义预设放这儿, 不放安装目录."""
    override = os.environ.get(CUSTOM_PRESETS_ENV)
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or ""
    return (Path(base) if base else Path.home()) / "图瘦身"


def _custom_presets_path() -> Path:
    return _user_data_root() / CUSTOM_PRESETS_FILE


def _clean_custom_preset(spec) -> dict | None:
    """校验并清洗一个自定义预设的参数. 返回 None = 这条是坏的, 直接丢掉.

    配置文件是人手改的(或者上个版本写的), 不能直接信。
    """
    if not isinstance(spec, dict):
        return None
    mode = str(spec.get("mode", "balanced"))
    if mode not in MODE_LABELS:
        mode = "balanced"
    try:
        quality = int(spec.get("quality", 85))
    except (TypeError, ValueError):
        quality = 85
    quality = max(1, min(95, quality))
    try:
        target_kb = max(0, int(spec.get("target_kb", 0)))
    except (TypeError, ValueError):
        target_kb = 0
    fmt = str(spec.get("format", "keep"))
    if fmt not in ("keep", "jpg", "png", "webp"):
        fmt = "keep"
    try:
        max_side = max(0, int(spec.get("max_side", 0)))
    except (TypeError, ValueError):
        max_side = 0
    keep_exif = bool(spec.get("keep_exif", False))
    # 目标体积 > 0 就必须是 target 模式, 否则那条目根本走不到目标分支
    if target_kb > 0:
        mode = "target"
    return {"mode": mode, "quality": quality, "target_kb": target_kb,
            "format": fmt, "max_side": max_side, "keep_exif": keep_exif}


def load_custom_presets() -> dict:
    """读用户自定义预设. 文件没了/坏了都当空, 绝不因为配置问题让程序起不来."""
    p = _custom_presets_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    items = raw.get("presets")
    if not isinstance(items, dict):
        items = raw            # 兼容直接写成 {名字: 参数} 的老格式
    out = {}
    for name, spec in items.items():
        clean = _clean_custom_preset(spec)
        if clean is None:
            continue
        out[str(name)] = clean
    return out


def save_custom_presets(items: dict) -> bool:
    """写自定义预设. 先写临时文件再原子替换, 避免写一半断电留下半截 JSON."""
    p = _custom_presets_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "presets": items}
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception:
        return False


def describe_preset(spec: dict) -> str:
    """给自定义预设生成一句人话描述 (界面/下拉框/日志都用它)."""
    mode = spec.get("mode", "balanced")
    if mode == "target":
        side = spec.get("max_side", 0)
        return (f"目标 ≤{spec.get('target_kb', 0)}KB, "
                f"{('长边 ' + str(side)) if side else '尺寸不变'}, "
                f"{str(spec.get('format', 'keep')).upper()}")
    if mode == "lossless":
        return "无损 (保留 EXIF)" if spec.get("keep_exif") else "无损 (剥 EXIF)"
    label = "均衡" if mode == "balanced" else "激进"
    return f"q={spec.get('quality', 85)} {label}"


def all_presets() -> dict:
    """内置预设 + 用户自定义预设.

    自定义的名字不许跟内置重名 (存的时候就会拦掉), 所以这里不会遮住谁。
    """
    out = dict(PRESETS)
    for name, spec in load_custom_presets().items():
        if name in out:
            continue
        s = dict(spec)
        s["desc"] = describe_preset(s)
        out[name] = s
    return out


def _raw_settings() -> dict:
    """读设置文件里的**原始**内容, 不做任何校验/回落.

    改名/删除自定义预设的时候必须用这个, 不能用 _load_settings():
    _load_settings() 读到"已经不存在的预设名"会判它非法, 然后静默回落成
    默认档 —— 改名落盘之后旧名就已经不存在了, 这时候再读只会读到回落值,
    永远等不到旧名, 于是"设置里指向这个预设"的引用就断了, 右键默认
    悄悄变回「推荐压缩」, 用户完全不知道为什么。
    """
    for name in ("settings.json", "quick.json"):     # quick.json = v9 老文件
        p = _pic_root() / name
        if not p.is_file():
            continue
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except Exception:
            continue
    return {}


def _v9_load_preset() -> str:
    """快捷入口默认预设 = 你在设置里定的那个 (或 GUI 里手动点过的)."""
    return _load_settings()["preset"]


def _v9_save_preset(name: str) -> None:
    """GUI 里手动换预设时记一笔, 右键快捷入口下次就用它."""
    if name not in all_presets():
        return
    s = _load_settings()
    # 存进去的一定要是新名, 否则下一次读配置时又得靠迁移兜一遍
    s["preset"] = PRESET_RENAMES.get(name, name)
    _save_settings(s)


def _backup_manifest(stamp_dir: Path) -> Path:
    return stamp_dir / "_restore.json"


def _backup_record(stamp_dir: Path, backup_file: Path, original: Path) -> None:
    """记下「这个备份是从哪个原文件来的」—— 还原时才知道往哪儿放回去."""
    import json
    mf = _backup_manifest(stamp_dir)
    data = {"items": []}
    if mf.is_file():
        try:
            old = json.loads(mf.read_text(encoding="utf-8"))
            if isinstance(old, dict) and isinstance(old.get("items"), list):
                data = old
        except Exception:
            pass
    try:
        osize = original.stat().st_size
    except OSError:
        osize = 0
    try:
        bsize = backup_file.stat().st_size
    except OSError:
        bsize = 0
    data["items"].append({
        "backup": backup_file.name,
        "original": str(original),
        "original_size": osize,
        "backup_size": bsize,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    try:
        mf.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    except Exception as e:
        _v9_log(f"[backup] 写清单失败: {e}")


def _backup_sessions() -> list[tuple[Path, list[dict]]]:
    """列出所有备份批次, 新的在前. 返回 [(目录, 清单项列表)]."""
    out: list[tuple[Path, list[dict]]] = []
    root = _backup_root()
    if not root.is_dir():
        return out
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        items: list[dict] = []
        mf = _backup_manifest(d)
        if mf.is_file():
            try:
                raw = json.loads(mf.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("items"), list):
                    items = [i for i in raw["items"] if isinstance(i, dict)]
            except Exception:
                items = []
        if not items:      # 清单丢了就退回按文件名认
            items = [{"backup": f.name, "original": "", "legacy": True}
                     for f in sorted(d.iterdir())
                     if f.is_file() and f.name != "_restore.json"]
        out.append((d, items))
    return out


def _restore_backup(stamp_dir: Path, items: list[dict]) -> tuple[int, int]:
    """把一个备份批次还原回原位. 返回 (成功数, 失败数)."""
    ok = bad = 0
    for it in items:
        src = stamp_dir / str(it.get("backup", ""))
        dst = Path(str(it.get("original") or "")).expanduser()
        if not src.is_file() or not it.get("original"):
            bad += 1
            continue
        try:
            if dst.exists() and _same_path(dst, src):
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            # 还原本身也要可逆: 还原前先给「当前版本」留一份
            pre_dir = _backup_root() / (_now_stamp() + "-prerestore")
            pre_dir.mkdir(parents=True, exist_ok=True)
            pre = pre_dir / dst.name
            shutil.copy2(dst if dst.exists() else src, pre)
            _backup_record(pre_dir, pre, dst)
            shutil.copy2(src, dst)
            ok += 1
        except Exception as e:
            _v9_log(f"[restore] 还原 {dst} 失败: {e}")
            bad += 1
    return ok, bad


def _now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _backup_original(src: Path) -> Path | None:
    """覆盖原图前先存一份, 出问题能还原. 返回备份路径."""
    try:
        d = _backup_root() / _now_stamp()
        d.mkdir(parents=True, exist_ok=True)
        dst = d / src.name
        n = 1
        while dst.exists():
            dst = d / f"{src.stem}_{n}{src.suffix}"
            n += 1
        shutil.copy2(src, dst)
        _backup_record(d, dst, src)
        return dst
    except Exception as e:
        _v9_log(f"[backup] 备份 {src} 失败: {e}")
        return None


_V9_VALUE_OPTS = {"--preset": "preset", "--out": "out", "--format": "format",
                  "--output-mode": "output_mode"}

V9_USAGE = f"""图瘦身 (PicShrink) v11.4 — 快捷压缩入口

  图瘦身.exe                            打开图形界面
  图瘦身.exe "D:\\图\\a.jpg"             直接压缩这一张
  图瘦身.exe "D:\\图\\*.jpg"             按通配符批量压
  图瘦身.exe "D:\\图"                    整个文件夹 (自动递归)
  图瘦身.exe --gui "D:\\图"              打开界面并预载这些图
  图瘦身.exe --preset 6 "D:\\图"         用第 6 个预设压
  图瘦身.exe --preset "🛒 亚马逊主图" "D:\\图"
  图瘦身.exe --out "D:\\出图" "D:\\图"   指定输出根目录

选项
  --preset N|全名        1-{len(PRESETS)} 或预设全名
  --out DIR              输出根目录 (默认 %USERPROFILE%\\{V9_DEFAULT_OUT})
  --format keep|jpg|png|webp
                         覆盖预设的输出格式 (默认保持原格式)
  --gui                  打开 GUI 并预载文件, 不直接压
  --install              装上右键菜单 / 发送到 / 桌面快捷方式
  --uninstall            卸掉上面这些 (压缩结果不删)
  --no-notify            不弹窗 (脚本 / 批处理用)
  --quiet                静默模式: 不弹窗, 只写日志
  --list-presets         列出全部预设
  -h, --help             显示本说明

原图永不覆盖: 输出统一写到 <输出根目录>\\<源文件夹名>\\ 下。
"""


def _v9_parse(argv: list[str]):
    """手写参数解析: 右键只传路径, 这里再兼容几个开关.

    返回 (opts, paths)。未知开关一律忽略, 免得 Explorer 传个怪东西就崩。
    """
    opts = {"preset": None, "out": None, "format": None, "output_mode": None,
            "gui": False, "notify": True, "help": False, "list_presets": False,
            "install": False, "uninstall": False, "quiet": False}
    paths: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        low = a.lower()
        if low in ("-h", "--help", "/?"):
            opts["help"] = True
        elif low == "--list-presets":
            opts["list_presets"] = True
        elif low == "--gui":
            opts["gui"] = True
        elif low == "--no-notify":
            opts["notify"] = False
        elif low == "--install":
            opts["install"] = True
        elif low == "--uninstall":
            opts["uninstall"] = True
        elif low == "--quiet":
            opts["quiet"] = True
            opts["notify"] = False
        elif "=" in a and a.split("=", 1)[0].lower() in _V9_VALUE_OPTS:
            opts[_V9_VALUE_OPTS[a.split("=", 1)[0].lower()]] = a.split("=", 1)[1]
        elif low in _V9_VALUE_OPTS:
            if i + 1 < len(argv):
                opts[_V9_VALUE_OPTS[low]] = argv[i + 1]
                i += 1
            else:
                opts["help"] = True
        elif not a.startswith("-"):
            # Explorer 偶尔会塞空串进来(菜单命令里的占位符没展开时就是这种情况,
            # 实测收到过 raw=[''])。留着的话"收到 0 个路径"会变成"收到 1 个空路径",
            # 现象一样但根因完全不同, 事后查日志会被带偏。这里直接丢掉。
            if a.strip():
                paths.append(a)
        i += 1
    return opts, paths


def _v9_expand(paths: list[str]) -> list[Path]:
    """把命令行里的路径展开成一张去重后的图片清单.

    支持: 单个文件 / 文件夹(递归) / 通配符. 非图片一律忽略。
    """
    out: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        s = raw.strip().strip('"')
        if not s:
            continue
        p = Path(s)
        cands: list[Path] = []
        if p.is_dir():
            try:
                cands = [q for q in sorted(p.rglob("*"))
                         if q.is_file() and q.suffix.lower() in SUPPORTED]
            except OSError:
                cands = []
        elif p.is_file():
            if p.suffix.lower() in SUPPORTED:
                cands = [p]
        elif any(ch in s for ch in "*?"):
            base = p.parent if str(p.parent) not in ("", ".") else Path(".")
            try:
                cands = [q for q in sorted(base.glob(p.name))
                         if q.is_file() and q.suffix.lower() in SUPPORTED]
            except (OSError, ValueError):
                cands = []
        for q in cands:
            try:
                key = str(q.resolve()).lower()
            except OSError:
                key = str(q).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(q)
    return out


def _v9_resolve_preset(spec: str | None) -> str:
    """预设可以是全名 / 1-{len(PRESETS)} 序号 / mode 名 (balanced 之类).

    ⚠ 序号只给内置预设用, 自定义预设一律用全名选。
      用户自定义预设的数量是会变的 (今天存 2 个, 明天删 1 个), 用序号指它
      等于埋雷: 用户删掉一个自定义预设, 后面所有序号全部错位, 而老快捷方式
      里存的序号不会跟着变, 结果就是"右键压出来的图跟当初选的根本不是一个档"。
      内置预设永远是 1..10 固定不变, 所以序号这条路对内置永远安全。
    """
    if not spec:
        return _v9_load_preset()
    s = spec.strip()
    if s in PRESETS:
        return s
    # 用户自定义预设: 只认全名
    if s in load_custom_presets():
        return s
    # 预设改过名: 老快捷方式里可能还写着旧的全名, 照样认, 别让人直接报错
    if s in PRESET_RENAMES:
        return PRESET_RENAMES[s]
    if s.isdigit():
        idx = int(s)
        keys = list(PRESETS.keys())
        if 1 <= idx <= len(keys):
            return keys[idx - 1]
    for k, v in PRESETS.items():
        if v.get("mode") == s:
            return k
    raise ValueError(f"未知预设: {spec} (可用 1-{len(PRESETS)} 或预设全名)")


def _v9_icon(root) -> None:
    """窗口图标. 兼容 PyInstaller 单文件 (资源在 sys._MEIPASS 里)."""
    try:
        base = getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent))
        ico = Path(base) / "app.ico"
        if ico.is_file():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass


def _v9_style(root) -> None:
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass


def _v9_geometry(root, w: int, h: int) -> str:
    """尽量把窗口摆到屏幕中间偏上, 抢眼但不离谱."""
    try:
        x = max(0, (root.winfo_screenwidth() - w) // 2)
        y = max(0, (root.winfo_screenheight() - h) // 3)
        return f"{w}x{h}+{x}+{y}"
    except Exception:
        return f"{w}x{h}"


def _v9_compress_all(files: list[Path], out_root: Path, mode: str, quality: int,
                     fmt_arg: str, max_side: int, keep_exif: bool, target_kb: int,
                     on_done=None, out_mode: str = "suffix") -> list[dict]:
    """逐张压, 返回结果字典列表. 完全复用 GUI 的 compress_one."""
    results: list[dict] = []
    for i, src in enumerate(files):
        try:
            save_fmt, ext = pick_output_format(src, fmt_arg)
        except Exception:
            save_fmt, ext = "JPEG", "jpg"
        rec = {"src": src, "out": None, "src_bytes": 0, "out_bytes": 0,
               "msg": "", "ok": False}
        try:
            rec["src_bytes"] = src.stat().st_size
        except OSError:
            pass
        try:
            out_path, sb, ob, msg = compress_one(
                src, out_root, mode, quality, save_fmt, ext,
                max_side, keep_exif, True, target_kb, out_mode)
            rec.update(out=out_path, src_bytes=sb, out_bytes=ob, msg=msg)
        except Exception as e:
            rec["msg"] = f"失败: {e}"
        rec["ok"] = str(rec["msg"]).startswith("ok")
        results.append(rec)
        _v9_log(f"  {src.name} -> {rec['msg']}")
        if on_done:
            try:
                on_done(i + 1)
            except Exception:
                pass
    return results


def _v9_rc(results: list[dict]) -> int:
    """0 = 全好 / 有跳过; 1 = 有失败; 2 = 压根没东西可压."""
    if not results:
        return 2
    fail = sum(1 for r in results if not r["ok"] and "跳过" not in r["msg"])
    return 1 if fail else 0


def _v9_report_text(results: list[dict], out_root: Path, preset_name: str) -> str:
    ok = sum(1 for r in results if r["ok"])
    skip = sum(1 for r in results if not r["ok"] and "跳过" in r["msg"])
    fail = len(results) - ok - skip
    saved = sum(r["src_bytes"] - r["out_bytes"]
                for r in results if r["ok"] and r["out_bytes"] > 0)
    lines = [
        "图瘦身 v11.4 — 完成",
        f"预设: {preset_name}",
        f"成功 {ok} · 跳过 {skip} · 失败 {fail}",
        f"省下: {human_size(max(0, saved))}" if saved > 0 else "没省下体积",
        f"输出: {out_root}",
        "",
    ]
    for r in results:
        lines.append(f"{r['src'].name}: {r['msg']}")
    return "\n".join(lines)


def _v9_fatal(msg: str, notify: bool = True) -> None:
    """无法继续时的提示. notify=False (脚本模式) 只落日志."""
    _v9_log("[FATAL] " + msg)
    _v9_print(msg)
    if not notify:
        return
    try:
        root = tk.Tk()
        root.withdraw()
        _v9_icon(root)
        messagebox.showerror("图瘦身 v11.4", msg, parent=root)
        root.destroy()
    except Exception:
        pass


def _v9_result_ui(root, results: list[dict], out_root: Path,
                  preset_name: str, auto_close_ms: int = 8000) -> None:
    """结果窗: 三个数 + 明细列表 + 打开输出目录, 8 秒后自动关."""
    ok = sum(1 for r in results if r["ok"])
    skip = sum(1 for r in results if not r["ok"] and "跳过" in r["msg"])
    fail = len(results) - ok - skip
    saved = sum(r["src_bytes"] - r["out_bytes"]
                for r in results if r["ok"] and r["out_bytes"] > 0)

    for w in root.winfo_children():
        w.destroy()
    root.title("图瘦身 v11.4 — 完成")
    root.geometry(_v9_geometry(root, 620, 460))
    root.minsize(620, 460)

    head = ttk.Frame(root, padding=(16, 14, 16, 6))
    head.pack(fill="x")
    if fail:
        title_text, color = f"完成, 但有 {fail} 张失败", "#c0392b"
    elif skip:
        title_text, color = "搞定 (有图压不动, 已保留原样)", "#b7791f"
    else:
        title_text, color = "全部搞定!", "#1e8449"
    ttk.Label(head, text=title_text, font=("Microsoft YaHei UI", 13, "bold"),
              foreground=color).pack(anchor="w")
    ttk.Label(head, text=f"预设: {preset_name}",
              font=("Microsoft YaHei UI", 9)).pack(anchor="w")
    detail = f"成功 {ok}   跳过 {skip}   失败 {fail}"
    if saved > 0:
        detail += f"   ·   共省下 {human_size(saved)}"
    ttk.Label(head, text=detail, font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(4, 0))

    body = ttk.Frame(root, padding=(12, 0, 12, 0))
    body.pack(fill="both", expand=True)
    txt = tk.Text(body, font=("Consolas", 9), wrap="word", height=12, relief="solid", bd=1)
    sb = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    txt.pack(side="left", fill="both", expand=True)
    for r in results:
        if r["ok"]:
            line = f"✅ {r['src'].name}  {human_size(r['src_bytes'])} → {human_size(r['out_bytes'])}"
        elif "跳过" in r["msg"]:
            line = f"⏭️  {r['src'].name}  {r['msg']}"
        else:
            line = f"❌ {r['src'].name}  {r['msg']}"
        txt.insert("end", line + "\n")
    txt.configure(state="disabled")

    foot = ttk.Frame(root, padding=(12, 8, 12, 12))
    foot.pack(fill="x")
    ttk.Label(foot, text=f"输出目录: {out_root}",
              font=("Microsoft YaHei UI", 8), foreground="#666").pack(anchor="w")

    btns = ttk.Frame(foot)
    btns.pack(fill="x", pady=(6, 0))

    def open_out():
        try:
            os.startfile(str(out_root))
        except Exception:
            pass

    ttk.Button(btns, text="📂 打开输出目录", command=open_out).pack(side="left")
    ttk.Button(btns, text="全部重压一遍", command=root.destroy).pack(side="left", padx=8)
    ttk.Button(btns, text="完成", command=root.destroy).pack(side="right")

    if auto_close_ms > 0:
        left = {"n": auto_close_ms // 1000}

        def countdown():
            left["n"] -= 1
            if left["n"] <= 0:
                root.destroy()
            else:
                lbl.config(text=f"{left['n']} 秒后自动关闭")
                root.after(1000, countdown)

        lbl = ttk.Label(foot, text=f"{auto_close_ms // 1000} 秒后自动关闭",
                        font=("Microsoft YaHei UI", 8), foreground="#999")
        lbl.pack(side="right")
        root.after(1000, countdown)


def _v9_overwrite_allowed(out_mode: str, cfg: dict, notify: bool,
                          n_files: int) -> bool:
    """覆盖原图前的一道闸. False = 不许跑, 一个字节都不能动.

    覆盖是唯一不可逆的输出模式, 所以:
      - 界面里: 每次都弹确认, 就算之前勾过"我知道有风险"
      - 脚本里: 没勾过确认就直接拒绝, 不猜你的意图
    """
    if out_mode != "overwrite" or cfg.get("overwrite_ack"):
        return True
    if notify:
        if _v9_box(
                "图瘦身 — 确认覆盖原图",
                "你把默认输出位置设成了「覆盖原图」。\n\n"
                f"这会把压好的图直接写回 {n_files} 个原文件, 原图路径不变。\n"
                "放心: 覆盖前会自动复制一份到备份文件夹, 出问题能还原。\n\n"
                "确定要继续吗?", ask=True):
            return True
        _v9_fatal("已取消, 没有任何文件被改动。", notify=False)
        return False
    _v9_fatal(
        "当前设置为「覆盖原图」, 但你还没确认过风险。\n\n"
        "  · 图形界面: 打开图瘦身 → 设置 → 勾一次「我知道覆盖原图有风险」\n"
        "  · 只想导出副本: 加 --output-mode suffix",
        notify=False)
    return False


def _v9_quick(paths: list[str], opts: dict) -> int:
    """V9 快捷压缩主流程: 进度窗 → 后台压缩 → 结果窗."""
    files = _v9_expand(paths)
    if not files:
        # v11: 把"到底收到了什么"直接摆给用户看。
        # 原来只说"没找到可处理的图片", 用户根本不知道是自己没选中图,
        # 还是 Explorer 传参出了问题, 只能反复点然后截图来问。
        got = [p for p in paths if str(p).strip()]
        if got:
            why = ("程序收到了这些参数, 但它们都不是能读到的图片路径:\n"
                   + "\n".join("  " + repr(p) for p in got[:6])
                   + (f"\n  …共 {len(got)} 个" if len(got) > 6 else "")
                   + "\n\n这通常说明右键菜单传参有问题, 请把这份内容发给作者。")
        else:
            why = ("程序一个路径都没收到。\n"
                   "如果你是在右键菜单里点的, 多半是菜单项注册坏了。\n"
                   "重装一次安装包即可修复。")
        _v9_fatal(
            "没找到可处理的图片。\n\n"
            + why + "\n\n"
            "可以这样用:\n"
            "  · 选中图片右键 → 立即压缩 (压完就走) / 加入压缩队列 (进主窗口)\n"
            "  · 选中文件夹 (自动递归所有图片)\n"
            "  · 命令行传通配符, 例如 图瘦身.exe \"D:\\图\\*.jpg\"\n\n"
            "支持的格式: " + ", ".join(sorted(SUPPORTED)),
            notify=opts["notify"])
        return 2

    try:
        preset_name = _v9_resolve_preset(opts["preset"])
    except ValueError as e:
        _v9_fatal(str(e), notify=opts["notify"])
        return 2

    pr = all_presets().get(preset_name)
    if not pr:
        _v9_fatal(f"预设不存在: {preset_name}", notify=opts["notify"])
        return 2
    mode = pr["mode"]
    quality = int(pr.get("quality", 85))
    max_side = int(pr.get("max_side", 0))
    keep_exif = bool(pr.get("keep_exif", False))
    target_kb = int(pr.get("target_kb", 0))

    # v11: 右键快捷入口读用户在设置里定的默认值.
    # 优先级: 命令行显式参数 > 用户设置 > 预设自带默认值.
    cfg = _load_settings()
    fmt_arg = opts["format"] or cfg["format"] or pr.get("format", "keep")
    out_mode = opts["output_mode"] or cfg["output_mode"]
    if out_mode not in OUTPUT_MODES:
        out_mode = "suffix"
    fixed_dir = str(cfg.get("output_dir") or "").strip()

    if out_mode == "fixed" and fixed_dir:
        # 固定目录模式: 用户指定了位置就用它
        try:
            out_root = Path(fixed_dir).expanduser().resolve()
        except Exception:
            out_root = (Path.home() / V9_DEFAULT_OUT).resolve()
    else:
        try:
            out_root = (Path(opts["out"]).expanduser() if opts["out"]
                        else (Path.home() / V9_DEFAULT_OUT)).resolve()
        except Exception:
            out_root = (Path.home() / V9_DEFAULT_OUT).resolve()

    try:
        out_root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _v9_fatal(f"输出目录建不了: {e}", notify=opts["notify"])
        return 2

    # overwrite 模式不往独立目录写, 但 out_root 仍要给报告用
    where = {"suffix": "原文件夹 (加 _compressed 后缀)",
             "fixed": "固定目录",
             "overwrite": "覆盖原图 (已自动备份)"}[out_mode]
    # 只有"从设置里读到的 fixed 但没配目录"才退回加后缀.
    # 命令行显式 --output-mode fixed --out X 必须照办.
    if out_mode == "fixed" and not fixed_dir and not opts["out"]:
        out_mode, where = "suffix", "原文件夹 (未设固定目录, 退回加后缀)"
    if out_mode == "suffix" and not opts["out"] and not fixed_dir:
        where = f"{where} · 备用副本在 {out_root}"

    # 覆盖原图 = 不可逆操作, 没确认过就不敢自动跑.
    if not _v9_overwrite_allowed(out_mode, cfg, opts["notify"], len(files)):
        return 2

    total_bytes = 0
    for f in files:
        try:
            total_bytes += f.stat().st_size
        except OSError:
            pass

    try:
        import time as _time
        _v9_log(f"[{_time.strftime('%Y-%m-%d %H:%M:%S')}] preset={preset_name} "
                f"mode={mode} fmt={fmt_arg} out_mode={out_mode} "
                f"n={len(files)} -> {out_root}")
    except Exception:
        _v9_log(f"preset={preset_name} mode={mode} fmt={fmt_arg} "
                f"out_mode={out_mode} n={len(files)} -> {out_root}")

    # 脚本 / 测试模式: 不开窗, 直接跑完并把结果打到控制台
    if not opts["notify"]:
        results = _v9_compress_all(files, out_root, mode, quality, fmt_arg,
                                   max_side, keep_exif, target_kb,
                                   out_mode=out_mode)
        _v9_print(_v9_report_text(results, out_root, preset_name))
        return _v9_rc(results)

    holder: dict = {}
    try:
        root = tk.Tk()
    except Exception as e:
        _v9_fatal(f"起不了窗口: {e}", notify=False)
        return 2
    _v9_style(root)
    _v9_icon(root)
    root.title("图瘦身 — 正在压缩")

    outer = ttk.Frame(root, padding=18)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text=f"预设: {preset_name}",
              font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
    ttk.Label(outer, text=pr["desc"],
              font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(2, 8))
    ttk.Label(outer, text=f"{len(files)} 张图 · 共 {human_size(total_bytes)}",
              font=("Microsoft YaHei UI", 9)).pack(anchor="w")

    bar = ttk.Progressbar(outer, mode="indeterminate")
    bar.pack(fill="x", pady=10)
    bar.start(12)
    cnt = ttk.Label(outer, text=f"0 / {len(files)}", font=("Microsoft YaHei UI", 9))
    cnt.pack(anchor="w")
    ttk.Label(outer, text=f"输出: {where}",
              font=("Microsoft YaHei UI", 8), foreground="#666",
              wraplength=480).pack(anchor="w", pady=(10, 0))
    root.geometry(_v9_geometry(root, 520, 260))
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    def on_tick(n):
        cnt.config(text=f"{n} / {len(files)}")

    def worker():
        res = _v9_compress_all(
            files, out_root, mode, quality, fmt_arg, max_side, keep_exif, target_kb,
            on_done=lambda n: root.after(0, lambda n=n: on_tick(n)),
            out_mode=out_mode)
        holder["results"] = res

        def show():
            try:
                bar.stop()
            except Exception:
                pass
            _v9_result_ui(root, res, out_root, preset_name)

        root.after(0, show)

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()
    return _v9_rc(holder.get("results", []))


def _v9_show_help(notify: bool) -> None:
    if not notify:
        _v9_print(V9_USAGE)
        return
    try:
        root = tk.Tk()
        _v9_icon(root)
        _v9_style(root)
        root.title("图瘦身 v11.4 — 用法")
        outer = ttk.Frame(root, padding=14)
        outer.pack(fill="both", expand=True)
        txt = tk.Text(outer, font=("Consolas", 9), wrap="none", width=76)
        txt.insert("1.0", V9_USAGE)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        root.geometry("760x520")
        ttk.Button(root, text="关闭", command=root.destroy).pack(pady=(0, 10))
        root.mainloop()
    except Exception:
        _v9_print(V9_USAGE)


def _v9_show_presets(notify: bool) -> None:
    lines = [f"共 {len(PRESETS)} 个内置预设 (快捷入口默认沿用 GUI 里你最后手动选的那个):", ""]
    for i, (name, p) in enumerate(PRESETS.items(), 1):
        lines.append(f"{i}. {name}")
        lines.append(f"   {p['desc']}")
    custom = load_custom_presets()
    if custom:
        lines.append("")
        lines.append(f"另有 {len(custom)} 个自定义预设 (只能用全名选, 不占序号):")
        for name, spec in custom.items():
            lines.append(f"· {name}")
            lines.append(f"   {describe_preset(spec)}")
    text = "\n".join(lines)
    if not notify:
        _v9_print(text)
        return
    try:
        root = tk.Tk()
        _v9_icon(root)
        _v9_style(root)
        root.title("图瘦身 v11.4 — 预设清单")
        outer = ttk.Frame(root, padding=14)
        outer.pack(fill="both", expand=True)
        txt = tk.Text(outer, font=("Consolas", 10), wrap="word", width=66)
        txt.insert("1.0", text)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        root.geometry("700x480")
        ttk.Button(root, text="关闭", command=root.destroy).pack(pady=(0, 10))
        root.mainloop()
    except Exception:
        _v9_print(text)


# ============================================================
#  V9 安装 / 卸载
#  (install.bat / uninstall.bat 只是两个 ASCII 空壳, 真正的活儿在这儿)
# ============================================================
#  为什么不让批处理直接干这些活:
#    中文 .bat 文件在非 936 控制台码页下会被 cmd 按错码页解读, 多字节字符
#    被当成特殊字符, 轻则乱码重则整行报错。chcp 也救不了 —— 码页切换发生在
#    文件被读取之后。而注册表键名 / 快捷方式名 / 真实桌面路径都带中文。
#    把它们交给 Python 就完全没有编码歧义: Unicode 走 Win32 API, 不经过码页。
#
#  顺带把 exe 文件名改成 ASCII 的 PicShrink.exe, 这样批处理引用它也不会出事。

V9_APP_TITLE = "图瘦身 (PicShrink) v11.4"
V9_FOLDER_NAME = "图瘦身"

# 右键现在是两条并排的路, 名字必须一眼能分开, 否则用户只能挨个试:
#   立即压缩      → 点完直接开压, 用设置里存的默认预设
#   加入压缩队列  → 装进主窗口, 能看清单、能改预设、再点"开始压缩"
#
# 注册表键名一律用 ASCII (PicShrinkQuick / PicShrinkQueue), 跟菜单显示名解耦。
# v9~v11.2 那次改名就是因为键名跟着显示名一起改, 老用户升级后新旧两项会同时
# 出现在菜单里 —— 显示名以后可以随便改, 键名不动就永远不会再有孤儿项。
V9_MENU_KEY_QUICK = "PicShrinkQuick"
V9_MENU_KEY_QUEUE = "PicShrinkQueue"
# v9~v11.2 用过的中文键名。安装/卸载时都要主动删, 不能指望覆盖。
#
# ⚠ 这个名单是**攒出来的**, 不是想出来的 —— 每一个都是真机上有孤儿键才补进去的:
#   "用图瘦身处理"      v9~v11.2 正式版的键名
#   "用图瘦身压缩这个文件夹"  同上, 文件夹那一版(早先漏了, 于是文件夹右键
#                        会多出一个点不掉的条目)
#   "立即压缩" / "立即压缩这个文件夹"  v11.3 开发期的中间构建用显示名当过键名,
#                        装过那一版的用户机器上会留下 command 为空的死键 ——
#                        右键里看得见, 点下去什么都不发生
# 补一条的代价是几行代码; 不补的代价是用户右键里永远多一个删不掉的条目。
V9_MENU_LEGACY_KEYS = ("用图瘦身处理", "用图瘦身压缩这个文件夹",
                       "立即压缩", "立即压缩这个文件夹")

V9_MENU_NAME = "立即压缩"
V9_MENU_NAME_DIR = "立即压缩这个文件夹"
V9_QUEUE_MENU_NAME = "加入压缩队列"
V9_QUEUE_MENU_NAME_DIR = "加入压缩队列这个文件夹"
V9_SHORTCUT_NAME = "图瘦身.lnk"

# FOLDERID_Desktop —— 问 Windows 要真实桌面路径。
# 不能用 %USERPROFILE%\Desktop: 桌面可以被重定向到别的盘(本机就是 D:\Desktop),
# 写死会在很多电脑上把图标丢到一个没人看的目录里。
_FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"


def _v9_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or ""
    root = Path(base) if base else Path.home()
    return root / V9_FOLDER_NAME


def _v9_self_exe() -> Path:
    """当前这个 exe 的真实路径 (打包后就是它自己)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(sys.argv[0]).resolve()


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def _v9_parse_guid(s: str):
    """把 "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}" 这种字符串变成 GUID 结构体.

    ctypes.c_void_p("...") 会直接抛 TypeError —— 它只吃整数/地址。
    所以必须自己按 GUID 的二进制布局拆, 再把地址交给 Win32。
    """
    s = s.strip().strip("{}")
    # GUID 是 8-4-4-4-12 五段: 前三段进 Data1/2/3,
    # 后两段拼起来才是完整的 16 个十六进制字符 (Data4)
    p = s.split("-")
    if len(p) < 5:
        raise ValueError("GUID 格式不对: " + s)
    tail = p[3] + p[4]
    d1 = int(p[0], 16)
    d2 = int(p[1], 16)
    d3 = int(p[2], 16)
    d4 = [int(tail[i:i + 2], 16) for i in range(0, 16, 2)]
    return _GUID(d1, d2, d3, (ctypes.c_ubyte * 8)(*d4))


def _known_desktop() -> Path:
    """真实桌面目录 (尊重用户重定向). 拿不到就退回 %USERPROFILE%\\Desktop."""
    try:
        guid = _v9_parse_guid(_FOLDERID_DESKTOP)
        buf = ctypes.c_void_p()
        fn = ctypes.windll.shell32.SHGetKnownFolderPath
        fn.argtypes = [ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
                       ctypes.POINTER(ctypes.c_void_p)]
        fn.restype = ctypes.c_long
        hr = fn(ctypes.byref(guid), 0, None, ctypes.byref(buf))
        if hr == 0 and buf:
            try:
                return Path(ctypes.wstring_at(buf))
            finally:
                ctypes.windll.ole32.CoTaskMemFree(buf)
    except Exception:
        pass
    # API 拿不到就读注册表 —— Explorer 自己就是从这儿读的
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        try:
            val = winreg.QueryValueEx(k, "Desktop")[0]
        finally:
            winreg.CloseKey(k)
        expanded = Path(os.path.expandvars(val))
        if expanded.is_dir():
            return expanded
    except Exception:
        pass
    return Path.home() / "Desktop"


def _refresh_shell() -> None:
    """通知资源管理器"关联项变了", 让右键菜单立刻出现, 不用重启 explorer."""
    try:
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass


def _make_lnk(target: Path, lnk_path: Path, icon: str, desc: str) -> bool:
    """建 .lnk 快捷方式.

    用 PowerShell 的 WScript.Shell。参数不走命令行 —— 路径里可能有空格,
    而且中文路径经 argv 传递后再拼进脚本很容易被二次解释, 所以改用环境变量,
    PowerShell 那边只读 $env:, 彻底绕开转义问题。
    """
    try:
        lnk_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    env = dict(os.environ)
    env.update({
        "PS_LNK_PATH": str(lnk_path),
        "PS_LNK_TARGET": str(target),
        "PS_LNK_WORKDIR": str(target.parent),
        "PS_LNK_ICON": icon,
        "PS_LNK_DESC": desc,
    })
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:PS_LNK_PATH);"
        "$s.TargetPath=$env:PS_LNK_TARGET;"
        "$s.WorkingDirectory=$env:PS_LNK_WORKDIR;"
        "$s.IconLocation=$env:PS_LNK_ICON;"
        "$s.Description=$env:PS_LNK_DESC;"
        "$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps],
            env=env, capture_output=True, timeout=90)
        return lnk_path.is_file()
    except Exception:
        return False


def _v9_box(title: str, msg: str, error: bool = False, ask: bool = False) -> bool:
    """弹结果窗. ask=True 时返回用户点的是"是"."""
    try:
        root = tk.Tk()
        root.withdraw()
        _v9_icon(root)
        if ask:
            return bool(messagebox.askyesno(title, msg, parent=root))
        messagebox.showerror(title, msg, parent=root) if error else \
            messagebox.showinfo(title, msg, parent=root)
        return True
    except Exception:
        return False


def _v9_install_step(n: int, total: int, text: str, lines: list[str]) -> None:
    lines.append(f"[{n}/{total}] {text}")


def _v9_find_stale_installs(dest: Path) -> list[tuple[str, str]]:
    """找出这台电脑上其它位置的图瘦身安装.

    为什么需要这个:
      Inno 记的是自己的 AppId, 装到哪儿就往"程序和功能"里写哪儿。
      但历史上如果换过安装目录(比如 v8/v10 装在 D 盘, v11 改到 %LOCALAPPDATA%),
      老的卸载登记项不会被自动清掉, 于是同一个程序在磁盘上留下两份 exe。
      后果是: 右键菜单只指向其中一份, 另一份成了僵尸;
              "程序和功能"里只能卸载一份, 另一份删不掉;
              用户还以为是版本冲突, 其实是路径重影。
    返回 [(路径, 说明), ...], 没有就返回空表。
    """
    import winreg
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(p: Path, why: str) -> None:
        try:
            key = str(p.resolve()).lower()
        except OSError:
            key = str(p).lower()
        if key == str(dest.resolve()).lower() or key in seen:
            return
        seen.add(key)
        found.append((str(p), why))

    # 1) 扫卸载登记项(三个 hive 都要, 32/64 位各一份)
    roots = [
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM(32位)"),
    ]
    for hive, sub, tag in roots:
        try:
            base = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ)
        except OSError:
            continue
        i = 0
        while True:
            try:
                name = winreg.EnumKey(base, i)
            except OSError:
                break
            i += 1
            try:
                k = winreg.OpenKey(base, name, 0, winreg.KEY_READ)
            except OSError:
                continue
            try:
                # 卸载表里混着大量没有 DisplayName 的杂项键(补丁残留等),
                # 直接 QueryValueEx 会 FileNotFoundError 把整个体检打断。
                try:
                    disp = str(winreg.QueryValueEx(k, "DisplayName")[0])
                except OSError:
                    continue
                try:
                    loc = str(winreg.QueryValueEx(k, "InstallLocation")[0])
                except OSError:
                    loc = ""
            finally:
                winreg.CloseKey(k)
            if "picshrink" not in disp.lower() and V9_FOLDER_NAME not in disp:
                continue
            if loc:
                p = Path(loc.strip().strip('"'))
                if (p / "PicShrink.exe").is_file():
                    _add(p, f"{tag} 卸载登记项还指向这里")
            else:
                _add(Path(name), f"{tag} 卸载登记项({disp})")

    # 2) 扫几个历史上用过的目录 —— 没有卸载登记项的野安装
    try:
        drives = [Path(d + "\\") for d in ("C:", "D:", "E:", "F:")
                  if Path(d + "\\").exists()]
    except OSError:
        drives = []
    for d in drives:
        p = d / V9_FOLDER_NAME
        try:
            if (p / "PicShrink.exe").is_file():
                _add(p, "磁盘上还残留一份, 但卸载列表里没有它")
        except OSError:
            pass

    return found


def _v9_write_verb(shell_path: str, key: str, display: str,
                   icon: str, cmd: str) -> None:
    """写一个右键菜单项。shell_path 形如 Software\\Classes\\*\\shell。"""
    import winreg
    k = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                           shell_path + "\\" + key, 0, winreg.KEY_ALL_ACCESS)
    try:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, display)
        winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon)
        # 升级必须主动删掉旧的 MultiSelectModel。SetValueEx 只写不删,
        # 老值留在那儿等于这次修复根本没生效 —— 这是最容易漏的一步。
        try:
            winreg.DeleteValue(k, "MultiSelectModel")
        except FileNotFoundError:
            pass
        c = winreg.CreateKeyEx(k, "command", 0, winreg.KEY_ALL_ACCESS)
        try:
            winreg.SetValueEx(c, "", 0, winreg.REG_SZ, cmd)
        finally:
            winreg.CloseKey(c)
    finally:
        winreg.CloseKey(k)


def _v9_drop_legacy_menu_keys() -> list[str]:
    """删掉历史版本用过的中文键名。

    不删的话, 从 v11.2 升上来的用户右键会同时看到「用图瘦身处理」和新的
    「立即压缩」/「加入压缩队列」三个图瘦身项 —— 看着像装重了。
    这正是当年 MultiSelectModel 残留的同一类坑, 别再踩第二次。
    """
    import winreg
    gone = []
    for shell_path in ("Software\\Classes\\*\\shell",
                       "Software\\Classes\\Directory\\shell"):
        for old in V9_MENU_LEGACY_KEYS:
            if _v9_del_key(winreg.HKEY_CURRENT_USER, shell_path + "\\" + old):
                _v9_log(f"[install] 已删除旧菜单项: {shell_path}\\{old}")
                gone.append(shell_path + "\\" + old)
    return gone


def v9_install(quiet: bool = False) -> int:
    """装上右键菜单 / 发送到 / 桌面快捷方式. 返回退出码."""
    import shutil
    import winreg

    exe = _v9_self_exe()
    dest = _v9_install_dir()
    lines: list[str] = []

    if not exe.is_file():
        _v9_log("[install] 找不到主程序: " + str(exe))
        if not quiet:
            _v9_box(V9_APP_TITLE, f"安装失败: 找不到主程序\n{exe}")
        return 1

    # 1) 复制主程序 (原 exe 作为安装源)
    try:
        dest.mkdir(parents=True, exist_ok=True)
        dst_exe = dest / exe.name
        if not dst_exe.is_file() or exe.resolve() != dst_exe.resolve():
            shutil.copy2(exe, dst_exe)
        # 图标: 打包的单文件 exe 内部自带一份, 另存一份出来给右键菜单/快捷方式用
        ico_src = Path(getattr(sys, "_MEIPASS", "")) / "app.ico" \
            if getattr(sys, "_MEIPASS", "") else Path(__file__).resolve().parent / "app.ico"
        if ico_src.is_file():
            shutil.copy2(ico_src, dest / "app.ico")
    except Exception as e:
        _v9_log(f"[install] 复制失败: {e}")
        if not quiet:
            _v9_box(V9_APP_TITLE,
                    f"安装失败: 复制主程序出错\n{e}\n\n"
                    f"如果图瘦身正在运行, 请先关掉再装。")
        return 1
    _v9_install_step(1, 5, f"主程序: {dst_exe}", lines)

    icon = f"{dest / 'app.ico'},0" if (dest / "app.ico").is_file() else str(dst_exe)
    # 文件菜单: 不写 MultiSelectModel, 命令用 "%1"。
    #
    # 这块注释是被真机 Explorer 打脸两次之后重写的:
    #   v9  MultiSelectModel=Single  → 多选时菜单根本不显示。
    #   v11 MultiSelectModel=Player + "%*" → 菜单显示, 点下去收到 raw=[''],
    #       一个空字符串参数, 零个路径, 比 v11 还让人一头雾水。
    #
    # 根因: MultiSelectModel 的 Player/Document 会把交给程序的命令行
    # 限制得极短, 而我们的 exe 路径本来就 50+ 字符, "%*" 直接被展开成空串。
    # 本机注册表取证也印证了 —— 9 个文件右键动词里 8 个是"不写 MultiSelectModel
    # + \"%1\""(美图秀修 / ToDesk / Tailscale / 夸克), 唯一写 Player+%* 的就是
    # 图瘦身, 也是唯一坏掉的。
    #
    # 正确写法: 不写 MultiSelectModel。默认模型下 "%1" 会展开成全部选中项
    # (每个各自带引号), 路径长短不影响, 多选一直是好的。别再加回去。
    cmd = f'"{dst_exe}" "%1"'
    # 文件夹菜单必须用 %V, 不能用 %*: Directory\ 这个位置右键点的是文件夹本身,
    # 没有"一批文件"可言, %* 会展开成空字符串 (v11 的实测教训)。
    # %V 才是当前文件夹的完整路径。
    cmd_dir = f'"{dst_exe}" "%V"'
    # 加入队列那条只是多带一个 --gui, 路径占位符的规矩完全一样:
    # 文件 %1 / 文件夹 %V, 同样不写 MultiSelectModel。
    cmd_q = f'"{dst_exe}" --gui "%1"'
    cmd_dir_q = f'"{dst_exe}" --gui "%V"'
    try:
        # 2) 图片右键菜单: 立即压缩 + 加入压缩队列
        _v9_write_verb("Software\\Classes\\*\\shell", V9_MENU_KEY_QUICK,
                       V9_MENU_NAME, icon, cmd)
        _v9_write_verb("Software\\Classes\\*\\shell", V9_MENU_KEY_QUEUE,
                       V9_QUEUE_MENU_NAME, icon, cmd_q)
        _v9_install_step(2, 5,
                         f"图片右键菜单: 「{V9_MENU_NAME}」「{V9_QUEUE_MENU_NAME}」(均支持多选)",
                         lines)

        # 3) 文件夹右键菜单: 同上两条, 自动递归
        _v9_write_verb("Software\\Classes\\Directory\\shell", V9_MENU_KEY_QUICK,
                       V9_MENU_NAME_DIR, icon, cmd_dir)
        _v9_write_verb("Software\\Classes\\Directory\\shell", V9_MENU_KEY_QUEUE,
                       V9_QUEUE_MENU_NAME_DIR, icon, cmd_dir_q)
        _v9_install_step(3, 5,
                         f"文件夹右键菜单: 「{V9_MENU_NAME_DIR}」「{V9_QUEUE_MENU_NAME_DIR}」",
                         lines)

        # 历史中文键名必须清掉, 否则菜单里会新旧并存
        gone = _v9_drop_legacy_menu_keys()
        if gone:
            _v9_install_step(3, 5, f"已清理旧菜单项 {len(gone)} 处", lines)
    except Exception as e:
        _v9_log(f"[install] 注册表失败: {e}")
        if not quiet:
            _v9_box(V9_APP_TITLE, f"安装失败: 写注册表出错\n{e}")
        return 1

    # 4) 发送到
    sendto = Path(os.environ.get("APPDATA", str(Path.home()))) / \
        "Microsoft/Windows/SendTo"
    ok_send = _make_lnk(dst_exe, sendto / V9_SHORTCUT_NAME, icon, "用图瘦身压缩图片")
    _v9_install_step(4, 5, "发送到 -> 图瘦身" if ok_send else "发送到 -> 图瘦身 (失败)", lines)

    # 5) 桌面快捷方式
    desk = _known_desktop()
    ok_desk = _make_lnk(dst_exe, desk / V9_SHORTCUT_NAME, icon, "打开图瘦身图形界面")
    _v9_install_step(5, 5,
                     f"桌面快捷方式: {desk}" if ok_desk else "桌面快捷方式: 失败", lines)

    # 6) 体检: 有没有别的位置还躺着一份老安装
    stale = _v9_find_stale_installs(dest)
    if stale:
        lines.append("")
        lines.append(f"⚠ 这台电脑上还发现 {len(stale)} 处旧安装:")
        for sp, why in stale:
            lines.append(f"   · {sp}")
            lines.append(f"     ({why})")
        lines.append("")
        lines.append("不影响本次使用 —— 右键菜单只认上面刚装好的这一份。")
        lines.append("但旧的那份会: ①在「程序和功能」里删不掉 ②让人怀疑是不是装重了")
        lines.append("清掉方法: 确认新版本好用后, 直接删掉上面列出的文件夹即可。")
        for sp, _ in stale:
            _v9_log(f"[install] 发现旧安装残留: {sp}")

    _refresh_shell()
    out_dir = Path.home() / V9_DEFAULT_OUT
    summary = "\n".join(lines) + f"\n\n输出目录: {out_dir}\n原图永不覆盖。"
    _v9_log("[install] 完成\n" + summary)

    if stale:
        # 旧安装残留一定要让人看见, 但 quiet 下绝不能弹模态框。
        # 安装器就是用 --install --quiet 调本函数的, 弹框 = 无人值守安装被卡死,
        # Inno 会一直等这个窗口, 用户看到的是"安装卡住了"。
        # 静默安装的正规做法: 写日志 + 写结果文件, 让上层/用户事后能查到。
        body = "\n".join(lines[-len(stale) * 2 - 4:])
        warn = ("安装完成, 但发现这台电脑上还有旧版本残留:\n\n"
                + body + "\n\n"
                "这些是历史安装留下的副本, 不影响现在使用 ——\n"
                "右键菜单只认刚装好的这一份。\n\n"
                "但留着会有两个后果:\n"
                "  · 「程序和功能」里只能卸载其中一份, 另一份删不掉\n"
                "  · 以后右键菜单出怪问题, 会分不清是哪一份在作怪\n\n"
                "建议: 确认新版本好用后, 直接把上面列出的文件夹删掉。")
        _v9_log("[install][残留告警] " + warn)
        try:
            # 结果文件: 让"静默装完但有残留"这件事在磁盘上留痕, 不是无声无息
            rf = dest / "install-warnings.txt"
            rf.write_text(warn, encoding="utf-8")
        except OSError:
            pass
        if not quiet:
            _v9_box(V9_APP_TITLE, warn, error=True)
    elif not quiet:
        _v9_box(V9_APP_TITLE,
                f"安装完成!\n\n{summary}\n\n"
                "用法:\n"
                f"  1. 选中图片右键 -> {V9_MENU_NAME} (压完就走) 或 "
                f"{V9_QUEUE_MENU_NAME} (进主窗口队列, 可再挑)\n"
                f"  2. 右键文件夹 -> {V9_MENU_NAME_DIR} / {V9_QUEUE_MENU_NAME_DIR}\n"
                "  3. 右键 -> 发送到 -> 图瘦身\n"
                "  4. 双击桌面 图瘦身 -> 完整界面\n\n"
                "右键菜单没出现就按 F5 或重开文件夹窗口。\n"
                "卸载: 运行 uninstall.bat")
    return 0


def _v9_del_key(root, path: str) -> bool:
    import winreg
    try:
        k = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return False
    # 先删子键再删父键, DeleteKey 不递归
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(k, i)
        except OSError:
            break
        _v9_del_key(root, path + "\\" + sub)
        i += 1
    winreg.CloseKey(k)
    try:
        winreg.DeleteKey(root, path)
        return True
    except OSError:
        return False


def v9_uninstall(quiet: bool = False) -> int:
    """卸掉右键菜单 / 发送到 / 桌面快捷方式. 返回退出码."""
    import winreg

    lines: list[str] = []
    removed = 0
    # 现在的键 + 历史遗留的中文键都要删, 漏一个就会在菜单里留个点不掉的残影。
    for ctx_label, shell_path in (("图片", "Software\\Classes\\*\\shell"),
                                  ("文件夹", "Software\\Classes\\Directory\\shell")):
        for key in (V9_MENU_KEY_QUICK, V9_MENU_KEY_QUEUE) + V9_MENU_LEGACY_KEYS:
            ok = _v9_del_key(winreg.HKEY_CURRENT_USER, shell_path + "\\" + key)
            if ok:
                removed += 1
                lines.append(f"已移除{ctx_label}右键菜单: {key}")
    if not removed:
        lines.append("右键菜单: 本来就没有")

    sendto = Path(os.environ.get("APPDATA", str(Path.home()))) / \
        "Microsoft/Windows/SendTo"
    lnk_send = sendto / V9_SHORTCUT_NAME
    try:
        lnk_send.unlink(missing_ok=True)
        lines.append(f"已移除: 发送到 -> 图瘦身")
    except OSError:
        lines.append("发送到 -> 图瘦身: 删除失败")

    desk = _known_desktop()
    lnk_desk = desk / V9_SHORTCUT_NAME
    try:
        lnk_desk.unlink(missing_ok=True)
        lines.append(f"已移除: 桌面快捷方式 ({desk})")
    except OSError:
        lines.append("桌面快捷方式: 删除失败")

    _refresh_shell()

    dest = _v9_install_dir()
    if dest.exists():
        if quiet:
            keep = True
        else:
            keep = not _v9_box(
                V9_APP_TITLE,
                f"要删掉安装目录吗?\n\n{dest}\n\n"
                f"你的压缩结果不会被删(在 {Path.home() / V9_DEFAULT_OUT})。\n\n"
                "点\"是\"删除, 点\"否\"保留。",
                ask=True)
        if keep:
            lines.append(f"保留安装目录: {dest}")
        else:
            import shutil
            try:
                shutil.rmtree(dest)
                lines.append(f"已删除安装目录: {dest}")
            except OSError as e:
                lines.append(f"删除安装目录失败 ({e}), 请关掉图瘦身后重试")

    summary = "\n".join(lines)
    _v9_log(f"[uninstall] 完成\n{summary}")
    if not quiet:
        _v9_box(V9_APP_TITLE,
                f"卸载完成\n\n{summary}\n\n"
                f"你的压缩结果还留着, 没动:\n{Path.home() / V9_DEFAULT_OUT}\n\n"
                "右键菜单如果还看得到, 按 F5 或重开文件夹窗口就会消失。")
    return 0


# ---------------------------------------------------------------------------
# 单实例: 右键"加入压缩队列"时, 主窗口若已经开着, 绝不能再弹第二个窗口。
#
# 不做这一步的后果很具体: 右键 5 次 = 5 个主窗口, 队列被劈成 5 份, 每份都
# 缺图, 用户看到的是"这软件坏了", 而且完全猜不到原因。
#
# 做法: 命名互斥体判断主窗口在不在。在 → 把路径写进收件箱目录后本进程直接退出,
# 由主窗口每 400ms 轮询一次收件箱。
#
# 为什么不用 WM_COPYDATA / 命名管道: 那两条路要把 ctypes 回调接进 Tk 事件循环,
# 跨线程碰 Tk 是这个项目反复栽跟头的类型。收件箱方案是纯 Python、逻辑全在主
# 进程内、可以脱离 GUI 单测, 出问题也好定位。
# ---------------------------------------------------------------------------
V9_MUTEX_NAME = "Local\\PicShrink_Main_v1"
# 测试钩子: 指到临时目录, 免得跑测试往真机 %TEMP% 里丢收件箱文件。
V9_INBOX_ENV = "PIC SHRINK_INBOX"
V9_INBOX_POLL_MS = 400

_v9_main_mutex = None


def _v9_inbox_dir() -> Path:
    override = os.environ.get(V9_INBOX_ENV)
    if override:
        return Path(override)
    tmp = os.environ.get("TEMP") or os.environ.get("TMP") or str(Path.home())
    return Path(tmp) / "PicShrink" / "inbox"


def _v9_claim_main_instance() -> bool:
    """抢占主实例身份。True = 还没人在跑, 该由我开主窗口。

    用 WaitForSingleObject 而不是 get_last_error(): CreateMutexW 在对象已存在时
    照样返回句柄, 只有"能不能立刻拿到所有权"才区分得开主次。
    """
    global _v9_main_mutex
    if os.name != "nt":
        return True
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        k32.WaitForSingleObject.restype = ctypes.c_ulong
        k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        h = k32.CreateMutexW(None, True, V9_MUTEX_NAME)
        if not h:
            _v9_log("[single] CreateMutexW 失败, 按无主实例处理")
            return True
        # 句柄必须一直持有, 提前被 GC 掉就等于悄悄放开了所有权,
        # 第二个进程会以为没人在跑, 于是又开一个窗口 —— 正是要避免的那个坑。
        _v9_main_mutex = h
        owned = k32.WaitForSingleObject(h, 0) == 0x00000000  # WAIT_OBJECT_0
        _v9_log(f"[single] mutex={V9_MUTEX_NAME} 拿到主实例={owned}")
        return bool(owned)
    except Exception as e:
        _v9_log(f"[single] 互斥体异常 {e}, 按无主实例处理")
        return True


def _v9_drop_to_inbox(paths: list[str]) -> bool:
    """把路径交给已经在跑的主窗口, 然后本进程就该退出了。"""
    d = _v9_inbox_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _v9_log(f"[inbox] 建目录失败: {e}")
        return False
    # 先写 .tmp 再原子改名: 主窗口轮询时不可能读到写了一半的文件。
    stamp = f"{os.getpid()}.{int(time.time() * 1000)}"
    tmp = d / (stamp + ".tmp")
    dst = d / (stamp + ".drop")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for p in paths:
                f.write(p + "\n")
        os.replace(tmp, dst)
    except OSError as e:
        _v9_log(f"[inbox] 写失败: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    _v9_log(f"[inbox] 已投递 {len(paths)} 条 -> {dst}")
    return True


def _v9_drain_inbox() -> list[str]:
    """主窗口定时调, 收走所有已就绪的 .drop, 返回路径列表。"""
    d = _v9_inbox_dir()
    if not d.is_dir():
        return []
    now = time.time()
    got: list[str] = []
    try:
        entries = list(d.iterdir())
    except OSError:
        return []
    for f in entries:
        try:
            age = now - f.stat().st_mtime
        except OSError:
            continue
        if f.suffix == ".tmp":
            # .tmp 是写一半的中间产物, 正常会被改名成 .drop。
            # 超过 60s 还在的说明上一个实例中途崩了, 清理掉免得攒垃圾。
            if age > 60:
                try:
                    f.unlink()
                except OSError:
                    pass
            continue
        if f.suffix != ".drop":
            continue
        try:
            raw = f.read_text(encoding="utf-8")
        except OSError:
            # 读不到就先不删, 下轮轮询再试 —— 删了就真把数据丢了。
            continue
        try:
            f.unlink()
        except OSError:
            pass
        for line in raw.splitlines():
            s = line.strip()
            if s:
                got.append(s)
    if got:
        _v9_log(f"[inbox] 收到 {len(got)} 条")
    return got


def main(preload: list[Path] | None = None):
    # 双击 exe 也要占住主实例身份, 否则用户连续双击两次就会开出两个窗口。
    _v9_claim_main_instance()
    # v6: 用 tkinterdnd2 的 Tk 替换原生 tk.Tk, 才能让 listbox 接 OS 文件拖拽
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app = App(root)
    # 右键"加入压缩队列"靠这条 after 链接收路径。首次调用顺便把上一次崩溃
    # 遗留的 .drop 也收走, 避免用户白点一次右键。
    app._poll_inbox()
    # --gui 入口: 把命令行带来的图预载进待压缩列表, 让用户自己点"开始压缩"
    if preload:
        try:
            app._add_paths(preload)
        except Exception:
            pass
    root.mainloop()


if __name__ == "__main__":
    _argv = sys.argv[1:]
    # v11: 每次启动先把收到的原始参数落盘。
    # windowed 打包没有 stderr, Explorer 右键传了什么在界面上根本看不见,
    # 出了问题只能靠这一行定位 —— 之前"没找到可处理的图片"就是这么查的。
    _v9_log(f"[argv] exe={_v9_self_exe()}")
    _v9_log(f"[argv] raw={_argv!r}")
    _opts, _paths = _v9_parse(_argv)
    _v9_log(f"[argv] paths={_paths!r} opts={_opts!r}")
    _has_action = any(_opts[k] for k in ("install", "uninstall", "help",
                                          "list_presets", "gui"))
    # 双击 exe → 完整 GUI。
    # 另外: 右键菜单一个真实路径都没传进来时(raw=[''] 这类), 也走 GUI。
    # 以前这里弹"没找到可处理的图片"的大红叉, 但用户当时既没选图也没输命令,
    # 根本无从下手; 直接把主界面打开, 至少人是能用的, 而且 raw 已经落盘,
    # 真要查根因日志里有证据。
    if not _argv or (not _paths and not _has_action):
        if _argv:
            _v9_log("[argv] 一个真实路径都没收到, 按双击处理 → 打开完整 GUI")
        main()                                    # 双击 exe → 完整 GUI
    elif _opts["install"]:
        sys.exit(v9_install(quiet=_opts["quiet"]))
    elif _opts["uninstall"]:
        sys.exit(v9_uninstall(quiet=_opts["quiet"]))
    elif _opts["help"]:
        _v9_show_help(_opts["notify"])
    elif _opts["list_presets"]:
        _v9_show_presets(_opts["notify"])
    elif _opts["gui"]:
        _pre = _v9_expand(_paths)
        if not _pre:
            _pre = [Path(x) for x in _paths if Path(x.strip().strip('"')).exists()]
        # 主窗口已经开着 → 投递过去就退出, 绝不能再弹第二个窗口。
        # 不做这一步, 用户右键 5 次就看到 5 个窗口, 队列被劈成 5 份。
        if _pre and not _v9_claim_main_instance():
            if _v9_drop_to_inbox([str(p) for p in _pre]):
                _v9_log("[single] 已投递到运行中的主窗口, 本进程退出")
                sys.exit(0)
            # 投递失败只能退回"自己开一个": 宁可多一个窗口, 也不能让右键彻底失灵。
        main(preload=_pre)
    else:
        sys.exit(_v9_quick(_paths, _opts))        # 右键 / SendTo / 拖到图标
