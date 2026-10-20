"""
compress_images.py — 一键批量压缩图片，画质尽量保住，体积尽量小。

用法:
    python compress_images.py                    # 压当前目录下所有 jpg/png/bmp/webp
    python compress_images.py a.jpg b.png c/     # 压指定文件或目录
    python compress_images.py . --quality 80    # 调质量
    python compress_images.py . --format jpg    # 输出格式 (webp/jpg/png/auto)
    python compress_images.py . --max-side 2048 # 长边限制
    python compress_images.py . --out my_out    # 改输出目录

把下面那个 "拖我压缩.bat" 跟脚本放一起，图片直接拖到 bat 上也能跑。
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Windows GBK 控制台强制 UTF-8, 防 emoji/中文报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image

# Windows 上 Pillow 在多线程里偶尔会报 "Too many open files" / 解码竞争，
# 把线程数压到 4 是稳的。CPU 核数多也不用开更高，Pillow 解码是 IO bound。
MAX_WORKERS = 4

# 浏览器/系统/手机/亚马逊/微信 全都认识 WebP（亚马逊 2024 也支持 WebP 主图）。
# WebP 同画质比 JPEG 小 25-35%，比 PNG 小非常多。
DEFAULT_FORMAT = "webp"
DEFAULT_QUALITY = 85
DEFAULT_MAX_SIDE = 2560  # 亚马逊主图推荐 2000+，日常用 2560 防爆
SUPPORTED_INPUT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def collect_inputs(paths: list[str]) -> list[Path]:
    """把文件/目录/glob 展开成实际图片文件列表。"""
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(x for x in path.rglob("*") if x.suffix.lower() in SUPPORTED_INPUT))
        elif path.is_file():
            if path.suffix.lower() in SUPPORTED_INPUT:
                out.append(path)
            else:
                print(f"  跳过(不支持): {path.name}")
        else:
            # 当 glob 处理
            matches = sorted(Path(".").glob(p))
            if matches:
                out.extend(x for x in matches if x.suffix.lower() in SUPPORTED_INPUT)
    # 去重保序
    seen, uniq = set(), []
    for x in out:
        if x.resolve() not in seen:
            seen.add(x.resolve())
            uniq.append(x)
    return uniq


def pick_output_format(src: Path, fmt_arg: str) -> str:
    """auto 模式下: 透明图保留 PNG，否则走 WebP。"""
    if fmt_arg != "auto":
        return fmt_arg
    if src.suffix.lower() in {".png", ".tif", ".tiff"}:
        # 探测是否有 alpha
        try:
            with Image.open(src) as im:
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    return "png"
        except Exception:
            pass
    return "webp"


def compress_one(
    src: Path,
    out_root: Path,
    fmt: str,
    quality: int,
    max_side: int,
    keep_exif: bool,
) -> tuple[Path, int, int, str]:
    """
    压缩单张图。
    返回: (输出路径, 原始字节, 输出字节, 状态消息)
    """
    rel = src.parent  # 保持相对目录结构
    fmt_ext = "jpg" if fmt == "jpg" else fmt  # Pillow 要 "JPEG"
    out_dir = out_root / rel.name if rel != Path(".") else out_root
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}.{fmt_ext}"

    # 跳过已存在（断点续传）
    if out_path.exists():
        return (out_path, src.stat().st_size, out_path.stat().st_size, "已存在,跳过")

    src_bytes = src.stat().st_size
    try:
        with Image.open(src) as im:
            # 1) 模式归一化: 透明图不能转 RGB, 否则丢 alpha
            has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            if fmt == "jpg" and has_alpha:
                # JPEG 不支持透明 → 白色底合成
                bg = Image.new("RGB", im.size, (255, 255, 255))
                im_rgba = im.convert("RGBA")
                bg.paste(im_rgba, mask=im_rgba.split()[-1])
                im = bg
            elif fmt in ("jpg", "webp") and im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if has_alpha else "RGB")

            # 2) 长边限制
            w, h = im.size
            if max(w, h) > max_side:
                if w >= h:
                    nw, nh = max_side, int(h * max_side / w)
                else:
                    nw, nh = int(w * max_side / h), max_side
                im = im.resize((nw, nh), Image.LANCZOS)

            # 3) EXIF
            exif = im.info.get("exif") if keep_exif else None

            # 4) 保存
            save_kwargs: dict = {"optimize": True}
            if fmt in ("jpg", "webp"):
                save_kwargs["quality"] = quality
            if fmt == "webp":
                save_kwargs["method"] = 4  # 0-6, 4 是质量/速度甜点
            if exif:
                save_kwargs["exif"] = exif

            # Pillow 格式名: "jpg" -> "JPEG"
            save_fmt = "JPEG" if fmt == "jpg" else fmt.upper()
            im.save(out_path, save_fmt, **save_kwargs)
    except Exception as e:
        return (out_path, src_bytes, 0, f"失败:{e}")

    out_bytes = out_path.stat().st_size
    return (out_path, src_bytes, out_bytes, "ok")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="一键批量压缩图片 (WebP 优先, 质量 85, 长边 ≤ 2560)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("inputs", nargs="*", default=["."], help="图片文件 / 目录 / glob, 留空=当前目录")
    ap.add_argument("--out", default="compressed", help="输出根目录 (默认: ./compressed)")
    ap.add_argument("--quality", type=int, default=DEFAULT_QUALITY, help=f"质量 1-95 (默认 {DEFAULT_QUALITY})")
    ap.add_argument("--format", choices=["webp", "jpg", "png", "auto"], default="auto",
                    help=f"输出格式 (默认 auto, 透明图→png 否则→webp)")
    ap.add_argument("--max-side", type=int, default=DEFAULT_MAX_SIDE, help=f"长边像素上限 (默认 {DEFAULT_MAX_SIDE})")
    ap.add_argument("--keep-exif", action="store_true", help="保留 EXIF/拍摄信息")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"并行线程数 (默认 {MAX_WORKERS})")
    args = ap.parse_args()

    files = collect_inputs(list(args.inputs))
    if not files:
        print("没找到可压缩的图片 (支持: jpg/jpeg/png/bmp/webp/tif)")
        return 1

    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"找到 {len(files)} 张图 → 输出到 {out_root}")
    print(f"参数: format={args.format}  quality={args.quality}  max-side={args.max_side}  "
          f"keep-exif={args.keep_exif}  workers={args.workers}")
    print("-" * 70)

    total_in = total_out = 0
    ok = fail = skip = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {}
        for src in files:
            fmt = pick_output_format(src, args.format)
            futures[ex.submit(
                compress_one, src, out_root, fmt, args.quality, args.max_side, args.keep_exif
            )] = src
        for fut in as_completed(futures):
            src = futures[fut]
            out_path, ib, ob, msg = fut.result()
            if msg == "ok":
                ratio = (1 - ob / ib) * 100 if ib else 0
                print(f"  [OK] {src.name:40s} {human_size(ib):>9s} -> {human_size(ob):<9s} -{ratio:5.1f}%")
                total_in += ib
                total_out += ob
                ok += 1
            elif msg.startswith("已存在"):
                print(f"  [SKIP] {src.name:40s} 跳过 (目标已存在)")
                skip += 1
            else:
                print(f"  [FAIL] {src.name:40s} {msg}")
                fail += 1

    print("-" * 70)
    if total_in:
        saved = (1 - total_out / total_in) * 100
        print(f"完成: OK={ok}  SKIP={skip}  FAIL={fail}    "
              f"总体积 {human_size(total_in)} -> {human_size(total_out)}  (省 {saved:.1f}%)")
    else:
        print(f"完成: OK={ok}  SKIP={skip}  FAIL={fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
