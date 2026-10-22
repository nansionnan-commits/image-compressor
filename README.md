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
1. 下载 releases 里最新的「PicShrink-Setup-v11.exe」
2. 双击它，一路点「下一步」到「安装」
3. 完事儿。桌面和开始菜单都有「图瘦身」
4. 选中图片右键 → 「用图瘦身处理」（可多选）
5. 想改默认行为 → 打开图瘦身，点「⚙ 设置」
6. 想卸：设置 → 应用 → 找到「图瘦身 (PicShrink) v11」→ 卸载
```

**方式 B：不装，解压即用（绿色便携版）**

```text
1. 下载 releases 里最新的「PicShrink-v11-portable.zip」
2. 解压到任意文件夹
3. 直接双击「PicShrink.exe」
4. 想加右键菜单 → 双击「install.bat」
```

两种方式都**不需要装 Python**，只需要 Win 10 / 11 64 位。

> 首次双击 Windows 可能弹「Windows 已保护你的电脑」（SmartScreen），点 **更多信息 → 仍要运行** 即可。我们的 exe 没做代码签名，这是已知限制，不是 bug。

---

## v11：设置会被记住，压缩结果能还原

### 设置会被记住

点主界面右上角 **⚙ 设置**，可以改三样东西，**关掉再开、换台电脑重启都还在**（存在 `%LOCALAPPDATA%\图瘦身\settings.json`）：

| 设置项 | 可选值 | 默认 |
|---|---|---|
| 右键菜单默认用哪个预设 | 7 个预设任选 | ⚡ 推荐压缩 |
| 右键菜单默认输出什么格式 | 保持原格式 / JPG / PNG / WebP | **保持原格式** |
| 右键菜单默认导出到哪 | 三种模式，见下 | 原文件夹加后缀 |

改完之后，**右键菜单和 SendTo 全都跟着走**，不需要每次重新选。

> 「保持原格式」是按文件**真实内容**判断的，不是看扩展名。有些图后缀写着 `.png` 实际存的是 JPEG，按后缀处理会直接崩，v11 已经绕开了这个坑。

### 三种输出位置

| 模式 | 效果 | 适合 |
|---|---|---|
| **原文件夹导出**（默认）| `原文件夹\01_compressed.jpg` | 最安全，原图一定不动 |
| **统一导出到指定文件夹** | `指定文件夹\01.jpg`，同名自动加序号不覆盖 | 想统一归档 |
| **直接覆盖原图** | 就地替换，**覆盖前自动备份** | 已经备份过原片的场景 |

**「覆盖原图」是唯一会动原图的模式**，所以它带三道保险：

1. 必须先在设置里确认「我已知风险」，否则右键时弹窗问你，脚本调用直接拒绝退出
2. 每覆盖一张先复制一份到 `%LOCALAPPDATA%\图瘦身\备份\<时间戳>\`
3. 写一份 `_restore.json` 清单，记录每个原文件的完整路径

### 备份可以还原

主界面点 **↩︎ 备份/还原**，能看到所有历史批次（时间 + 压了几张 + 省了多少），选一个批次点还原即可。还原之前还会再存一次「还原前」的版本——**所以连误操作都能退回去**。

---

## v10：装一次，右键就能压

安装器（`PicShrink-Setup-v11.exe`）是标准 Windows 向导式安装包：

| 项 | 值 |
|---|---|
| 安装位置 | `%LOCALAPPDATA%\图瘦身\`（不需要管理员权限）|
| 开始菜单 | 开始菜单里有一组「图瘦身」：主程序 + 卸载项 |
| 桌面 | 桌面快捷方式「图瘦身」 |
| 卸载 | 设置 → 应用 →「图瘦身 (PicShrink) v11」→ 卸载，**能点** |
| 注册表 | 只写 `HKCU`，不影响别的账号 |

装完之后，图片压缩这件事**根本不用打开主界面**：

| 你做的事 | 结果 |
|---|---|
| 右键一张图 → 「用图瘦身处理」| 直接压这一张 |
| **选中多张图** → 右键 →「用图瘦身处理」| **一次全压完**，一张一个窗口都不会多弹 |
| 右键一个文件夹 →「用图瘦身压缩这个文件夹」| 递归扫整个文件夹，一次压完 |
| 右键任意文件 → 发送到 →「图瘦身」| 同上，SendTo 的经典用法 |

快捷入口走的是**和界面完全相同的 7 预设引擎**，不是另一套简化逻辑。

压缩过程会弹一个进度窗，压完弹结果窗（成功 / 跳过 / 失败各几张、省了多少、输出在哪），结果窗上有「打开输出目录」和「全部重压一遍」，8 秒不操作会自动关掉。

### 安装 / 卸载

| 方式 | 文件 | 干什么 |
|---|---|---|
| **推荐** | `PicShrink-Setup-v11.exe` | 向导式安装：放文件 + 桌面/开始菜单图标 + 登记到「应用」列表可点的卸载器；顺带调用下面的 `--install` 把右键菜单、SendTo 一起配好 |
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

**两个目标体积预设的原理**：先把图等比缩放到长边限制，然后在质量区间 [18, 92] 里**二分搜索**——找到刚好不超过目标字节数的最高质量。降质量比硬降像素能保住更多细节。

> 如果压到最低质量（q=18）**仍然大于原图**（这只在「目标体积 + PNG + 保持原格式」这种组合下会发生，因为对 PNG 降质量几乎没用），v11 会**直接跳过并保留原图**，绝不给你一个比原来更大的文件。日志里会写清楚原因。
>
> 高级用户可以在右下的「自定义参数」面板自己填「目标体积 (KB)」，> 0 即自动切到目标模式。

---

## 四个保命设计

1. **压完反而更大就保留原图**
   除无损预设外，任何情况压完 ≥ 原图 95% 都直接丢弃结果、留原图；目标体积模式下压到底还更大，**同样保留原图**。
2. **小图 (< 50KB) 直接跳过**
   省下来的字节数不值得付出复制一份的开销。
3. **无损预设的 1KB 绝对下限**
   即便省不到 95%，只要净省 ≥ 1KB 就认。避免为省几十字节去复制一份几 MB 的文件。
4. **任何会动原图的操作都先备份**
   覆盖原图前先存一份 + 写还原清单，界面里一键退回。

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

### 透明 PNG 也能压

带透明通道的 PNG 在 v10 一压就崩（`cannot write mode PA as PNG`）。v11 修好了：带透明的图**不做调色板量化**（量化会改颜色，商品图上是灾难），改走 RGBA + zlib 优化，实测未 optimize 的图能省 60%+。真压不小就原样保留。

---

## 输出位置

见上面「三种输出位置」。主界面拖拽压缩时用输出框下面那三个单选；右键 / SendTo 快捷入口用「⚙ 设置」里配好的默认值。

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

# 生成并编译安装器 (v11)
C:\Python314\python.exe _mk_iss.py
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" setup.iss

# 产物: _setup_out\PicShrink-Setup-v11.exe
```

> `--clean` 重新打包前先结束残留的 `PicShrink.exe`，否则 `dist\PicShrink.exe` 被占用会直接报 `WinError 5`。

`图瘦身.spec` 里 `collect_all tkinterdnd2` 和 `datas = [('app.ico', '.')]` 都是必须的：前者保证 tkdnd 的 tcl/dll 进 onefile，后者让运行时读得到品牌图标、也让安装器能把图标取出来给右键菜单用。

exe 文件名定成 ASCII 的 `PicShrink` 而不是中文，就是为了让 `install.bat` / `uninstall.bat` 能稳定引用它（见上面「安装 / 卸载」那条）。中文品牌留在界面、快捷方式和右键菜单显示名里。

---

## 文件清单

| 文件 | 作用 |
|---|---|
| `compress_images_gui.py` | **图瘦身 (PicShrink) v11 入口** — Tkinter + tkinterdnd2 OS 拖拽，自带压缩引擎、`_safe_out_path()`、目标体积模式二分搜索、应用图标、右键快捷入口与安装/卸载、设置持久化与备份还原 |
| `app.ico` | 品牌图标（256/128/64/48/32/16 多尺寸），打包时嵌入 exe |
| `图瘦身.spec` | PyInstaller 打包配置（`--collect-all tkinterdnd2` + 嵌入 app.ico）|
| `setup.iss` | Inno Setup 6 安装器脚本（v11）— 向导式安装 + 开始菜单 + 卸载器登记 |
| `_mk_iss.py` | 生成 `setup.iss` 的脚本（带 UTF-8 BOM）|
| `install.bat` / `uninstall.bat` | 纯 ASCII 安装 / 卸载壳，转调 `PicShrink.exe --install` / `--uninstall` |
| `compress_images.py` | 命令行等价入口（同款 7 预设 + 目标体积模式）|
| `_jpeg_strip.py` | JPEG 无损优化器（纯 Python，替代 jpegoptim）|
| `dist/PicShrink.exe` | 打包好的单文件可执行（约 19.6 MB）|
| `_shots/` | 截图存档 |

---

## 历史 & 版本

### v11 — 设置可自定义 + 备份可还原（2026-10）

**修的真 bug：**

- **透明 PNG 一压就崩**：`cannot write mode PA as PNG`。根因是量化后调 `putalpha()` 把 `P` 变成了 `PA`，而 Pillow 12.3.0 根本不接受 `PA` 存 PNG。v11 让带 alpha 的图一律不做量化，走 RGBA + zlib 优化
- **「保持原格式」只看扩展名**：后缀写 `.png` 实际存 JPEG 的图会走错编码路径直接崩。改成按文件真实内容格式判断，扩展名只做兜底
- **多选右键菜单不出现**：`MultiSelectModel=Single` 按微软文档只支持单选，选中数量对不上时 Explorer 直接不显示这个菜单项。改成 `Player` + 命令行 `"%*"`
- **目标体积模式「越压越大」**：「目标体积 + PNG + 保持原格式」这个组合下，降质量对 PNG 几乎无效，二分一路压到 q=18 仍然超标，最后给用户一个比原图更大的文件。改成走和别处一样的智能回退：没变小就原样保留并说明原因
- **固定目录模式下同名图互相覆盖**：不同来源的 `01.jpg` 会挤掉彼此。改成自动加序号，同一来源重复压仍幂等重写
- **安装器会装出两份 exe**：Inno Setup 默认用卸载项里记的 `InstallLocation` 覆盖 `DefaultDirName`。只要历史装到过别的盘（比如 `D:\图瘦身`），`{app}` 就和 `--install` 用的 `%LOCALAPPDATA%\图瘦身` 分家，磁盘上留两份 `PicShrink.exe`，而右键菜单只指向其中一份 —— 升级后菜单跑的仍是旧代码。加 `UsePreviousAppDir=no` 强制回到默认目录，exe 全程只有一份

**新能力：**

- **设置会被记住**（`%LOCALAPPDATA%\图瘦身\settings.json`）：右键菜单的默认预设 / 默认输出格式 / 默认输出位置三样都归你管，改一次长期有效
- **三种输出位置**：原文件夹加后缀（默认） / 统一导出到指定目录 / 直接覆盖原图
- **覆盖前强制确认 + 自动备份**：未确认时 GUI 弹框、脚本直接拒绝退出，绝不静默动原图
- **备份可查看可还原**：主界面「↩︎ 备份/还原」窗口列出所有历史批次，还原前还会再存一次「还原前」版本，让还原本身也可逆
- 设置文件从 `quick.json` 迁移到 `settings.json`（旧文件仍会自动读取），并逐字段校验，配置损坏自动退回默认值
- 保留 v8/v9/v10 的压缩引擎与 7 预设行为**一行未改**

**回归（全部实跑通过）：** 源码级 v7 27/27、预设级全绿、设置 53/53、右键设置 32/32、透明图 0 失败、打包 exe 35/35 + 15/15、安装器实测 36/36、安装器端到端 23/23、便携包端到端 26/26、窗口与右键注册表验证 PASS。

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

- **资源管理器右键菜单**：图片右键、文件夹右键（自动递归）
- **SendTo 条目** + **桌面快捷方式**，桌面路径走 Windows Known Folder API，**尊重用户把桌面重定向到别的盘**
- 新增 `install.bat` / `uninstall.bat` + `--install` / `--uninstall`；只写 `HKCU`，不需要管理员
- exe 文件名改 ASCII `PicShrink.exe`，中文品牌留在界面 / 快捷方式 / 右键显示名
- 快捷入口改为**复用界面的 7 预设引擎**（此前走的是旧 CLI 的 `format=auto` / WebP 默认 / `max-side=2560` 那一套，已废弃）
- windowed exe 自绘进度窗 + 结果窗，错误同时落到 `%TEMP%\picshrink_v11.log`
- v7/v8 的压缩引擎与 7 预设行为**完全不变**
- 回归：源码 28/28、打包 exe 15/15、安装器端到端 36/36
- ⚠️ 此版本右键菜单用的是 `MultiSelectModel=Single` + `%1`，**多选时菜单不显示**，已在 v11 修复

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
- **全局自定义快捷键暂未提供**。v11 走的是资源管理器右键 / 文件夹右键 / SendTo / 桌面与开始菜单图标这五条路，都是官方支持的机制。做成「任意界面按一个全局热键就压缩当前选中的图」需要常驻进程 + 读 Explorer 选中项 + 托盘 + 开机自启，属于 v11.1 的范围。
- **`install.bat` 必须是纯 ASCII**。这是踩过坑之后定的：cmd 按活动控制台码页解析 `.bat`，中文脚本在码页不匹配时会被切乱码。中文提示一律由 exe 弹窗。
- **目标体积 + PNG 常常压不动**。PNG 是无损格式，对它降质量本来就没意义。真要小就得转 JPG/WebP——在设置里把输出格式改成 WebP 就有了。

---

## License

MIT — 完整文本见 [LICENSE](LICENSE)。

---

## English

PicShrink (图瘦身 / "slim-down pictures") is a fully-local image compressor for Windows. v11 adds persistent settings and reversible backups: the right-click entry now honours a saved default preset, default output format (keep original / JPG / PNG / WebP) and one of three output locations (export next to the original with a `_compressed` suffix, export flat into a fixed folder, or overwrite the original with automatic backup). Backups are browsable and restorable from the GUI, and even a restore is itself reversible.

v11 also fixes several real bugs: transparent PNGs crashed with `cannot write mode PA as PNG` (quantisation plus `putalpha()` produced a `PA` mode that Pillow refuses to write); "keep original format" trusted the file extension instead of the real content; the Explorer context menu vanished on multi-select because `MultiSelectModel=Single` only supports one item; and target-size mode could hand back a file larger than the original for PNG.

Seven presets including two target-size presets (≤200KB / ≤120KB with auto binary-search quality). Two lossless presets produce mathematically pixel-identical output (verified via `ImageChops.difference(a,b).getbbox() is None`). No upload, no telemetry, no network after launch. Single-file `.exe` (~19.6MB), no Python install required. Win 10/11 64-bit. MIT.