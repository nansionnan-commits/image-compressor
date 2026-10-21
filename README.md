<div align="center">

# 图瘦身 · PicShrink

**把图片压小，像素不丢，操作只靠拖。**

[下载 Windows 单文件版 (.exe)](../../releases/latest) · [看源码](../../) · [English below](#-english)

</div>

---

## 这是什么

图瘦身 (PicShrink) 是一个**完全跑在你本机**的图片压缩工具。打开它、把图片（一张、几张、或整个文件夹）从桌面**拖进窗口**，选个预设，按一下就开始。**全程不上传任何服务器，不联网**。

适合：

- 亚马逊 / TikTok Shop 主图要压在 ≤ 200KB / ≤ 120KB
- 手机拍的大体积 JPG 想分享，又不想上传到云端
- 简历 / 公众号 / 邮件附件需要小一点的图
- 任何不想装 Python 又要把图片压小的场景

---

## 30 秒上手

```text
1. 下载 releases 里最新的「图瘦身-v8-portable.zip」
2. 解压到任意文件夹
3. 双击里面的「图瘦身.exe」
4. 用 Windows 资源管理器把图片拖进窗口
5. 点蓝色「▶ 开始压缩」
6. 去「输出」框指向的目录收成品
```

不需要装 Python。只需要 Win 10 / 11 64 位。

> 首次双击 Windows 可能弹「Windows 已保护你的电脑」（SmartScreen），点 **更多信息 → 仍要运行** 即可。我们的 exe 没做代码签名，这是已知限制，不是 bug。

---

## 7 个预设

双行排布按钮，一行点不全也会自动换行不会被截：

| 预设 | 干啥 | JPG 省多少 | 画质 |
|---|---|---|---|
| 🎯 **无损压缩** | 剥 EXIF，**像素零差异** | 5–20% | **数学零损失** |
| 💎 **极致保真** | 同上，但保留 EXIF 拍摄信息 | 少一点 | **数学零损失** |
| ⚡ **推荐压缩** | q=85 重编码，业界甜点 | ~25% | 肉眼难辨 |
| 💾 **压最小** | q=80 重编码 | 最多 | 细看能看出 |
| 🛒 **亚马逊主图** | 转 JPG + 长边 2000px + q=85 | 很多 | 好，符合 Amazon 主图要求 |
| 📦 **主图 ≤ 200KB** | 长边 1280 + 自动二分搜索质量 | 自动达标 | 肉眼难辨 |
| 📦 **主图 ≤ 120KB** | 长边 1100 + 自动二分搜索质量 | 自动达标 | 肉眼难辨 |

**两个目标体积预设的原理**：先把图等比缩放到长边限制，然后在质量区间 [18, 92] 里**二分搜索**——找到刚好不超过目标字节数的最高质量。降质量比硬降像素能保住更多细节。降到底仍不达标（极少见，比如要求 ≤ 5KB）会写最低质量 (q=18) 的结果，并在日志里标 **「未达标」**，绝不静默失败。

> 高级用户可以在右下的「自定义参数」面板自己填「目标体积 (KB)」，> 0 即自动切到目标模式。

---

## 三个保命设计

1. **压完反而更大就保留原图**
   除无损预设外，任何情况压完 ≥ 原图 95% 都直接丢弃结果、留原图，避免越压越胖。
2. **小图 (< 50KB) 直接跳过**
   省下来的字节数不值得付出复制一份的开销。
3. **无损预设的 1KB 绝对下限**
   即便省不到 95%，只要净省 ≥ 1KB 就认。避免为省几十字节去复制一份几 MB 的文件。

---

## 拖图怎么用

拖动来源可以是桌面 / 资源管理器 / 任意文件对话框，**真 OS 级拖拽**（tkdnd 2.10.3），不是程序内部的伪拖：

| 拖什么 | 结果 |
|---|---|
| 一张图（中文名 / 带空格）| ✅ 加进队列 |
| 多张图 | ✅ 全加进队列 |
| 一个文件夹 | ✅ 递归扫里面所有支持的图 |
| 不支持的格式（`.gif` / `.exe` 等）| ✅ 自动忽略 |
| 混合包（支持 + 不支持）| ✅ 只收支持格式 |
| 重复拖同一文件/文件夹 | ✅ 自动去重 |
| 空数据 / 垃圾数据 | ✅ 不崩，忽略 |

**支持格式**：`jpg` `jpeg` `png` `bmp` `webp` `tif` `tiff`。默认保持原格式（jpg→jpg，png→png），不强转 webp。

---

## 输出位置

默认输出到与 exe 同目录下的 `compressed\<预设名>\` 里。重复运行会原子覆盖旧输出，**永远不会覆盖原图**：撞路径时自动加 `_compressed` / `_compressed2` 后缀。

修改方法：在 GUI 里改「输出」框，点「修改」选新位置。

---

## 无损是怎么做到的

`jpegoptim` 靠反复试参数来调量化表，耗时长还得装外部二进制。

图瘦身换了思路：JPEG 文件是一段一段的数据块，其中：

- `APP0 ~ APP15` = EXIF 拍摄参数、相机型号、内嵌缩略图
- `COM` = 注释

手机拍的照片，光这些就占 40KB+，但它们**根本不参与画面解码**。`_jpeg_strip.py` 遍历所有段，把 APP/COM 丢掉，量化表、哈夫曼表、熵编码数据原样保留 → 像素完全一致，字节数下降。

**真实零差异校验**只用 Pillow 的：

```python
ImageChops.difference(a, b).getbbox() is None
```

⚠️ **不要用 Pillow 的 `image_a == image_b`**——它不是按像素比较的，会误判。

---

## 隐私

- 所有处理都在本机完成，**不上传任何服务器**
- 不联网（启动后完全断网也能用）
- 不做任何遥测
- tkdnd 的 tcl 资源全在 PyInstaller `_MEIPASS` 内本地解压

---

## 运行环境

| 项 | 要求 |
|---|---|
| OS | Windows 10 / 11 64 位 |
| 用 `.exe` | 不需要装任何东西 |
| 从源码 | Python 3.11+（推荐 3.14），`pip install pillow tkinterdnd2` |

实测过的版本：

| 软件 | 版本 |
|---|---|
| Python | 3.14.5 |
| tkinter | 8.6 |
| tkinterdnd2 | 0.6.4（带 tkdnd 2.10.3）|
| Pillow | 12.3.0 |
| PyInstaller | 6.22.3 |

---

## 从源码构建

```powershell
# 一次性
C:\Python314\python.exe -m pip install --upgrade pyinstaller pillow tkinterdnd2

# 打包 (在项目根目录)
C:\Python314\python.exe -m PyInstaller --onefile --noconsole ^
  --name 图瘦身 ^
  --icon app.ico ^
  --add-data "app.ico;." ^
  --collect-all tkinterdnd2 ^
  --collect-submodules tkinterdnd2 ^
  compress_images_gui.py

# 产物: dist\图瘦身.exe
```

`--collect-all tkinterdnd2` 和 `--add-data "app.ico;."` 都是必须的：前者保证 tkdnd 的 tcl/dll 进 onefile，后者让运行时读得到品牌图标。

---

## 文件清单

| 文件 | 作用 |
|---|---|
| `compress_images_gui.py` | **图瘦身 (PicShrink) v8 入口** — Tkinter + tkinterdnd2 OS 拖拽，自带压缩引擎、`_safe_out_path()`、目标体积模式二分搜索、应用图标 |
| `app.ico` | 品牌图标（256/128/64/48/32/16 多尺寸），打包时嵌入 exe |
| `app.png` | 256x256 品牌图标（PNG 版本） |
| `compress_images.py` | 命令行等价入口（同款 7 预设 + 目标体积模式）|
| `_jpeg_strip.py` | JPEG 无损优化器（纯 Python，替代 jpegoptim）|
| `dist/图瘦身.exe` | 打包好的单文件可执行（约 19.5 MB）|
| `_shots/` | 截图存档 |

---

## 历史 & 版本

### v8 — 品牌「图瘦身」+ 蓝青图标（2026-10）

- **新中文名「图瘦身」/ 英文 PicShrink / exe 改名 `图瘦身.exe`**
- 新增蓝青渐变品牌图标（圆角 + 图片卡 + 瘦身箭头），嵌入 exe + 应用窗口 + 任务栏
- 顶部 docstring 从过期 v3 描述改为真实 v8 描述；移除历史残留 `_core.py`
- 桌面快捷方式更新为 `图瘦身.lnk`，统一指向新 exe
- v7 的压缩引擎与 7 预设行为**完全不变**，已是验证过 27/27 通过的稳定底盘

### v7 — 目标体积预设 + 路径自撞修复（2026-10）

- 新增 📦 主图≤200KB / 📦 主图≤120KB 两个预设，按亚马逊主图常用目标量自动二分搜索质量
- 修路径自撞：输出撞原图自动加 `_compressed` 后缀，不再误报「目标已存在」
- 重复运行不再「全部跳过」，上一轮的压缩输出会被原子覆盖
- 无损预设不再被 95% 智能回退门槛卡住，但设 1KB 绝对下限

### v6 — Tkinter + tkinterdnd2 真 OS 拖拽（2026-10）

回到 Tkinter + tkinterdnd2 这条稳路，加入真 OS 文件拖拽。

### v5 — 已回退

试过 Flet Material 3：UI 是漂亮，但 `DragTarget` 接不到 OS 资源管理器，且首次启动还要下载 40 MB 客户端。回退。

### v4 之前

v4 = Tkinter 旧版基线（不能拖图）。v3 之前是命令行版 + 拖 BAT。完整历史在 git log。

---

## 已知小坑（不影响功能）

- **没做代码签名** → 第一次双击 Windows SmartScreen 会拦一下，点「更多信息 → 仍要运行」即可。
- **中文文件名 exe** 在纯英文 Windows 上极少数情况可能展示成乱码备选名（不影响功能）。

---

## License

MIT

---

## English

PicShrink (图瘦身 / "slim-down pictures") is a fully-local image compressor for Windows. Drop pictures into the window, pick a preset, click start. Seven presets including two target-size presets (≤200KB / ≤120KB with auto binary-search quality). Two lossless presets produce mathematically pixel-identical output (verified via `ImageChops.difference(a,b).getbbox() is None`). No upload, no telemetry, no network after launch. Single-file `.exe` (~19MB), no Python install required. Win 10/11 64-bit. MIT.
