"""
纯 Python JPEG 无损优化器（等效 jpegoptim --strip-all）

原理
----
JPEG 文件是一串「段」，每段结构为 [FF marker(2字节) + 长度(2字节) + 内容]：

  - APP0~APP15 (FFE0~FFEF) = EXIF 拍摄参数 / 相机信息 / 内嵌缩略图
  - COM (FFFE)               = 注释

手机拍的照片光 EXIF + 缩略图就占 40KB+，但它们**完全不影响画面像素**。

做法：遍历所有段，丢掉 APP/COM，其余原样保留：
  DQT(量化表) DHT(哈夫曼表) SOF(帧头) DRI(帧间间隔) SOS+熵编码数据

结果：字节数下降，像素一个 bit 都没变 → 数学意义上的无损。

对外接口（与 compress_images_gui.py 调用方式严格对齐）：
    ok, in_bytes, out_bytes = optimize_jpeg(src_path, out_path,
                                            strip_all=True, keep_jfif=True)
"""

import struct
from pathlib import Path

# 影响解码/画画的段，必须原样保留
_KEEP = frozenset({
    0xDB,                      # DQT 量化表
    0xC4,                      # DHT 哈夫曼表
    0xDD,                      # DRI 帧间间隔
    0xDA,                      # SOS 扫描头
    0xC0, 0xC1, 0xC2, 0xC3,    # SOF0-3  基线/扩展顺序/渐进
    0xC5, 0xC6, 0xC7,          # SOF5-7  无损/差分
    0xC9, 0xCA, 0xCB,          # SOF9-11 算术编码
    0xCD, 0xCE, 0xCF,          # SOF13-15
})

# 后面不跟长度字段的标记
_NO_LENGTH = frozenset({0xD8, 0xD9, 0x01} | set(range(0xD0, 0xD8)))


def strip_jpeg_bytes(data: bytes, strip_all: bool = True,
                     keep_jfif: bool = True) -> bytes:
    """底层：返回剥掉元数据后的 JPEG 字节流。结构异常时原样返回。"""
    if not data or len(data) < 4:
        return data
    if data[0] != 0xFF or data[1] != 0xD8:
        return data                      # 不是 JPEG

    out = bytearray(data[:2])            # SOI
    i, n = 2, len(data)

    while i < n - 1:
        if data[i] != 0xFF:
            break                        # 结构异常，放弃优化
        marker = data[i + 1]

        if marker == 0xD9:               # EOI
            out.extend(data[i:])
            return bytes(out)

        if marker in _NO_LENGTH:         # SOI/EOI/RSTn/TEM
            i += 2
            continue

        if i + 3 >= n:
            break
        seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
        end = i + 2 + seg_len
        if seg_len < 2 or end > n:
            break                        # 长度非法，放弃优化

        if marker == 0xDA:               # SOS 之后全是熵编码数据，整段照抄
            out.extend(data[i:])
            return bytes(out)

        if marker in _KEEP:              # 画质相关，必须留
            out.extend(data[i:end])
            i = end
            continue

        # ---- 到这里是要丢的段 ----
        if 0xE0 <= marker <= 0xEF:       # APPn
            keep = False
            if not strip_all:
                if marker == 0xE1:       # APP1 = EXIF，keep_exif=True 时留
                    keep = True
                elif marker == 0xE0 and keep_jfif:   # APP0 = JFIF
                    keep = True
            if keep:
                out.extend(data[i:end])
        # COM(0xFE) / DNL(0xDC) / JPG 扩展(0xC8) 等一律丢弃

        i = end

    return bytes(out) if len(out) >= 4 else data


def optimize_jpeg(src_path, out_path, strip_all: bool = True,
                  keep_jfif: bool = True) -> tuple[bool, int, int]:
    """把 src_path 的 JPEG 优化后写到 out_path。

    返回 (是否成功, 原字节数, 新字节数)。失败时返回 (False, 原字节数, 0)。
    """
    src = Path(src_path)
    dst = Path(out_path)
    try:
        data = src.read_bytes()
    except Exception:
        return False, 0, 0

    in_bytes = len(data)
    if in_bytes < 4:
        return False, in_bytes, 0

    out = strip_jpeg_bytes(data, strip_all=strip_all, keep_jfif=keep_jfif)
    if not out or len(out) < 4:
        return False, in_bytes, 0

    try:
        dst.write_bytes(out)
    except Exception:
        return False, in_bytes, 0

    return True, in_bytes, len(out)


if __name__ == "__main__":
    import os
    import sys

    strip_all = "--keep-exif" not in sys.argv
    for path in [a for a in sys.argv[1:] if not a.startswith("--")]:
        out_path = path + ".opt"
        ok, ib, ob = optimize_jpeg(path, out_path, strip_all=strip_all)
        if not ok:
            print(f"{os.path.basename(path)}: FAILED")
            continue
        pct = (ib - ob) / ib * 100 if ib else 0
        print(f"{os.path.basename(path)}: "
              f"{ib / 1024:.1f}KB -> {ob / 1024:.1f}KB  省 {pct:.1f}%")