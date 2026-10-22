# -*- coding: utf-8 -*-
"""打便携 ZIP: dist/PicShrink-v11.2-portable.zip

包里只放 5 个文件, 保持"解压就能双击"的直觉:
  PicShrink.exe  install.bat  uninstall.bat  README.md  LICENSE

安装器脚本的硬约束: install.bat / uninstall.bat 必须纯 ASCII (cmd 按活动
控制台码页解析 .bat, 中文会被切乱码导致连 exe 都找不到)。这里构建时校验,
防止哪天有人往 bat 里加了中文还没人发现。
"""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
EXE = DIST / "PicShrink.exe"
ZIP = DIST / "PicShrink-v11.2-portable.zip"
MEMBERS = ["PicShrink.exe", "install.bat", "uninstall.bat", "README.md", "LICENSE"]
# exe 在 dist/ 下, 其余在项目根
SOURCES = {m: (DIST / m if m == "PicShrink.exe" else ROOT / m) for m in MEMBERS}


def main() -> int:
    missing = [str(p) for m, p in SOURCES.items() if not p.is_file()]
    if missing:
        print("缺文件:")
        for p in missing:
            print("   ", p)
        if EXE.is_file() is False and (ROOT / "dist").is_dir():
            print("  -> dist/PicShrink.exe 不存在, 先 PyInstaller 打包")
        return 2

    # 纯 ASCII 校验 (含 CRLF 校验)
    for name in ("install.bat", "uninstall.bat"):
        raw = (ROOT / name).read_bytes()
        bad = [i for i, b in enumerate(raw) if b > 127]
        if bad:
            print(f"FAIL {name} 含非 ASCII 字节 {len(bad)} 处, 不能放进便携包")
            return 1
        lf = raw.count(b"\n")
        crlf = raw.count(b"\r\n")
        if lf != crlf:
            print(f"FAIL {name} 换行不是纯 CRLF (LF={lf} CRLF={crlf})")
            return 1
        print(f"  OK {name}: {len(raw)} 字节, 纯 ASCII, 全 CRLF")

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for m in MEMBERS:
            z.write(SOURCES[m], arcname=m)

    print(f"\n{ZIP}  {ZIP.stat().st_size:,} 字节")
    with zipfile.ZipFile(ZIP) as z:
        for i in z.infolist():
            print(f"   {i.filename:<18} {i.file_size:>12,} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())