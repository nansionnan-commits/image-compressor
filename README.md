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

**方式 A：装到电脑上（推荐，有开始菜单、有卸载器）**

```text
1. 下载 releases 里最新的「PicShrink-Setup-v10.exe」
2. 双击它，一路点「下一步」到「安装」
3. 完事儿。桌面和开始菜单都有「图瘦身」
4. 选中图片右键 → 「用图瘦身处理」（可多选）
5. 想卸：设置 → 应用 → 找到「图瘦身 (PicShrink) v10」→ 卸载
```

**方式 B：不装，解压即用（绿色便携版）**

```text
1. 下载 releases 里最新的「PicShrink-v9-portable.zip」
2. 解压到任意文件夹
3. 直接双击「PicShrink.exe」
4. 想加右键菜单 → 双击「install.bat」
```

两种方式都**不需要装 Python**，只需要 Win 10 / 11 64 位。

> 首次双击 Windows 可能弹「Windows 已保护你的电脑」（SmartScreen），点 **更多信息 → 仍要运行** 即可。我们的 exe 没做代码签名，这是已知限制，不是 bug。

---

## v10：装一次，右键就能压

安装器（`PicShrink-Setup-v10.exe`）是标准 Windows 向导式安装包：

| 项 | 值 |
|---|---|
| 安装位置 | `%LOCALAPPDATA%\图瘦身\`（不需要管理员权限）|
| 开始菜单 | 开始菜单里有一组「图瘦身」：主程序 + 卸载项 |
| 桌面 | 桌面快捷方式「图瘦身」 |
| 卸载 | 设置 → 应用 →「图瘦身 (PicShrink) v10」→ 卸载，**能点** |
| 注册表 | 只写 `HKCU`，不影响别的账号 |

装完之后，图片压缩这件事**根本不用打开主界面**：

| 你做的事 | 结果 |
|---|---|
| 右键一张图 → 「用图瘦身处理」| 直接压这一张 |
| **选中多张图** → 右键 →「用图瘦身处理」| **一次全压完**，一张一个窗口都不会多弹 |
| 右键一个文件夹 →「用图瘦身压缩这个文件夹」| 递归扫整个文件夹，一次压完 |
| 右键任意文件 → 发送到 →「图瘦身」| 同上，SendTo 的经典用法 |

快捷入口走的是**和界面完全相同的 7 预设引擎**，不是另一套简化逻辑。你在界面里手动选过预设之后，右键入口会记住它（存 `%LOCALAPPDATA%\图瘦身\quick.json`）；没手动选过时默认用「⚡ 推荐压缩」。

压缩过程会弹一个进度窗，压完弹结果窗（成功 / 跳过 / 失败各几张、省了多少、输出在哪），结果窗上有「打开输出目录」和「全部重压一遍」，8 秒不操作会自动关掉。

**快捷入口的输出位置**是 `%USERPROFILE%\picshrink_out\`，按源文件夹分层：

```text
%USERPROFILE%\picshrink_out\实拍图\01.jpg
%USERPROFILE%\picshrink_out\旅行照片\02.jpg
```

所以**同名图片放在不同文件夹里不会互相覆盖**——它们各自落到自己文件夹名下面。**原图在任何路径下都不会被改动或覆盖。**

### 安装 / 卸载

| 方式 | 文件 | 干什么 |
|---|---|---|
| **推荐** | `PicShrink-Setup-v10.exe` | 向导式安装：放文件 + 桌面/开始菜单图标 + 登记到「应用」列表可点的卸载器；顺带调用下面的 `--install` 把右键菜单、SendTo 一起配好 |
| 便携 | `install.bat` | 装右键菜单（图片 / 文件夹）、SendTo、桌面快捷方式 |
| 便携 | `uninstall.bat` | 卸掉上面这些；**已压好的图片一律保留**，还会问你要不要删安装目录 |

安装只写 `HKCU`，不碰系统级注册表，不需要管理员权限，只对当前这个 Windows 账号生效。装完在资源管理器里按一下 `F5` 右键菜单就出现。

走安装器卸载时，程序会先跑一次 `--uninstall --quiet` 清掉右键菜单 / SendTo / 桌面快捷方式（但**保留安装目录**），再由安装器自己删文件——两边分工不重叠，**你压好的图片一张都不会少**。

> `install.bat` / `uninstall.bat` 内部是**纯 ASCII**，一个中文都没有。所有中文提示都由 exe 自己弹窗。这样做是因为 `.bat` 会被 cmd 按控制台码页解析，中文脚本在部分机器上会被切乱码导致连 exe 都找不到。
>
> Inno Setup 安装器不受这条限制——它是 Unicode 的，所以安装向导、开始菜单项、卸载项全都可以正常显示中文。

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

# 打包 (在项目根目录, 用仓库自带的 spec)
C:\Python314\python.exe -m PyInstaller 图瘦身.spec

# 产物: dist\PicShrink.exe

# 生成并编译安装器 (v10)
C:\Python314\python.exe _mk_iss.py
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" setup.iss

# 产物: _setup_out\PicShrink-Setup-v10.exe
```

`图瘦身.spec` 里 `collect_all tkinterdnd2` 和 `datas = [('app.ico', '.')]` 都是必须的：前者保证 tkdnd 的 tcl/dll 进 onefile，后者让运行时读得到品牌图标、也让安装器能把图标取出来给右键菜单用。

exe 文件名定成 ASCII 的 `PicShrink` 而不是中文，就是为了让 `install.bat` / `uninstall.bat` 能稳定引用它（见上面「安装 / 卸载」那条）。中文品牌留在界面、快捷方式和右键菜单显示名里。

---

## 文件清单

| 文件 | 作用 |
|---|---|
| `compress_images_gui.py` | **图瘦身 (PicShrink) v10 入口** — Tkinter + tkinterdnd2 OS 拖拽，自带压缩引擎、`_safe_out_path()`、目标体积模式二分搜索、应用图标、v9 快捷入口与安装/卸载 |
| `app.ico` | 品牌图标（256/128/64/48/32/16 多尺寸），打包时嵌入 exe |
| `图瘦身.spec` | PyInstaller 打包配置（`--collect-all tkinterdnd2` + 嵌入 app.ico）|
| `setup.iss` | Inno Setup 6 安装器脚本（v10）— 向导式安装 + 开始菜单 + 卸载器登记 |
| `_mk_iss.py` | 生成 `setup.iss` 的脚本（带 UTF-8 BOM）|
| `install.bat` / `uninstall.bat` | v9 纯 ASCII 安装 / 卸载壳，转调 `PicShrink.exe --install` / `--uninstall` |
| `compress_images.py` | 命令行等价入口（同款 7 预设 + 目标体积模式）|
| `_jpeg_strip.py` | JPEG 无损优化器（纯 Python，替代 jpegoptim）|
| `dist/PicShrink.exe` | 打包好的单文件可执行（约 19.6 MB）|
| `_shots/` | 截图存档 |

---

## 历史 & 版本

### v10 — 标准安装器（2026-10）

- 新增 **Inno Setup 6 向导式安装包** `PicShrink-Setup-v10.exe`（约 21.2 MB）：下一步 / 安装 / 完成三步走，压缩包体积几乎不变（LZMA2 max + solid）
- **开始菜单**里出现「图瘦身」组（主程序 + 卸载项），**桌面**快捷方式由安装器创建
- **Windows「应用」（Add/Remove Programs）里可点击的真卸载器** — 登记名为「图瘦身 (PicShrink) v10」，不再需要用户自己翻目录找 `uninstall.bat`
- 免管理员安装（`PrivilegesRequired=lowest`），与 v9 只写 `HKCU` 的设计保持一致
- 安装目录与 v9 的 `_v9_install_dir()` **完全一致**（`%LOCALAPPDATA%\图瘦身`），不会出现两份安装
- 桌面快捷方式用 `{userdesktop}` 而非 `{autodesktop}`——免管理员模式下后者指向公共桌面，普通用户装完看不到图标
- 卸载分工不重叠：`--uninstall --quiet` 只清 HKCU / SendTo / 桌面快捷方式并**保留安装目录**，文件与快捷方式由 Inno 自己删
- 压缩引擎、7 预设、快捷入口行为**一行未改**
- 回归：安装器端到端 21/21，v9 五套全绿（源码 28/28、打包 exe 15/15、便携安装器 36/36、e2e 26/26、窗口验证 PASS）

### v9 — 右键快捷入口 + 便携安装器（2026-10）

- **资源管理器右键菜单**：图片右键（`MultiSelectModel=Single`，**多选一次压完**）、文件夹右键（自动递归）
- **SendTo 条目** + **桌面快捷方式**，桌面路径走 Windows Known Folder API，**尊重用户把桌面重定向到别的盘**
- 新增 `install.bat` / `uninstall.bat` + `--install` / `--uninstall`；只写 `HKCU`，不需要管理员
- exe 文件名改 ASCII `PicShrink.exe`，中文品牌留在界面 / 快捷方式 / 右键显示名
- 快捷入口改为**复用界面的 7 预设引擎**（此前走的是旧 CLI 的 `format=auto` / WebP 默认 / `max-side=2560` 那一套，已废弃）
- 快捷入口默认预设跟随你在界面里最后一次手动选择（`%LOCALAPPDATA%\图瘦身\quick.json`），没选过则用「⚡ 推荐压缩」
- windowed exe 自绘进度窗 + 结果窗，错误同时落到 `%TEMP%\picshrink_v9.log`
- v7/v8 的压缩引擎与 7 预设行为**完全不变**
- 回归：源码 28/28、打包 exe 15/15、安装器端到端 36/36

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
- **全局自定义快捷键暂未提供**。v10 走的是资源管理器右键 / 文件夹右键 / SendTo / 桌面与开始菜单图标这五条路，都是官方支持的机制。做成「任意界面按一个全局热键就压缩当前选中的图」需要常驻进程 + 读 Explorer 选中项 + 托盘 + 开机自启，属于 v10.1 的范围。
- **`install.bat` 必须是纯 ASCII**。这是踩过坑之后定的：cmd 按活动控制台码页解析 `.bat`，中文脚本在码页不匹配时会被切乱码。中文提示一律由 exe 弹窗。

---

## License

MIT — 完整文本见 [LICENSE](LICENSE)。

---

## English

PicShrink (图瘦身 / "slim-down pictures") is a fully-local image compressor for Windows. v9 adds Explorer integration: right-click any picture (or multi-select many) → compress; right-click a folder → compress recursively; SendTo entry and desktop shortcut. The quick entry reuses the exact same seven-preset engine as the GUI. Seven presets including two target-size presets (≤200KB / ≤120KB with auto binary-search quality). Two lossless presets produce mathematically pixel-identical output (verified via `ImageChops.difference(a,b).getbbox() is None`). No upload, no telemetry, no network after launch. Single-file `.exe` (~19.6MB), no Python install required. Win 10/11 64-bit. MIT.
