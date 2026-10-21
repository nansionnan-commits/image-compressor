"""
图瘦身 (PicShrink) — 单文件 GUI 入口 (压缩引擎 + Tkinter + tkinterdnd2 OS 拖拽).

品牌: 中文名「图瘦身」/ 英文名 PicShrink / exe 名「图瘦身.exe」.
版本: v8 (按品牌 + 图标重做; 压缩引擎与 v7 同源, 7 预设 / 目标体积 / 像素零差异保护不变).

核心能力 (相对早期 v3/v4):
  - 7 个预设 (按"画质损失程度"分层):
      两个无损 / 三个有损 / 两个目标体积 (200KB / 120KB).
  - 真实 OS 拖拽 (tkinterdnd2 + tkdnd 2.10+) — 不只是 Listbox, 整个窗口都能拖.
  - 目标体积模式: 长边限位 + 质量二分搜索, 选择能达标的最高质量 (下限 q18).
  - 输出撞原图时自动加 _compressed 后缀; 重复运行覆盖旧压缩输出, 原图永不覆盖.
  - 像素零差异验证: ImageChops.difference(a,b).getbbox() is None.
  - 单文件 PyInstaller 打包, 内置 Python + Pillow + tkdnd 资源.
"""

import io
import os
import queue
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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

# ===== 7 个预设: 按"画质损失程度"分层 =====
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
    "📦 主图≤200KB": {"mode": "target", "format": "jpg", "max_side": 1280,
                  "target_kb": 200, "quality": 90, "keep_exif": False,
                  "desc": "长边 1280 + 自动降质量, 压到 ≤200KB"},
    "📦 主图≤120KB": {"mode": "target", "format": "jpg", "max_side": 1100,
                  "target_kb": 120, "quality": 90, "keep_exif": False,
                  "desc": "长边 1100 + 自动降质量, 压到 ≤120KB"},
}

# 预设分两行显示 (一行塞不下 7 个按钮会被截断)
PRESET_ROWS = [
    ["🎯 无损压缩", "💎 极致保真", "⚡ 推荐压缩", "💾 压最小"],
    ["🛒 亚马逊主图", "📦 主图≤200KB", "📦 主图≤120KB"],
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
    """返回 (Pillow 保存格式, 输出扩展名). 'keep' = 保持原格式."""
    if fmt_arg == "keep":
        ext = src.suffix.lower().lstrip(".")
        if ext == "tif":
            ext = "tiff"
        save_fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG",
                    "webp": "WEBP", "bmp": "BMP", "tiff": "TIFF"}.get(ext, "JPEG")
        return save_fmt, src.suffix.lower().lstrip(".") or "jpg"
    if fmt_arg == "auto":
        return pick_output_format(src, "keep")
    if fmt_arg == "jpg":
        return "JPEG", "jpg"
    return fmt_arg.upper(), "jpg" if fmt_arg == "jpg" else fmt_arg


def _apply_mode(im: Image.Image, mode: str, fmt: str, quality: int) -> Image.Image:
    """根据 mode 调整图像 (量化等) + 决定是否传 quality 参数."""
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)

    if fmt == "JPEG" and has_alpha:
        bg = Image.new("RGB", im.size, (255, 255, 255))
        im_rgba = im.convert("RGBA")
        bg.paste(im_rgba, mask=im_rgba.split()[-1])
        im = bg
    elif fmt in ("JPEG", "WEBP") and im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if has_alpha else "RGB")

    if fmt == "PNG" and mode in ("balanced", "aggressive"):
        colors = 256 if mode == "balanced" else 128
        if im.mode == "RGBA":
            # 透明图量化: 拆 alpha + RGB 量化 + 合并
            alpha = im.split()[-1]
            rgb = im.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
            rgb.putalpha(alpha)
            im = rgb
        elif im.mode != "P":
            im = im.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    return im


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
        buf = io.BytesIO()
        im.save(buf, fmt, quality=q, optimize=True, **kw_exif)
        return buf.getvalue()

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


def compress_one(src: Path, out_root: Path, mode: str, quality: int,
                 fmt: str, ext: str, max_side: int, keep_exif: bool,
                 skip_if_larger: bool = True,
                 target_kb: int = 0) -> tuple[Path, int, int, str]:
    """压缩单张. mode: lossless / balanced / aggressive / target.

    安全策略 (v7):
      - 输出路径永远不可能等于原图, 撞车自动加 _compressed 后缀
      - 原图只读, 任何分支都不覆盖原图
      - 上一轮生成的压缩结果会被直接覆盖重写 -> 重复点"开始压缩"不再一堆"跳过"

    返回 (输出路径, 原图字节, 输出字节, 状态消息)
      状态 "ok" 或 "ok|..." = 成功; 含"跳过" = 没压; 其余 = 失败
    """
    out_dir = out_root / (src.parent.name if src.parent != Path(".") else ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = _safe_out_path(src, out_dir, ext)
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
        if not _write_bytes(out_path, data):
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

            buf = io.BytesIO()
            im2.save(buf, fmt, **kw)
            data = buf.getvalue()

            if skip_if_larger and len(data) >= src_bytes * KEEP_IF_LARGER_RATIO:
                return (src, src_bytes, src_bytes,
                        f"跳过 (压完 {human_size(len(data))} ≥ 原图 {human_size(src_bytes)}, 保留原图)")

            if not _write_bytes(out_path, data):
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
            return (got, "")
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
            buf = io.BytesIO()
            im2.save(buf, fmt, **kw)
            return (buf.tell(), "")
    except Exception as e:
        return (0, f"预览失败:{e}")


class App:
    def __init__(self, root):
        self.root = root
        root.title("图瘦身 v8 (拖图片/文件夹进窗口, 7 预设 + 按目标体积压)")
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
        # 7 个预设分 2 行, 一行塞不下会被截断
        for row_names in PRESET_ROWS:
            row = ttk.Frame(preset_frame)
            row.pack(fill="x")
            for name in row_names:
                ttk.Button(row, text=name, width=15,
                           command=lambda n=name: self.apply_preset(n)).pack(side="left", padx=2, pady=2)
        self.preset_hint = ttk.Label(preset_frame, text="默认: ⚡ 推荐压缩 (q=85 业界甜点)",
                                      foreground="#06c", wraplength=380)
        self.preset_hint.pack(anchor="w", padx=4, pady=2)

        self.show_custom = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text="显示自定义参数 (高级用户)",
                        variable=self.show_custom, command=self._toggle_custom).pack(anchor="w", padx=4)

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
                                      values=["保持原格式 (推荐)", "JPG", "PNG"],
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
                 "   📦 两个预设按目标体积压: 自动二分搜索最高能达标的质量.\n"
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

    def apply_preset(self, name: str, silent: bool = False):
        p = PRESETS[name]
        self.mode_var.set(MODE_LABELS[p["mode"]])
        self.quality_var.set(p.get("quality", 85))
        self.q_label.config(text=str(self.quality_var.get()))
        fmt_label = {"keep": "保持原格式 (推荐)", "jpg": "JPG",
                     "png": "PNG"}.get(p.get("format", "keep"), "保持原格式 (推荐)")
        self.fmt_var.set(fmt_label)
        side_label = "原图" if p.get("max_side", 0) == 0 else str(p["max_side"])
        if side_label not in self.side_combo["values"]:
            self.side_combo["values"] = list(self.side_combo["values"]) + [side_label]
        self.side_var.set(side_label)
        self.exif_var.set(p.get("keep_exif", False))
        self.target_var.set(str(p.get("target_kb", 0)))
        self.preset_hint.config(text=f"已选: {name}  ({p['desc']})")
        if not silent:
            self._log(f">>> 预设: {name}  ({p['desc']})\n")
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
               "PNG": "png"}.get(self.fmt_var.get(), "keep")
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
                                f"想真压, 换 ⚡ 推荐压缩 或 📦 主图≤200KB")
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


def main():
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
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
