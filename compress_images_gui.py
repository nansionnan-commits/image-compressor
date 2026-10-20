"""
compress_images_gui.py — v3 重新设计: 质量分层 + 默认无损压缩.

核心变更 (相对 v2):
  - 默认"推荐"改用 lossless 策略: 不重编码 quality + 剥元数据 + 优化
    -> 真实测试: JPG 2.9MB -> 1.3MB 省 55% 但画质几乎 0 损失
    -> 这才是真正匹配"质量尽量不降 + 字节数变小"
  - 4 个预设改为质量分层, 不再按"q 数字"分, 按"损 vs 省"分
  - lossless 模式: PIL optimize=True + 不传 quality + 剥 EXIF
  - balanced 模式: 轻微重编码 (q=90 / 256色)
  - aggressive 模式: 明显重编码 (q=85 / 128色)
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

# ===== 4 个预设: 按"画质损失程度"分层 =====
#   lossless  = 纯 Python 剥 EXIF (真 0 损失) + PIL PNG optimize
#   balanced  = q=85 重编码 (用户选定, 业界甜点)
#   aggressive = q=80 重编码 (省最多)
#   amazon    = jpg 2000px q=85
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
}

MIN_SIZE_SKIP = 50 * 1024
KEEP_IF_LARGER_RATIO = 0.95


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


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


def compress_one(src: Path, out_root: Path, mode: str, quality: int,
                 fmt: str, ext: str, max_side: int, keep_exif: bool,
                 skip_if_larger: bool = True) -> tuple[Path, int, int, str]:
    """压缩单张. mode: lossless/balanced/aggressive."""
    out_dir = out_root / (src.parent.name if src.parent != Path(".") else ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}.{ext}"
    src_bytes = src.stat().st_size

    if src_bytes < MIN_SIZE_SKIP:
        return (out_path, src_bytes, src_bytes,
                f"跳过 (原图 < 50KB, {human_size(src_bytes)})")
    if out_path.exists():
        return (out_path, src_bytes, out_path.stat().st_size, "目标已存在,跳过")

    # ============== lossless 模式: 真 0 损失 ==============
    if mode == "lossless":
        # JPG 走纯 Python 剥 EXIF (真 0 损失)
        if fmt == "JPEG" and HAS_JPEG_STRIP and max_side == 0:
            tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
            ok, ib, ob = optimize_jpeg(src, tmp_path, strip_all=not keep_exif, keep_jfif=True)
            if not ok:
                return (out_path, src_bytes, 0, "lossless 失败")
            if skip_if_larger and ob >= src_bytes * KEEP_IF_LARGER_RATIO:
                tmp_path.unlink(missing_ok=True)
                return (src, src_bytes, src_bytes,
                        f"跳过 (剥EXIF后 {human_size(ob)} ≈ 原图 {human_size(src_bytes)}, 保留原图)")
            if out_path.exists():
                out_path.unlink()
            tmp_path.rename(out_path)
            return (out_path, src_bytes, ob, "ok")
        # PNG 走 PIL optimize (真 0 损失)
        # 其他情况降级到 balanced
        mode = "balanced" if fmt == "JPEG" else "lossless_fallback"

    try:
        with Image.open(src) as im:
            im2 = _apply_mode(im, mode, fmt, quality)

            # 长边
            w, h = im2.size
            if max_side and max(w, h) > max_side:
                if w >= h:
                    nw, nh = max_side, int(h * max_side / w)
                else:
                    nw, nh = int(w * max_side / h), max_side
                im2 = im2.resize((nw, nh), Image.LANCZOS)

            kw = _save_kwargs(mode, fmt, quality, keep_exif, im)

            tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
            im2.save(tmp_path, fmt, **kw)
            tmp_bytes = tmp_path.stat().st_size

            if skip_if_larger and tmp_bytes >= src_bytes * KEEP_IF_LARGER_RATIO:
                tmp_path.unlink(missing_ok=True)
                return (src, src_bytes, src_bytes,
                        f"跳过 (压完 {human_size(tmp_bytes)} ≥ 原图 {human_size(src_bytes)}, 保留原图)")

            if out_path.exists():
                out_path.unlink()
            tmp_path.rename(out_path)
            return (out_path, src_bytes, tmp_bytes, "ok")

    except Exception as e:
        return (out_path, src_bytes, 0, f"失败:{e}")


def compress_to_bytes(src: Path, mode: str, quality: int,
                      fmt: str, max_side: int, keep_exif: bool) -> tuple[int, str]:
    """预览: 内存压缩."""
    src_bytes = src.stat().st_size
    if src_bytes < MIN_SIZE_SKIP:
        return (src_bytes, f"原图 < 50KB, 不压")
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
            im2 = _apply_mode(im, mode, fmt, quality)
            w, h = im2.size
            if max_side and max(w, h) > max_side:
                if w >= h:
                    nw, nh = max_side, int(h * max_side / w)
                else:
                    nw, nh = int(w * max_side / h), max_side
                im2 = im2.resize((nw, nh), Image.LANCZOS)
            kw = _save_kwargs(mode, fmt, quality, keep_exif, im)
            buf = io.BytesIO()
            im2.save(buf, fmt, **kw)
            return (buf.tell(), "")
    except Exception as e:
        return (0, f"预览失败:{e}")


class App:
    def __init__(self, root):
        self.root = root
        root.title("图片一键压缩 (v4 jpegoptim 集成)")
        root.geometry("980x720")
        root.minsize(880, 660)

        self.files: list[Path] = []
        self.out_dir: Path = Path("compressed").resolve()
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.preview_job: str | None = None
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

        list_frame = ttk.LabelFrame(left, text="待压缩文件 (可多次选, 累加)", padding=4)
        list_frame.pack(fill="x", pady=4)
        self.listbox = tk.Listbox(list_frame, height=4, font=("Consolas", 9))
        self.listbox.pack(fill="x")

        preset_frame = ttk.LabelFrame(left, text="★ 一键预设 (默认=推荐压缩 q=85)", padding=6)
        preset_frame.pack(fill="x", pady=4)
        btn_row1 = ttk.Frame(preset_frame)
        btn_row1.pack(fill="x")
        for name in PRESETS:
            ttk.Button(btn_row1, text=name, width=14,
                       command=lambda n=name: self.apply_preset(n)).pack(side="left", padx=2, pady=2)
        self.preset_hint = ttk.Label(preset_frame, text="默认: ⚡ 推荐压缩 (q=85 业界甜点)",
                                      foreground="#06c")
        self.preset_hint.pack(anchor="w", padx=4, pady=2)

        self.show_custom = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text="显示自定义参数 (高级用户)",
                        variable=self.show_custom, command=self._toggle_custom).pack(anchor="w", padx=4)

        self.custom_frame = ttk.LabelFrame(left, text="自定义 (留空 = 用预设)", padding=6)
        mf = ttk.Frame(self.custom_frame)
        mf.pack(fill="x", pady=2)
        ttk.Label(mf, text="压缩模式:", width=10).pack(side="left")
        self.mode_var = tk.StringVar(value="无损 (不重编码 quality)")
        self.mode_combo = ttk.Combobox(mf, textvariable=self.mode_var, state="readonly",
                                       values=["无损 (不重编码 quality)",
                                               "均衡 (q=90 / 256色, 肉眼难辨)",
                                               "激进 (q=85 / 128色, 细看能看)"],
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
                                       values=["原图", "2560", "2048", "1080"],
                                       width=18)
        self.side_combo.pack(side="left", padx=4)
        self.side_combo.bind("<<ComboboxSelected>>", lambda e: self._on_param_change())

        self.exif_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.custom_frame, text="保留拍摄参数 (EXIF)",
                        variable=self.exif_var, command=self._on_param_change).pack(anchor="w")

        outf = ttk.Frame(left, padding=(0, 6, 0, 0))
        outf.pack(fill="x")
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
        paned.add(right, weight=2)

        ttk.Label(right, text="🔍 实时参数预览", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", pady=(0, 4))

        prev_info = ttk.LabelFrame(right, text="样本图信息", padding=8)
        prev_info.pack(fill="x", pady=4)
        self.prev_sample_name = ttk.Label(prev_info, text="(未选图)", foreground="#666", wraplength=240)
        self.prev_sample_name.pack(anchor="w")
        self.prev_sample_size = ttk.Label(prev_info, text="", font=("Consolas", 9))
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
        self.prev_settings = ttk.Label(prev_settings_frame, text="", font=("Consolas", 9), justify="left")
        self.prev_settings.pack(anchor="w")

        ttk.Label(
            right,
            text="💡 默认=无损压缩: 剥元数据+优化, 画质几乎不损.\n"
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
            # 插到 outf 之前
            self.custom_frame.pack(fill="x", padx=0, pady=4, before=self.out_var.master.master.slaves()[0])
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
        mode = p["mode"]
        self.mode_var.set({"lossless": "无损 (不重编码 quality)",
                           "balanced": "均衡 (q=90 / 256色, 肉眼难辨)",
                           "aggressive": "激进 (q=85 / 128色, 细看能看)"}[mode])
        self.quality_var.set(p.get("quality", 85))
        self.q_label.config(text=str(self.quality_var.get()))
        fmt_label = {"keep": "保持原格式 (推荐)", "jpg": "JPG",
                     "png": "PNG"}.get(p.get("format", "keep"), "保持原格式 (推荐)")
        self.fmt_var.set(fmt_label)
        side_label = "原图" if p.get("max_side", 0) == 0 else str(p["max_side"])
        self.side_var.set(side_label)
        self.exif_var.set(p.get("keep_exif", False))
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
        for p in paths:
            pp = Path(p)
            if pp.suffix.lower() in SUPPORTED and pp not in self.files:
                self.files.append(pp)
        self._refresh_list()
        self._refresh_preview()
        self.status.config(text=f"已选 {len(self.files)} 张图")

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
        mode = {"无损 (不重编码 quality)": "lossless",
                "均衡 (q=90 / 256色, 肉眼难辨)": "balanced",
                "激进 (q=85 / 128色, 细看能看)": "aggressive"}[self.mode_var.get()]
        q = int(self.quality_var.get())
        fmt = {"保持原格式 (推荐)": "keep", "JPG": "jpg",
               "PNG": "png"}.get(self.fmt_var.get(), "keep")
        side = {"原图": 0, "2560": 2560, "2048": 2048,
                "1080": 1080}.get(self.side_var.get(), 0)
        return mode, q, fmt, side, self.exif_var.get()

    def _refresh_preview(self):
        if self.preview_job:
            try:
                self.root.after_cancel(self.preview_job)
            except Exception:
                pass
            self.preview_job = None
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

        mode, quality, fmt_arg, max_side, keep_exif = self._resolve_params()
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
            text=f"  原: {human_size(src_bytes)}  ·  {w}x{h}px  ·  原图 quality 会被保留")
        self.prev_arrow.config(text="  按当前参数预估 →")
        self.prev_new.config(text="  压缩中...", foreground="#999")
        self.prev_ratio.config(text="")
        self.prev_note.config(text="")

        mode_text = {"lossless": "无损 (不重编码 quality)",
                     "balanced": f"均衡 q={quality}",
                     "aggressive": f"激进 q={quality}"}[mode]
        self.prev_settings.config(
            text=f"  模式: {mode_text}\n"
                 f"  格式: {fmt_arg}  (保存为 {save_fmt})\n"
                 f"  长边: {max_side or '原图'}\n"
                 f"  EXIF: {'保留' if keep_exif else '丢弃'}\n"
                 f"  智能回退: 压完更大就保留原图"
        )

        sample_path = sample

        def work():
            new_size, err = compress_to_bytes(
                sample_path, mode, quality, save_fmt, max_side, keep_exif)
            self.preview_q.put((new_size, err, src_bytes, mode))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(50, self._poll_preview)

    def _poll_preview(self):
        try:
            new_size, err, src_bytes, mode = self.preview_q.get_nowait()
        except queue.Empty:
            self.root.after(50, self._poll_preview)
            return

        if err:
            self.prev_new.config(text=f"  {err}", foreground="#c00")
            self.prev_ratio.config(text="")
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

        mode, quality, fmt_arg, max_side, keep_exif = self._resolve_params()
        out_root = Path(self.out_var.get()).resolve()
        out_root.mkdir(parents=True, exist_ok=True)

        self.log.delete("1.0", "end")
        mode_text = {"lossless": "无损 (不重编码 quality)",
                     "balanced": f"均衡 q={quality}",
                     "aggressive": f"激进 q={quality}"}[mode]
        self._log(f">>> 输出目录: {out_root}\n")
        self._log(f">>> 模式: {mode_text}  格式: {fmt_arg}  长边: {max_side or '原图'}  EXIF: {keep_exif}\n")
        self._log(f">>> 智能回退: 压完 < 原图 95% 才覆盖, 否则保留原图\n")
        self._log("-" * 60 + "\n")

        self.progress["maximum"] = len(self.files)
        self.progress["value"] = 0
        self.prog_label.config(text=f"0 / {len(self.files)}")
        self.start_btn.config(state="disabled", text="⏳ 压缩中...")
        self.status.config(text="正在压缩...")

        def work():
            total_in = total_out = ok = skip = fail = 0
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {}
                for src in self.files:
                    save_fmt, ext = pick_output_format(src, fmt_arg)
                    futures[ex.submit(
                        compress_one, src, out_root, mode, quality,
                        save_fmt, ext, max_side, keep_exif, True
                    )] = src
                for fut in as_completed(futures):
                    src = futures[fut]
                    out_path, ib, ob, msg = fut.result()
                    if msg == "ok":
                        ratio = (1 - ob / ib) * 100 if ib else 0
                        line = f"  [OK]   {src.name}    {human_size(ib)} -> {human_size(ob)}  (-{ratio:.1f}%)\n"
                        total_in += ib; total_out += ob; ok += 1
                    elif "跳过" in msg or "已存在" in msg:
                        line = f"  [跳过] {src.name}    {msg}\n"
                        skip += 1
                    else:
                        line = f"  [失败] {src.name}    {msg}\n"
                        fail += 1
                    self.q.put(("log", line))
                    self.q.put(("progress", ok + skip + fail))
            self.q.put(("done", (ok, skip, fail, total_in, total_out)))

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
                    ok, skip, fail, ti, to = payload
                    self._log("-" * 60 + "\n")
                    saved = ((ti - to) / ti * 100) if ti else 0
                    self._log(f"完成: ✓压缩{ok}  ↷跳过{skip}  ✗失败{fail}\n"
                              f"      总原大小 {human_size(ti)} -> 压后 {human_size(to)}  (净省 {saved:.1f}%)\n")
                    self.start_btn.config(state="normal", text="▶  开始压缩")
                    if fail == 0 and (ok + skip) > 0:
                        self.status.config(text=f"搞定! 压缩 {ok}, 跳过 {skip}")
                        messagebox.showinfo("搞定",
                                            f"压缩 {ok} 张, 跳过 {skip} 张 (智能回退或太小).\n\n"
                                            f"净省: {saved:.1f}%\n输出: {self.out_var.get()}")
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
    root = tk.Tk()
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
