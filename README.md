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
1. 下载 releases 里最新的「PicShrink-Setup-v11.4.exe」
2. 双击它，一路点「下一步」到「安装」
3. 完事儿。桌面和开始菜单都有「图瘦身」
4. 选中图片右键 → 「立即压缩」直接压，或「加入压缩队列」丢进主窗口慢慢挑（两个都能多选）
5. 想改默认行为 → 打开图瘦身，点「⚙ 设置」
6. 想卸：设置 → 应用 → 找到「图瘦身 (PicShrink) v11.4」→ 卸载
```

**方式 B：不装，解压即用（绿色便携版）**

```text
1. 下载 releases 里最新的「PicShrink-v11.4-portable.zip」
2. 解压到任意文件夹
3. 直接双击「PicShrink.exe」
4. 想加右键菜单 → 双击「install.bat」
```

两种方式都**不需要装 Python**，只需要 Win 10 / 11 64 位。

> 首次双击 Windows 可能弹「Windows 已保护你的电脑」（SmartScreen），点 **更多信息 → 仍要运行** 即可。我们的 exe 没做代码签名，这是已知限制，不是 bug。

---

## v11.2：预设名字终于说人话了 + 多一档小体积

### 之前名字看不懂在哪

老名字叫「📦 主图≤200KB」「📐 A+图≤500KB」，问题在于：**光看名字猜不出它到底动没动你的像素**。

「主图≤200KB」到底是缩到 1280 还是缩到 1100？「A+图≤500KB」到底会不会偷偷改尺寸？名字里一个字都没提。而这两种行为**恰好相反**，猜错了就是货不对板。

### 现在：名字直接写清楚改了什么

| 老名字 | 新名字 | 差别 |
|---|---|---|
| `📦 主图≤200KB` | `📦 限边长1280 ≤200KB` | 会缩，长边压到 1280 |
| `📦 主图≤120KB` | `📦 限边长1100 ≤120KB` | 会缩，长边压到 1100 |
| `📐 A+图≤500KB` | `📐 尺寸不变 ≤500KB` | **一个像素都不动** |
| `📐 A+图≤900KB` | `📐 尺寸不变 ≤900KB` | **一个像素都不动** |
| — | `📐 尺寸不变 ≤200KB` | **新增**，同样不动尺寸 |

分界线很干脆：**带「📦 限边长」的会缩，不带的就是「📐 尺寸不变」——尺寸、比例、边长一个像素都不动，只降质量。**

### 为什么要专门留「尺寸不变」这一档

A+ 各模块的像素尺寸是平台硬性要求（`970×300`、`1400×300`、`1920×600` 等），**缩了就直接不合规**。而压体积只需要降质量就够了，完全没必要动尺寸。

以前「A+图≤900KB」这个名字让人以为它会偷偷缩图。现在它叫「尺寸不变 ≤900KB」，用的人一眼就知道这张图拿去贴 A+ 是安全的。

### 新增 ≤200KB 小体积档

之前最小只到 500KB。有些模块塞 500KB 太奢侈，现在加一档 **200KB**，同样只降质量。

> 这里的 500 / 900 / 200 KB 是工具给出的**保守目标**，不是平台的官方数字。平台实际限制请以你所在站点的后台要求为准。

### 改名不用你做任何事

你之前在设置里选的预设，**升级后自动还是那个**，不会静默变回「推荐压缩」—— 老名字会被自动搬到新名字上。界面和设置里存的旧全名也照样认。

### 预设总数：7 → 10

| 类型 | 数量 | 说明 |
|---|---|---|
| 无损 | 2 | 像素零差异 |
| 固定质量 | 2 | q=85 / q=80 |
| 📦 限边长 | 2 | 缩尺寸 + 控体积 |
| 📐 尺寸不变 | 3 | 只降质量，200 / 500 / 900KB |
| 🛒 亚马逊主图 | 1 | 2000px JPG |

---

## v11.1：右键真的修好了

### 右键文件夹以前完全没反应

文件菜单那行命令是 `"%*"`（把选中的所有文件传进去），文件夹菜单当初照抄了这一行。可是**文件夹右键点的是文件夹本身**，没有「一批选中文件」这回事，`%*` 就展开成了空字符串 —— 程序收到零个参数，自然什么都不干。

v11.1 把文件夹那行换成 `"%V"`（当前文件夹的完整路径）。现在右键文件夹会递归压整个目录。

### 报错信息终于能用了

以前只说一句「没找到可处理的图片」，你没法判断是自己的问题还是菜单坏了。现在分两种情况：

- **一个路径都没收到** → 直说「菜单项注册坏了，重装一次即可修复」
- **收到了但路径不对** → 把实际收到的内容原样摆给你看

真再出问题，把弹窗内容截图发过来就行。

### 安装时会体检这台电脑有没有重复安装

如果之前换过安装目录（比如老版本装在 D 盘、现在装在 `%LOCALAPPDATA%`），老的卸载记录不会被自动清掉，磁盘上会留下两份 exe。这时：

- 手动安装 → 装完弹窗告诉你旧的那份在哪、怎么清
- 静默安装 → 不弹框（免得无人值守时卡住），信息写到 `%LOCALAPPDATA%\图瘦身\install-warnings.txt` 和日志里

> 重复安装**不影响正常使用** —— 右键菜单只认刚装好的这一份。它只是让「程序和功能」里只能卸载其中一份而已。

### 每次启动的真实参数都会记进日志

`%TEMP%\picshrink_v11.log` 现在记录 exe 路径、原始 argv、解析结果。以后再出问题有据可查，不用靠猜。

---

## v11：设置会被记住，压缩结果能还原

### 设置会被记住

点主界面右上角 **⚙ 设置**，可以改三样东西，**关掉再开、换台电脑重启都还在**（存在 `%LOCALAPPDATA%\图瘦身\settings.json`）：

| 设置项 | 可选值 | 默认 |
|---|---|---|
| 右键菜单默认用哪个预设 | 10 个预设任选 | ⚡ 推荐压缩 |
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

安装器（`PicShrink-Setup-v11.4.exe`）是标准 Windows 向导式安装包：

| 项 | 值 |
|---|---|
| 安装位置 | `%LOCALAPPDATA%\图瘦身\`（不需要管理员权限）|
| 开始菜单 | 开始菜单里有一组「图瘦身」：主程序 + 卸载项 |
| 桌面 | 桌面快捷方式「图瘦身」 |
| 卸载 | 设置 → 应用 →「图瘦身 (PicShrink) v11.4」→ 卸载，**能点** |
| 注册表 | 只写 `HKCU`，不影响别的账号 |

装完之后，图片压缩这件事**根本不用打开主界面**：

| 你做的事 | 结果 |
|---|---|
| 右键一张图 → 「立即压缩」| 直接压这一张 |
| **选中多张图** → 右键 →「立即压缩」| **一次全压完**，一张一个窗口都不会多弹 |
| 右键一个文件夹 →「立即压缩这个文件夹」| 递归扫整个文件夹，一次压完 |
| 右键图/文件夹 →「加入压缩队列」| 丢进**已经开着**的主窗口待处理列表，窗口自动弹到最前，可以先看看再点开始 |
| 右键任意文件 → 发送到 →「图瘦身」| 同上，SendTo 的经典用法 |

> 「加入压缩队列」不会多开窗口。主窗口已经开着就直接把路径投进去退出；没开着才新开一个。

快捷入口走的是**和界面完全相同的 7 预设引擎**，不是另一套简化逻辑。

压缩过程会弹一个进度窗，压完弹结果窗（成功 / 跳过 / 失败各几张、省了多少、输出在哪），结果窗上有「打开输出目录」和「全部重压一遍」，8 秒不操作会自动关掉。

### 安装 / 卸载

| 方式 | 文件 | 干什么 |
|---|---|---|
| **推荐** | `PicShrink-Setup-v11.4.exe` | 向导式安装：放文件 + 桌面/开始菜单图标 + 登记到「应用」列表可点的卸载器；顺带调用下面的 `--install` 把右键菜单、SendTo 一起配好 |
| 便携 | `install.bat` | 装右键菜单（图片 / 文件夹）、SendTo、桌面快捷方式 |
| 便携 | `uninstall.bat` | 卸掉上面这些；**已压好的图片一律保留**，还会问你要不要删安装目录 |

安装只写 `HKCU`，不碰系统级注册表，不需要管理员权限，只对当前这个 Windows 账号生效。装完在资源管理器里按一下 `F5` 右键菜单就出现。

走安装器卸载时，程序会先跑一次 `--uninstall --quiet` 清掉右键菜单 / SendTo / 桌面快捷方式（但**保留安装目录**），再由安装器自己删文件——两边分工不重叠，**你压好的图片一张都不会少**。

> `install.bat` / `uninstall.bat` 内部是**纯 ASCII**，一个中文都没有。所有中文提示都由 exe 自己弹窗。这样做是因为 `.bat` 会被 cmd 按控制台码页解析，中文脚本在部分机器上会被切乱码导致连 exe 都找不到。
>
> Inno Setup 安装器不受这条限制——它是 Unicode 的，所以安装向导、开始菜单项、卸载项全都可以正常显示中文。

---

## 10 个内置预设（还能自己存更多）

按钮按行均分宽度，每行按本页名字最长的那个撑开，**点不全也不会被截断**：

| 预设 | 干啥 | 会缩尺寸吗 | JPG 省多少 |
|---|---|---|---|
| 🎯 **无损压缩** | 剥 EXIF，**像素零差异** | 否 | 5–20% |
| 💎 **极致保真** | 同上，但保留 EXIF 拍摄信息 | 否 | 少一点 |
| ⚡ **推荐压缩** | q=85 重编码，业界甜点 | 否 | ~25% |
| 💾 **压最小** | q=80 重编码 | 否 | 最多 |
| 🛒 **亚马逊主图** | 转 JPG + 长边 2000px + q=85 | **是**，2000px | 很多 |
| 📦 **限边长1280 ≤200KB** | 缩到 1280 + 自动二分搜索质量 | **是**，1280 | 自动达标 |
| 📦 **限边长1100 ≤120KB** | 缩到 1100 + 自动二分搜索质量 | **是**，1100 | 自动达标 |
| 📐 **尺寸不变 ≤900KB** | 只降质量 | **否** | 自动达标 |
| 📐 **尺寸不变 ≤500KB** | 只降质量 | **否** | 自动达标 |
| 📐 **尺寸不变 ≤200KB** | 只降质量 | **否** | 自动达标 |

**「会缩尺寸吗」这一列是选预设时唯一要看的。** 带 `📦 限边长` 的会把图缩小，带 `📐 尺寸不变` 的尺寸、比例、边长一个像素都不动、只降质量。

**五个目标体积预设的原理**：先把图等比缩到该预设的边长限制（`📐` 那一类是 0，即不缩），然后在质量区间 [18, 92] 里**二分搜索**——找到刚好不超过目标字节数的最高质量。降质量比硬降像素能保住更多细节。

> 如果压到最低质量（q=18）**仍然大于原图**（这只在「目标体积 + PNG + 保持原格式」这种组合下会发生，因为对 PNG 降质量几乎没用），v11 会**直接跳过并保留原图**，绝不给你一个比原来更大的文件。日志里会写清楚原因。
>
> 高级用户可以在右下的「自定义参数」面板自己填「目标体积 (KB)」，> 0 即自动切到目标模式。

---

## v11.4：预设可以自己存了

内置那 10 个是产品定的，总有人要的档位它没有——比如「长边 1600、压到 250KB、转 JPG、留 EXIF」。以前只能每次手动调一遍，调完下次又得重调。

现在可以**存成自己的预设**：

```text
1. 勾上「显示自定义参数 (高级用户)」
2. 调：压缩模式 / 质量 / 目标体积 / 输出格式 / 长边限制 / 保留 EXIF
3. 在「预设名称」里起个名字 → 点「💾 保存为自定义预设」
4. 主界面多出「★ 我的自定义预设」区，点一下就套用
```

每个自定义预设旁边有 ✎（改名）和 🗑（删除）。改名和删除都会同步更新「⚙ 设置」里的右键默认预设，不会出现「右键悄悄变回推荐压缩」。

### 卸载重装，预设还在

自定义预设存在 **`%APPDATA%\图瘦身\presets.json`**，**不在安装目录里**。

这是故意的。安装目录是 `%LOCALAPPDATA%\图瘦身`，卸载时那里会被清空——你在卸载时点「是」删安装目录，连 `settings.json` 一起没了。预设放进去就等于「卸载一次全没了」。

`%APPDATA%`（AppData\Roaming）是安装器和卸载器**永远碰不到**的地方，所以：

| 场景 | 你的自定义预设 |
|---|---|
| 关掉程序再打开 | ✅ 在 |
| 换个版本重装 | ✅ 在 |
| 卸载（哪怕点了删安装目录）再装 | ✅ 在 |
| 换台电脑用同一个域账号 | ✅ 在（Roaming 会跟着走） |

内置预设的编号（`--preset 1` 到 `--preset 10`）**一个都没动**，老快捷方式、老脚本照常能用。自定义预设只能用**全名**选，不占编号——你删掉一个自定义预设，后面所有内置编号都不会错位。

### 存的是什么

```json
{
  "version": 1,
  "presets": {
    "我的主图 300KB": {
      "mode": "target", "quality": 90, "target_kb": 300,
      "format": "jpg", "max_side": 2000, "keep_exif": false
    }
  }
}
```

字段跟内置预设完全一致，文件坏了会自动当空处理（不会让程序起不来），单个条目写坏了只会丢那一条。

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

# 生成并编译安装器 (v11.4)
C:\Python314\python.exe _mk_iss.py
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" setup.iss

# 产物: _setup_out\PicShrink-Setup-v11.4.exe
```

> `--clean` 重新打包前先结束残留的 `PicShrink.exe`，否则 `dist\PicShrink.exe` 被占用会直接报 `WinError 5`。

`图瘦身.spec` 里 `collect_all tkinterdnd2` 和 `datas = [('app.ico', '.')]` 都是必须的：前者保证 tkdnd 的 tcl/dll 进 onefile，后者让运行时读得到品牌图标、也让安装器能把图标取出来给右键菜单用。

exe 文件名定成 ASCII 的 `PicShrink` 而不是中文，就是为了让 `install.bat` / `uninstall.bat` 能稳定引用它（见上面「安装 / 卸载」那条）。中文品牌留在界面、快捷方式和右键菜单显示名里。

---

## 文件清单

| 文件 | 作用 |
|---|---|
| `compress_images_gui.py` | **图瘦身 (PicShrink) v11.4 入口** — Tkinter + tkinterdnd2 OS 拖拽，自带压缩引擎、`_safe_out_path()`、目标体积模式二分搜索、应用图标、右键快捷入口与安装/卸载、设置持久化与备份还原、旧安装体检 |
| `app.ico` | 品牌图标（256/128/64/48/32/16 多尺寸），打包时嵌入 exe |
| `图瘦身.spec` | PyInstaller 打包配置（`--collect-all tkinterdnd2` + 嵌入 app.ico）|
| `setup.iss` | Inno Setup 6 安装器脚本（v11.4）— 向导式安装 + 开始菜单 + 卸载器登记 |
| `_mk_iss.py` | 生成 `setup.iss` 的脚本（带 UTF-8 BOM）|
| `_mk_portable.py` | 生成便携 ZIP 的脚本（校验 bat 必须纯 ASCII + 全 CRLF）|
| `install.bat` / `uninstall.bat` | 纯 ASCII 安装 / 卸载壳，转调 `PicShrink.exe --install` / `--uninstall` |
| `compress_images.py` | 命令行等价入口（同款 7 预设 + 目标体积模式）|
| `_jpeg_strip.py` | JPEG 无损优化器（纯 Python，替代 jpegoptim）|
| `dist/PicShrink.exe` | 打包好的单文件可执行（约 19.6 MB）|
| `_shots/` | 截图存档 |

---

## 历史 & 版本

### v11.4 — 预设可以自己存了（2026-10）

**改的真问题：内置 10 个预设是产品定的，总有人要的档位它没有**

以前要一个自定义档位，只能每次手动调一遍「自定义参数」——模式、质量、目标体积、格式、长边、EXIF 六项，调完下次又得从头调。

现在调完可以直接存下来：

| 你做的事 | 结果 |
|---|---|
| 勾上「显示自定义参数」调参数 → 起名 → 「💾 保存」 | 主界面多出「★ 我的自定义预设」区 |
| 点自定义预设的按钮 | 六个参数一次性套用 |
| ✎ / 🗑 | 改名 / 删除，改名和删除都会同步更新「⚙ 设置」里的右键默认预设 |

**关键决定：预设存 `%APPDATA%\图瘦身\presets.json`，不在安装目录里。**

安装目录是 `%LOCALAPPDATA%\图瘦身`，卸载时会被清空（`v9_uninstall()` 里还有一行 `shutil.rmtree(dest)`，用户在卸载时点"是"的话连 `settings.json` 一起没）。用户的硬要求是"卸载后再装新版本，预设还在"，所以预设必须存在安装器/卸载器永远碰不到的地方 —— `AppData\Roaming` 正好满足。

**内置预设一个都没动**：`--preset 1` 到 `--preset 10` 的编号和顺序一字不改，老快捷方式、老脚本照常能用。自定义预设**只用全名选、不占编号** —— 用户删掉一个自定义预设，后面所有内置编号都不会错位（这正是 v11.2 那轮踩过的坑：新增档位插在中间会把后面序号顶掉一位）。

**顺带修掉的一个真 bug**（新写的测试当场抓到的）：改名自定义预设时，"设置里存的是不是这个预设名"必须在**改磁盘之前**判断。改完磁盘旧名就不存在了，此时 `_load_settings()` 会把它判成非法并静默回落成默认档 —— 于是引用断了，右键默认悄悄变回「推荐压缩」，用户完全不知道为什么。现在改名/删除都改用 `_raw_settings()` 读原始值。

**回归：** 新增 `_t_v19_custom_presets.py`（78 项，全绿），锁住 10 件事：存储位置不在安装目录、存取往返、坏文件不崩、参数清洗、内置 10 个没动、合并逻辑、settings 能指向自定义预设、`--preset` 编号不变、改名/删除同步配置、**模拟卸载（整个安装目录被 rmtree）后预设仍在**。已接进 `_t_run_all.py`，护栏审计加了 F 段（自定义预设是第二条用户配置通路，`LOCALAPPDATA` 重定向管不到，得单独指走 + 单独快照）。

### v11.3 — 右键多了一条「加入压缩队列」（2026-10）

**改的真问题：右键只能"点了就压"，想先看看再压做不到**

以前右键菜单只有一条路：点下去就开一个进度窗开始压。压之前你没法改预设、没法挑输出位置、也没法看这次到底要压哪些文件 —— 主界面里那些能力，右键一条都用不上。

现在右键分成两条：

| 菜单项 | 图片右键 | 文件夹右键 | 行为 |
|---|---|---|---|
| 立即压缩 | ✅ 可多选 | ✅ 递归 | 点完直接压，跟以前一样，不弹主窗口 |
| 加入压缩队列 | ✅ 可多选 | ✅ 递归 | 路径投进**已经开着**的主窗口待处理列表，窗口自动弹到最前 |

「加入压缩队列」**不会多开窗口**：主窗口开着就直接投递然后退出这个进程；没开着才新开一个。投递用命名互斥体 + `%TEMP%\PicShrink\inbox\` 目录，主窗口每 400ms 收一次，写入时先落 `.tmp` 再原子改名，主窗口永远不会读到半截文件。主窗口退出前遗留的投递（超过 60 秒）会自动清掉。

**顺手修掉的升级坑：**

- **升级后右键出现两套菜单**：菜单在注册表里的键名以前直接用中文显示名（`用图瘦身处理`），一改显示名就留下一个删不掉的孤儿键。现在键名固定成 ASCII（`PicShrinkQuick` / `PicShrinkQueue`），显示名随便改都不会产生孤儿项；安装和卸载都会主动清掉历史的中文键
- **旧版留下的 `MultiSelectModel` 会害多选失效**：安装时主动删掉这个值（它在 Explorer 里会把命令行截得很短，导致路径传不进来）

**回归（全部实跑通过）：** 新增 `_t_v18_menu_queue.py` 38 项全绿；统一回归入口 `_t_run_all.py` 17 项全绿（65.3 秒），同时快照/还原三代菜单键，真实 `settings.json` / `quick.json` 和右键菜单全程未被测试污染；防线审计加了"三代键都在快照范围""新测试进了自动入口"两条断言。

**真机验收（装完 v11.3 后实跑）：** 静默安装退出码 0；注册表读回确认 4 个菜单项的显示名与命令行都对，命令里没有 `%*`、没有 `MultiSelectModel`，旧的中文键在图片和文件夹两类下都已删除；按注册表里的真实命令形状投递 4 张图到「加入压缩队列」，投递进程退出码 0，主窗口投递前后都是 1 个，待处理列表显示 4 张、状态栏「已选 4 张图 (+4)」—— 没有多弹窗口。

### v11.2 — 预设名字说人话了 + 新增 200KB 档（2026-10）

**改名（4 个）**，目的是让名字直接回答「到底动没动我的像素」：

| 老名字 | 新名字 |
|---|---|
| `📦 主图≤200KB` | `📦 限边长1280 ≤200KB` |
| `📦 主图≤120KB` | `📦 限边长1100 ≤120KB` |
| `📐 A+图≤500KB` | `📐 尺寸不变 ≤500KB` |
| `📐 A+图≤900KB` | `📐 尺寸不变 ≤900KB` |

**新增（1 个）**：`📐 尺寸不变 ≤200KB` —— 尺寸/比例/边长一个像素不动，只降质量。预设总数 7 → 10。

**改名对用户透明**：`PRESET_RENAMES` 迁移表在 `_load_settings()` 里**先迁移、再校验**，老配置里的旧名自动搬到新名，不会被判非法后静默回落到「推荐压缩」。`--preset` 按插入顺序编号，新档追加在 `PRESETS` **末尾**，老脚本里的 `--preset 1`–`9` 语义完全不变。

**按钮不再截断**：去掉写死的 `width=15`，改 `sticky="ew"` + `columnconfigure(..., uniform="preset")`，每行按本页最长名字撑开，并新增独立图例行。

**回归（全部实跑通过）**：统一入口 16/16 全绿（67.9s，退出码 0）、预设改名 134/134、打包 exe 预设 93/93、exe 35/35、输出模式 8/8、防线审计 A–E 全 PASS。真机截图验收按钮三行 4/3/3 完整无截断。

**顺手修掉的测试隔离事故**：`_t_run_all.py` 原本只重定向 `LOCALAPPDATA`（管得住 `settings.json` / `quick.json`），但**注册表不受环境变量影响** —— `_t_v9_win2.py` 的 `--install --quiet` 把右键菜单写到了隔离临时目录且从不还原，跑完用户右键就失效。现已加注册表快照/还原 + 逐测试归因打印真凶，并给会真写 HKCU 的测试自身加 `atexit` 护栏。

### v11.1 — 右键真的修好了 + 会查重装了（2026-10）

**修的真 bug：**

- **右键文件夹完全没反应**：`Directory\shell` 的命令行误用了 `"%*"`。文件夹右键点的是文件夹**本身**，没有「一批选中文件」这回事，`%*` 展开成空字符串 → 程序收到零个参数 → 什么都不干。改成 `"%V"`（当前文件夹完整路径），现在右键文件夹能递归压整个目录
- **报错信息没法用**：以前只说一句「没找到可处理的图片」，用户无法判断是自己没选图还是菜单传参坏了。现在分两种情况给不同提示：压根没收到路径 → 直说菜单注册坏了、让你重装；收到了但不对 → 把实际收到的内容原样摆出来

**新能力：**

- **启动时把真实参数落盘**：`%TEMP%\picshrink_v11.log` 现在会记录 exe 路径、原始 argv、解析结果。以后再出问题有据可查，不用靠猜
- **安装时体检重复安装**：扫 HKCU/HKLM（含 32 位重定向）的卸载登记项 + 常见历史目录，发现同一台电脑上还有别的图瘦身副本就报出来。手动安装弹窗告知；静默安装只写日志和 `install-warnings.txt`，**不弹框**（安装器就是用 `--install --quiet` 调的，弹框会让无人值守安装永久卡住）。重复安装不影响使用 —— 右键菜单只认刚装好的这一份，它只是让「程序和功能」里只能卸载其中一份

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
- **全局自定义快捷键暂未提供**，v11.2 也没有做。目前走的是资源管理器右键 / 文件夹右键 / SendTo / 桌面与开始菜单图标这五条路，都是官方支持的机制。做成「任意界面按一个全局热键就压缩当前选中的图」需要常驻进程 + 读 Explorer 选中项 + 托盘 + 开机自启，成本和风险都不小，属于将来版本的范围。
- **`install.bat` 必须是纯 ASCII**。这是踩过坑之后定的：cmd 按活动控制台码页解析 `.bat`，中文脚本在码页不匹配时会被切乱码。中文提示一律由 exe 弹窗。
- **目标体积 + PNG 常常压不动**。PNG 是无损格式，对它降质量本来就没意义。真要小就得转 JPG/WebP——在设置里把输出格式改成 WebP 就有了。

---

## License

MIT — 完整文本见 [LICENSE](LICENSE)。

---

## English

PicShrink (图瘦身 / "slim-down pictures") is a fully-local image compressor for Windows. v11.2 renames four presets so the name states whether your pixels get resized, and adds one more size target, bringing the total from 7 to 10. `📦 主图≤200KB` became `📦 限边长1280 ≤200KB` and `📦 主图≤120KB` became `📦 限边长1100 ≤120KB` — both shrink the long edge. `📐 A+图≤500KB` / `📐 A+图≤900KB` became `📐 尺寸不变 ≤500KB` / `📐 尺寸不变 ≤900KB`, which touch no pixel at all: dimensions, aspect ratio and edge length are untouched and only the quality is lowered. The new `📐 尺寸不变 ≤200KB` works the same way. This matters for Amazon A+ modules, where pixel dimensions are a hard requirement (`970×300`, `1400×300`, `1920×600`, …) — shrinking breaks compliance, and lowering quality alone is enough to hit a size budget. Renaming is transparent: stored presets are migrated before validation, so a saved preset never silently reverts to the default. The new preset is appended at the end of the table, so existing `--preset 1`–`9` numbering is unchanged.

v11.1 fixed the remaining right-click bugs. The folder context menu was dead: its command line used `%*` (the multi-select token), but a folder has no "list of selected files", so `%*` expanded to nothing and the app received zero arguments. It now uses `%V`, the folder's own full path, so right-clicking a folder recursively compresses it. On launch, the app now writes the real exe path, raw argv and parsed arguments to `%TEMP%\picshrink_v11.log`, so a failure is diagnosable instead of guesswork. Silent installs (`--install --quiet`) no longer pop a modal dialog when a previous install is found; findings go to the log and to `%LOCALAPPDATA%\图瘦身\install-warnings.txt`, while manual installs still warn on screen. Nothing is ever deleted automatically.

v11 adds persistent settings and reversible backups: the right-click entry now honours a saved default preset, default output format (keep original / JPG / PNG / WebP) and one of three output locations (export next to the original with a `_compressed` suffix, export flat into a fixed folder, or overwrite the original with automatic backup). Backups are browsable and restorable from the GUI, and even a restore is itself reversible.

v11 also fixes several real bugs: transparent PNGs crashed with `cannot write mode PA as PNG` (quantisation plus `putalpha()` produced a `PA` mode that Pillow refuses to write); "keep original format" trusted the file extension instead of the real content; the Explorer context menu vanished on multi-select because `MultiSelectModel=Single` only supports one item; and target-size mode could hand back a file larger than the original for PNG.

Seven presets including two target-size presets (≤200KB / ≤120KB with auto binary-search quality). Two lossless presets produce mathematically pixel-identical output (verified via `ImageChops.difference(a,b).getbbox() is None`). No upload, no telemetry, no network after launch. Single-file `.exe` (~19.6MB), no Python install required. Win 10/11 64-bit. MIT.