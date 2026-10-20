# 图片一键压缩

拖图进去，字节数就变小。画质肉眼难辨，JPG 无损模式能做到**数学上零损失**。

纯 Python + Pillow，**不需要装 jpegoptim**，不需要联网，所有计算都在你自己的电脑上跑。

---

## 快速开始

### 方式一：双击桌面快捷方式（推荐，v5 新增）

桌面上会有一个 **「图片一键压缩」** 图标（首次启动点 AppBar 右上角的「🔗」图标即可创建），双击就开。

### 方式二：双击 `.exe`（v5 新增）

`dist/ImageCompressor.exe`，21.7 MB，单文件，不需要装 Python 也能跑（首次会下载 Flet 客户端到 `%USERPROFILE%\.flet\client\`，约 40 MB，之后就缓存）。

### 方式三：从源码启动

```powershell
C:\Python311\pythonw.exe compress_images_flet.py
```

### Tkinter 旧版（v4 兼容入口，保留作为后备）

```powershell
C:\Python311\python.exe compress_images_gui.py
```

或双击 `图片一键压缩.bat`。

---

## 5 个预设

| 预设 | 原理 | JPG 省多少 | 画质 |
|---|---|---|---|
| 🎯 无损压缩 | 剥掉 EXIF 拍摄参数，像素一个 bit 不动 | 5~20% | **零损失** |
| 💎 极致保真 | 同上，但保留 EXIF 拍摄信息 | 少一点 | **零损失** |
| ⚡ 推荐压缩 | q=85 重编码（业界甜点） | ~25% | 肉眼难辨 |
| 💾 压最小 | q=80 重编码 | 最多 | 细看能看 |
| 🛒 亚马逊主图 | 转 JPG + 长边 2000px + q=85 | 很多 | 好，且符合 Amazon 主图要求 |

**默认是 ⚡ 推荐压缩。**

---

## 两个保命设计

这两条是踩过坑才加的：

1. **压完反而更大就自动保留原图**
   JPEG 本身优化程度不一，有些图压完会变大。任何情况下压完 ≥ 原图的 95%，直接丢弃结果、保留原图。绝不给你变大的文件。

2. **小于 50KB 的图直接跳过**
   这种图不值得压，硬压还会掉画质。

---

## 无损是怎么做到的

`jpegoptim` 靠反复试参数来优化量化表，耗时长还依赖外部二进制。

本项目换了个思路：JPEG 文件里有一段一段的数据块，其中

- `APP0~APP15` = EXIF 拍摄参数、相机型号、**内嵌缩略图**
- `COM` = 注释

手机拍的照片，光这些就占 40KB+，但它们**根本不参与画面解码**。

`_jpeg_strip.py` 遍历所有段，把 APP/COM 丢掉，量化表、哈夫曼表、熵编码数据原样保留 → **像素完全一致，字节数下降**。

### 实测验证

```
原始    : 2899.0 KB   带 EXIF   3000x2000
剥完    : 2854.9 KB   无 EXIF   3000x2000
省      : 1.5%（44KB 就是 EXIF）
像素最大差: 0          ← 数学无损
```

---

## 环境要求

- 从源码运行：Python 3.11（v5 锁版本，Flet 1.0.4 桌面客户端在该版本最稳）+ Pillow
- 用 `.exe`：什么都不用装，Win10/11 64 位即可
- Tkinter 是 Python 自带的，不用装

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `compress_images_flet.py` | **v5 入口**，Flet Material 3 桌面 GUI（推荐） |
| `compress_images_gui.py` | v4 Tkinter 旧版（保留作为后备） |
| `_core.py` | 压缩引擎（GUI / CLI 共用） |
| `_jpeg_strip.py` | JPEG 无损优化器（纯 Python，替代 jpegoptim） |
| `compress_images.py` | 命令行版（拖图到 `拖我压缩.bat` 上） |
| `dist/ImageCompressor.exe` | v5 打包好的单文件可执行（21.7 MB） |
| `图片一键压缩.bat` | 启动 Tkinter 旧版 |
| `拖我压缩.bat` | 拖图 = 压 |

---

## 支持格式

`.jpg` `.jpeg` `.png` `.bmp` `.webp` `.tif` `.tiff`

默认**保持原格式**（jpg→jpg，png→png），不强转 webp——小图转 webp 反而会变大。

---

## 隐私

所有图片处理都在本机完成，不上传任何服务器，不联网。v5 唯一一次网络请求是首次启动下载 Flet 桌面客户端（缓存到本地，之后不再访问）。

---

## 更新日志（CHANGELOG）

### v5 — Flet Material 3 桌面 GUI（2026-10-20）

**界面重做**

- 从 Tkinter 迁移到 Flet 1.0.4 Material 3 桌面客户端
- 5 段预设选择器、GridView 缩略图、实时预览、设置面板（默认输出目录 / 默认预设 / 窗口尺寸 持久化到 `config.json`）
- AppBar 右上角「🔗」一键创建桌面快捷方式，参数全部正确（指向 Python 3.11，不踩裸 `python` 调到 3.14 的坑）

**打包**

- PyInstaller 6.22.3 单文件 `.exe`（21.7 MB，路径 `dist/ImageCompressor.exe`）
- 首次启动会下载 Flet 桌面客户端到 `%USERPROFILE%\.flet\client\flet-desktop-full-1.0.4\`（约 40 MB），之后本地缓存

**压缩引擎保持兼容**

- 抽出 `_core.py` 共用压缩逻辑，GUI / CLI 同一份代码
- `🎯 无损压缩` / `💎 极致保真` 仍走 `_jpeg_strip.py`，数学零损失
- 智能回退（压完 ≥ 95% 直接保留原图）和 50KB 以下跳过两条保命设计保留

**兼容入口**

- Tkinter 旧版（v4）未删除，仍可双击 `图片一键压缩.bat` 启动，作为退路

### v4 — Tkinter 旧版基线

- Tkinter GUI，5 预设，无 EXIF 无损保留
- `compress_images_gui.py` + `图片一键压缩.bat`
- 这条 commit 是 v5 重写前的稳定基线

### v3 及更早

- 命令行版 `compress_images.py`、拖图到 `拖我压缩.bat` 上即可
- 最初版的 JPEG 无损剥 EXIF 实现

---

## License

MIT
