"""
_core.py — 旧版压缩引擎 (无 GUI 依赖)

⚠️ v6 / v7 已不再 import 此文件
   - v6 起 `compress_images_gui.py` 把压缩引擎 + `_safe_out_path()` + target 二分搜索
     都内联进了自己文件, 完全自包含, 没有外部依赖。
   - v5 的 Flet 版 (`compress_images_flet.py`) 已经回退。
   - CLI `compress_images.py` 也是独立自包含的 (WebP 默认输出)。
   本文件仅作历史档案保留, 但 PRESETS 与 GUI 同步在 v6/v7 之间手动对齐过。
   如果之后又有人需要把 GUI 拆出独立引擎, 直接以 `compress_images_gui.py` 里
   的 `_safe_out_path / _encode_to_target / compress_one / compress_to_bytes` 为起点
   复制, 不要从这里继续改 —— 这份的函数体还是 v4 时代的旧路径逻辑, 不支持
   target 模式与新安全策略。
"""

import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

# 集成纯 Python jpeg 优化器 (替代 jpegoptim, 剥 EXIF 真 0 损失)
try:
    from _jpeg_strip import optimize_jpeg
    HAS_JPEG_STRIP = True
except ImportError:
    HAS_JPEG_STRIP = False


SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

# ===== 7 个预设: 与 compress_images_gui.py 保持一致 =====
#   lossless    = 纯 Python 剥 EXIF (真 0 损失) + PIL PNG optimize
#   balanced    = q=85 重编码 (业界甜点)
#   aggressive  = q=80 重编码 (省最多)
#   amazon      = jpg 2000px q=85
#   target      = 先限长边, 再二分搜索质量压到目标字节数以内
PRESETS = {
    "🎯 无损压缩": {
        "mode": "lossless", "keep_exif": False, "max_side": 0, "format": "keep",
        "quality": 0, "desc": "剥 EXIF 真 0 损失, JPG 省 5-20%",
    },
    "💎 极致保真": {
        "mode": "lossless", "keep_exif": True, "max_side": 0, "format": "keep",
        "quality": 0, "desc": "无损+保留 EXIF, 跟上面一样省",
    },
    "⚡ 推荐压缩": {
        "mode": "balanced", "keep_exif": False, "max_side": 0, "format": "keep",
        "quality": 85, "desc": "q=85 业界甜点, 省 25% 肉眼难辨",
    },
    "💾 压最小": {
        "mode": "aggressive", "keep_exif": False, "max_side": 0, "format": "keep",
        "quality": 80, "desc": "q=80 重编码, 省最多",
    },
    "🛒 亚马逊主图": {
        "mode": "balanced", "keep_exif": False, "max_side": 2000, "format": "jpg",
        "quality": 85, "desc": "2000px JPG 符合 Amazon 主图要求",
    },
    "📦 主图≤200KB": {
        "mode": "target", "keep_exif": False, "max_side": 1280, "format": "jpg",
        "quality": 90, "target_kb": 200, "desc": "长边 1280 + 自动降质量, 压到 ≤200KB",
    },
    "📦 主图≤120KB": {
        "mode": "target", "keep_exif": False, "max_side": 1100, "format": "jpg",
        "quality": 90, "target_kb": 120, "desc": "长边 1100 + 自动降质量, 压到 ≤120KB",
    },
}

MIN_SIZE_SKIP = 50 * 1024
KEEP_IF_LARGER_RATIO = 0.95
TARGET_MIN_Q = 18          # 目标大小模式允许降到的最低质量
LOSSLESS_MIN_SAVED = 1024  # 无损模式至少要省这么多字节才值得另存一个文件
DEFAULT_OUTPUT_DIR = "compressed"


def human_size(n: int | float) -> str:
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
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        has_alpha = True
    else:
        has_alpha = False

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
            alpha = im.split()[-1]
            rgb = im.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
            rgb.putalpha(alpha)
            im = rgb
        elif im.mode != "P":
            im = im.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    return im


def _save_kwargs(mode: str, fmt: str, quality: int, keep_exif: bool, src: Image.Image) -> dict:
    kw: dict = {"optimize": True}
    if keep_exif and "exif" in src.info:
        kw["exif"] = src.info["exif"]
    if fmt in ("JPEG", "WEBP"):
        if mode == "lossless":
            pass  # 不传 quality → 用原图 quality, 即真无损
        else:
            kw["quality"] = quality
        if fmt == "WEBP" and mode != "lossless":
            kw["method"] = 4
    return kw


def compress_one(src: Path, out_root: Path, preset_name: str,
                 skip_if_larger: bool = True) -> dict:
    """压一张图, 返回 dict.

    返回字段:
      out_path    → 实际输出文件路径 (智能回退时 = src 原路径)
      src_bytes   → 原图字节
      out_bytes   → 实际写入字节 (0 表示失败, 等于 src_bytes 表示跳过或回退)
      saved_bytes → 省的字节 (可能负数, 表示回退)
      status      → "ok" / "skipped_small" / "skipped_exists" / "kept_original" /
                    "no_exif_to_strip" / "lossless_failed" / "failed:<reason>"
      preset_name → 用的预设
    """
    p = PRESETS[preset_name]
    mode = p["mode"]
    quality = p["quality"]
    fmt_arg = p["format"]
    max_side = p["max_side"]
    keep_exif = p["keep_exif"]

    fmt, ext = pick_output_format(src, fmt_arg)
    out_dir = out_root / (src.parent.name if src.parent != Path(".") else ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}.{ext}"
    src_bytes = src.stat().st_size

    if src_bytes < MIN_SIZE_SKIP:
        return {"out_path": out_path, "src_bytes": src_bytes, "out_bytes": src_bytes,
                "saved_bytes": 0, "status": "skipped_small",
                "preset_name": preset_name, "src": src}

    if out_path.exists() and out_path.resolve() != src.resolve():
        try:
            return {"out_path": out_path, "src_bytes": src_bytes,
                    "out_bytes": out_path.stat().st_size, "saved_bytes": 0,
                    "status": "skipped_exists", "preset_name": preset_name, "src": src}
        except OSError:
            pass

    if mode == "lossless" and fmt == "JPEG" and HAS_JPEG_STRIP and max_side == 0:
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        ok, ib, ob = optimize_jpeg(src, tmp, strip_all=not keep_exif, keep_jfif=True)
        if not ok:
            try: tmp.unlink(missing_ok=True)
            except OSError: pass
            return {"out_path": out_path, "src_bytes": src_bytes, "out_bytes": 0,
                    "saved_bytes": 0, "status": "lossless_failed",
                    "preset_name": preset_name, "src": src}
        if ob == src_bytes and not keep_exif:
            try: tmp.unlink(missing_ok=True)
            except OSError: pass
            return {"out_path": out_path, "src_bytes": src_bytes, "out_bytes": src_bytes,
                    "saved_bytes": 0, "status": "no_exif_to_strip",
                    "preset_name": preset_name, "src": src}
        if skip_if_larger and ob >= src_bytes * KEEP_IF_LARGER_RATIO:
            try: tmp.unlink(missing_ok=True)
            except OSError: pass
            return {"out_path": src, "src_bytes": src_bytes, "out_bytes": src_bytes,
                    "saved_bytes": 0, "status": "kept_original",
                    "preset_name": preset_name, "src": src}
        if out_path.exists() and out_path.resolve() != src.resolve():
            try: out_path.unlink()
            except OSError: pass
        try:
            tmp.rename(out_path)
        except OSError:
            return {"out_path": out_path, "src_bytes": src_bytes, "out_bytes": 0,
                    "saved_bytes": 0, "status": "rename_failed",
                    "preset_name": preset_name, "src": src}
        return {"out_path": out_path, "src_bytes": src_bytes, "out_bytes": ob,
                "saved_bytes": src_bytes - ob, "status": "ok",
                "preset_name": preset_name, "src": src}

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
            tmp = out_path.with_suffix(out_path.suffix + ".tmp")
            im2.save(tmp, fmt, **kw)
            tmp_bytes = tmp.stat().st_size
            if skip_if_larger and tmp_bytes >= src_bytes * KEEP_IF_LARGER_RATIO:
                try: tmp.unlink(missing_ok=True)
                except OSError: pass
                return {"out_path": src, "src_bytes": src_bytes, "out_bytes": src_bytes,
                        "saved_bytes": 0, "status": "kept_original",
                        "preset_name": preset_name, "src": src}
            if out_path.exists() and out_path.resolve() != src.resolve():
                try: out_path.unlink()
                except OSError: pass
            try:
                tmp.rename(out_path)
            except OSError:
                return {"out_path": out_path, "src_bytes": src_bytes, "out_bytes": 0,
                        "saved_bytes": 0, "status": "rename_failed",
                        "preset_name": preset_name, "src": src}
            return {"out_path": out_path, "src_bytes": src_bytes, "out_bytes": tmp_bytes,
                    "saved_bytes": src_bytes - tmp_bytes, "status": "ok",
                    "preset_name": preset_name, "src": src}
    except Exception as e:
        return {"out_path": out_path, "src_bytes": src_bytes, "out_bytes": 0,
                "saved_bytes": 0, "status": f"failed:{e}",
                "preset_name": preset_name, "src": src}


def preview_size(src: Path, preset_name: str) -> int | None:
    """预览: 不写盘, 估算压缩后字节数. 出错返回 None."""
    p = PRESETS[preset_name]
    src_bytes = src.stat().st_size
    if src_bytes < MIN_SIZE_SKIP:
        return src_bytes

    if p["mode"] == "lossless" and p["format"] == "keep" and src.suffix.lower() in (".jpg", ".jpeg"):
        ext = src.suffix.lower()
        save_fmt = "JPEG"
        if HAS_JPEG_STRIP and p["max_side"] == 0:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                ok, _, ob = optimize_jpeg(src, tmp_path,
                                           strip_all=not p["keep_exif"],
                                           keep_jfif=True)
                if ok:
                    return ob
            finally:
                try: tmp_path.unlink(missing_ok=True)
                except OSError: pass

    try:
        with Image.open(src) as im:
            im2 = _apply_mode(im, p["mode"], save_fmt, p["quality"])
            w, h = im2.size
            if p["max_side"] and max(w, h) > p["max_side"]:
                if w >= h:
                    nw, nh = p["max_side"], int(h * p["max_side"] / w)
                else:
                    nw, nh = int(w * p["max_side"] / h), p["max_side"]
                im2 = im2.resize((nw, nh), Image.LANCZOS)
            kw = _save_kwargs(p["mode"], save_fmt, p["quality"], p["keep_exif"], im)
            buf = io.BytesIO()
            im2.save(buf, save_fmt, **kw)
            return buf.tell()
    except Exception:
        return None


def batch_compress(files: list[Path], preset_name: str, out_root: Path,
                   max_workers: int = 4,
                   on_progress=None) -> list[dict]:
    """并发批量压缩. on_progress(done, total, latest_result) 每完成一张调一次."""
    results: list[dict] = []
    done = 0
    total = len(files)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(compress_one, f, out_root, preset_name): f
                   for f in files}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            done += 1
            if on_progress:
                try:
                    on_progress(done, total, r)
                except Exception:
                    pass
    return results