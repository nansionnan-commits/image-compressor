# 图片一键压缩 v6

**直接拖图片/文件夹进窗口就能压缩。** 真 OS 拖拽，不是应用内的伪拖。

- 🎯 **无损压缩** / 💎 **极致保真** — 像素**数学零差异**（用 `ImageChops.difference(...).getbbox() is None` 验过）
- ⚡ **推荐压缩** — q=85 重编码，业界甜点，肉眼难辨
- 💾 **压最小** — q=80，省最多
- 🛒 **亚马逊主图** — 2000px JPG，符合 Amazon 主图要求

**默认是 ⚡ 推荐压缩**。纯 Python + Pillow，**不依赖 jpegoptim，不联网**，所有计算都在你这台电脑上跑。

---

## 三种打开方式

### 方式一：双击桌面快捷方式（推荐）

桌面上会有一个 **「图片一键压缩」** 图标，双击就开。**首次双击后请用 Windows 资源管理器拖一张图进窗口验证拖图能用**（下面有验证步骤）。

### 方式二：双击 `.exe`

`dist/ImageCompressor.exe`，约 18.5 MB，**单文件**，不需要装 Python。

### 方式三：从源码启动

需要 Python 3.11+（推荐 3.14，已实测）+ Pillow 12.x + tkinterdnd2 0.6.x：

```powershell
C:\Python314\python.exe compress_images_gui.py
```

如果 `tkinterdnd2` 没装，仍可启动，但只能用「选文件」按钮加图、不能用拖拽。

---

## 拖图怎么用

✅ = 测试通过 · ❌ = 不支持

| 拖什么 | 结果 |
|---|---|
| 拖一张图（中文名 / 带空格）| ✅ 加进队列 |
| 拖多张图 | ✅ 全加进队列 |
| 拖文件夹 | ✅ 递归扫里面的所有支持格式图 |
| 拖不支持的格式（`.gif`、`.exe` 等）| ✅ 自动忽略 |
| 拖混合包（支持 + 不支持）| ✅ 只收支持格式 |
| 重复拖同一文件/文件夹 | ✅ 自动去重 |
| 空的、垃圾的数据 | ✅ 不崩，忽略 |

**真实拖图验证步骤**：① 双击 exe ② 打开 Windows 资源管理器 ③ 找一张 `.jpg` ④ 用鼠标拖到 ImageCompressor 窗口里 ⑤ 看到文件出现在「待压缩文件」列表 ⑥ 点蓝色「▶ 开始压缩」→ 看「处理日志」滚动输出 ⑦ 完成看 `dist\compressed\<预设名>\` 下产出。

如果拖不动，最常见原因：① 拖到了标题栏而不是内容区（要落到 Listbox 或下面的整个空白区）② exe 被杀毒拦截（关掉 Windows Defender 的「受控文件夹访问」再试）。

---

## 5 个预设

| 预设 | 原理 | JPG 省多少 | 画质 |
|---|---|---|---|
| 🎯 无损压缩 | 剥掉 EXIF，像素一个 bit 不动 | 5~20% | **零损失** |
| 💎 极致保真 | 同上，但保留 EXIF 拍摄信息 | 少一点 | **零损失** |
| ⚡ 推荐压缩 | q=85 重编码（业界甜点） | ~25% | 肉眼难辨 |
| 💾 压最小 | q=80 重编码 | 最多 | 细看能看 |
| 🛒 亚马逊主图 | 转 JPG + 长边 2000px + q=85 | 很多 | 好，且符合 Amazon 主图要求 |

**两个保命设计**：

1. **压完反而更大就自动保留原图**
   任何情况下压完 ≥ 原图的 95%，直接丢弃结果保留原图。

2. **小于 50KB 的图直接跳过**
   这种图不值得压。

---

## 无损是怎么做到的

`jpegoptim` 靠反复试参数来优化量化表，耗时长还依赖外部二进制。

本项目换了个思路：JPEG 文件里有一段一段的数据块，其中

- `APP0~APP15` = EXIF 拍摄参数、相机型号、**内嵌缩略图**
- `COM` = 注释

手机拍的照片，光这些就占 40KB+，但它们**根本不参与画面解码**。

`_jpeg_strip.py` 遍历所有段，把 APP/COM 丢掉，量化表、哈夫曼表、熵编码数据原样保留 → **像素完全一致，字节数下降**。

### 实测验证（v6 跑过的真实数据）

| 文件 | 省多少 | 验证 |
|---|---|---|
| 4 张不同尺寸图 | 剥完基本不省（已优化过）| 跳过保留原图 |
| 1 张故意写 6KB EXIF 垃圾的图 | **省 9%** | ✅ 像素完全一致（差分图全 0） |
| 强制写出 4 张图 × 2 个无损预设 | 像素完全一致 8/8 ✅ | 0 差异 |
| 3 个有损预设 × 3 张图 | 省 34.8%–62.1% | 确实变小 |

判定像素真零差异只用 `ImageChops.difference(a, b).getbbox() is None`。**不要用 Pillow 的 `Image.__eq__`，它不是按内容比较的，会误判**。

---

## 输出位置

默认输出到 `dist\compressed\<预设名>\` 下（与 exe 同目录）。

修改方式：在 GUI 里改「输出」框，点「修改」选新位置。**程序不会覆盖原图**——产出是新增的 `_compressed` 后缀版本，除非你选了与原图不同的输出目录。

---

## 支持格式

`.jpg` `.jpeg` `.png` `.bmp` `.webp` `.tif` `.tiff`

默认**保持原格式**（jpg→jpg，png→png），不强转 webp。

---

## 运行环境

| 项 | 要求 |
|---|---|
| OS | Win 10 / 11 64 位 |
| 用 `.exe` | 不需要装任何东西 |
| 从源码 | Python 3.11+ + `pip install pillow tkinterdnd2`（3.14 上 `--collect-all tkinterdnd2` 已验证 onefile 打包 OK）|
| Tkinter | Python 自带 |

实测过的版本组合：

| 软件 | 版本 |
|---|---|
| Python | 3.14.5 |
| tkinter | 8.6 |
| tkinterdnd2 | 0.6.4（带 tkdnd 2.10.3）|
| Pillow | 12.3.0 |
| PyInstaller | 6.22.3 |

---

## 从源码重新打包成 `.exe`

```powershell
# 一次性
C:\Python314\python.exe -m pip install --upgrade pyinstaller pillow tkinterdnd2

# 打包 (在项目根目录)
C:\Python314\python.exe -m PyInstaller --onefile --noconsole ^
  --name ImageCompressor ^
  --collect-all tkinterdnd2 ^
  --collect-submodules tkinterdnd2 ^
  compress_images_gui.py

# 产物: dist\ImageCompressor.exe
```

`--collect-all tkinterdnd2` 是关键，不然 onefile 模式下 tkinterdnd2 的 tkdnd tcl/dll 找不到。

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `compress_images_gui.py` | **v6 入口**（Tkinter + tkinterdnd2 OS 拖拽，推荐）|
| `_core.py` | 压缩引擎（GUI / CLI 共用）|
| `_jpeg_strip.py` | JPEG 无损优化器（纯 Python，替代 jpegoptim）|
| `compress_images.py` | 命令行版（拖图到 `compress_images.py` 上）|
| `dist/ImageCompressor.exe` | 打包好的单文件可执行（约 18.5 MB）|
| `dist\compressed\` | 压缩产出（默认在 exe 同目录）|

---

## 隐私

所有图片处理都在本机完成，不上传任何服务器，不联网。`_MEIPASS` 里所有 tkdnd 的 tcl 都在本地解压，不下载任何东西。

---

## 历史与回退

### v6 — Tkinter + tkinterdnd2 真 OS 拖拽（2026-10）

界面仍是 Tkinter（v4 的成熟形态），但**首次加入 tkinterdnd2** 接入了真 OS 拖拽：

- 之前 Tkinter 版（v4）只能用「选文件」按钮，不能从资源管理器拖
- 现在 Tkinter + tkinterdnd2 + `ImageChops.difference` 像素零损失校验 = 这次推荐的最稳形态
- 5 个预设、4 段列表（队列 / 预览 / 日志 / 状态栏）、自定义参数面板、可调输出目录
- 5 个预设按钮：**全部完整不截断**（默认 1000×880，最小 920×720）
- 右侧预览面板 wraplength=250/260，文字不会被截
- `_on_drop` 主路径用 `tk.splitlist` 解析 tkdnd 真实格式（带空格自动加花括号），加正则 + 整串路径兜底，8 种用例都不崩
- PyInstaller 6.22.3 onefile 打包 18.5 MB

### v5 — 已被回退

尝试过 Flet Material 3：UI 美、但 `DragTarget` 接不到 OS 资源管理器。每次首次启动还要下载 40 MB Flet 客户端。对「真 OS 拖拽」这条核心需求没什么用，回退到 Tkinter + tkinterdnd2 这条更稳的路。

### v4 之前

v4 = Tkinter 旧版基线（无法拖图）。v3 之前是命令行版 + 拖 BAT。这条历史只在 git log 里，不影响现在的使用。

---

## License

MIT
