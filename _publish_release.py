# -*- coding: utf-8 -*-
"""PicShrink 发布脚本: 建 v9/v10 Release + 传资产 + 改仓库 description/topics + 删诊断 milestone.

铁律: token 只从注册表读进内存, 绝不进 stdout / 日志 / 文件 / git.
"""
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import winreg
from pathlib import Path

OWNER = "nansionnan-commits"
REPO = "image-compressor"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"
BASE = Path(__file__).resolve().parent

HDRS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "PicShrink-release",
}


def load_token() -> str:
    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
    ) as k:
        tok, _ = winreg.QueryValueEx(k, "GITHUB_TOKEN")
    tok = (tok or "").strip()
    if not tok:
        sys.exit("GITHUB_TOKEN 为空, 中止")
    return tok


TOK = load_token()
HDRS["Authorization"] = "Bearer " + TOK


def api(method: str, url: str, data=None, raw=None, ctype=None):
    hdrs = dict(HDRS)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    elif raw is not None:
        body = raw
        hdrs["Content-Type"] = ctype or "application/octet-stream"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw_body = r.read()
            return r.status, (json.loads(raw_body) if raw_body else None)
    except urllib.error.HTTPError as e:
        raw_body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw_body)
        except json.JSONDecodeError:
            return e.code, raw_body[:300]


def ensure_release(tag: str, name: str, body: str):
    """返回 (release_id, upload_url_base). upload_url 末尾带 {?name,label} 要剥掉."""
    st, data = api("GET", f"{API}/releases/tags/{tag}")
    if st == 200:
        print(f"  release {tag} 已存在 (id={data['id']}), 复用")
        return data["id"], data["upload_url"].split("{")[0]
    if st != 404:
        sys.exit(f"查询 release {tag} 失败: HTTP {st} {data}")
    st, data = api("POST", f"{API}/releases", {
        "tag_name": tag, "name": name, "body": body,
        "draft": False, "prerelease": False,
    })
    if st not in (200, 201):
        sys.exit(f"创建 release {tag} 失败: HTTP {st} {data}")
    print(f"  release {tag} 已创建 (id={data['id']})")
    return data["id"], data["upload_url"].split("{")[0]


def sync_asset(release_id: int, upload_base: str, path: Path):
    if not path.is_file():
        print(f"  [跳过] 文件不存在: {path}")
        return
    st, data = api("GET", f"{API}/releases/{release_id}/assets?per_page=100")
    if st != 200:
        sys.exit(f"列资产失败: HTTP {st}")
    for a in data:
        if a["name"] == path.name:
            st2, _ = api("DELETE", a["url"])
            print(f"  删同名旧资产 {path.name}: HTTP {st2}")

    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    st, data = api(
        "POST",
        f"{upload_base}?name={path.name}",
        raw=path.read_bytes(), ctype=ctype,
    )
    if st not in (200, 201):
        sys.exit(f"上传 {path.name} 失败: HTTP {st} {data}")
    print(f"  上传 {path.name}  {path.stat().st_size:,} 字节  "
          f"({data['state']}, {data['browser_download_url']})")


NOTES_V9 = """## 图瘦身 (PicShrink) v9 — 右键就能压

完全跑在本机的 Windows 图片压缩工具。**不上传、不联网**。

### 下载

| 资产 | 说明 |
|---|---|
| `PicShrink-v9-portable.zip` | 便携版，解压即用（推荐先试这个）|
| `PicShrink.exe` | 单文件主程序，不想用 bat 也行 |
| `app.ico` | 品牌图标 |

### 这个版本带来了什么

- **图片右键菜单**：`MultiSelectModel=Single`，**选中多张一次压完**，只弹一个窗口
- **文件夹右键**：自动递归扫整个文件夹
- **SendTo 条目** + **桌面快捷方式**，桌面路径走 Windows Known Folder API，**尊重用户把桌面重定向到别的盘**
- 快捷入口走的是**和界面完全相同的 7 预设引擎**，不是另一套简化逻辑
- 默认预设跟随你在界面里最后一次手动选择（`%LOCALAPPDATA%\\图瘦身\\quick.json`）

### 安装

解压后想加右键菜单就双击 `install.bat`；只想用就直接双击 `PicShrink.exe`。
安装只写 `HKCU`，不需要管理员权限。装完在资源管理器按一下 `F5`。

> v10 已经提供**向导式安装包**（有开始菜单、能从「应用」里点卸载），不想折腾 bat 的话直接去 v10。

### 前提

Windows 10 / 11 64 位。**不需要装 Python。**

⚠️ exe 没做代码签名，第一次双击可能弹 SmartScreen，点「更多信息 → 仍要运行」即可。
"""

NOTES_V10 = """## 图瘦身 (PicShrink) v10 — 标准 Windows 安装器

完全跑在本机的 Windows 图片压缩工具。**不上传、不联网**。

### 下载

| 资产 | 说明 |
|---|---|
| `PicShrink-Setup-v10.exe` | **向导式安装包（推荐）**，约 21.2 MB |
| `PicShrink.exe` | 单文件主程序，免安装直接双击 |
| `app.ico` | 品牌图标 |

### 怎么装

双击 `PicShrink-Setup-v10.exe`，一路点「下一步」到「安装」。

- 安装位置 `%LOCALAPPDATA%\\图瘦身\\`，**不需要管理员权限**
- 桌面和开始菜单都有「图瘦身」
- 设置 → 应用 → 找到「图瘦身 (PicShrink) v10」→ **可点击的真卸载器**
- 安装只写 `HKCU`，不影响别的 Windows 账号

### 不想装？

直接双击 `PicShrink.exe` 就能用。想要右键菜单的话，去 [v9 Release](https://github.com/nansionnan-commits/image-compressor/releases/tag/v9) 下便携 ZIP，解压后双击 `install.bat`。

### 核心能力（v7 起未变）

- **7 个预设**，含「主图 ≤ 200KB / ≤ 120KB」两个目标体积预设，自动二分搜索质量，压不达标会在日志里明说，绝不静默失败
- **2 个无损预设**产出**数学零差异**图片（剥 EXIF，验证用 `ImageChops.difference(a,b).getbbox() is None`）
- **原图在任何路径下都不会被改动或覆盖**
- 压完反而更大就保留原图；小于 50KB 的图直接跳过；无损预设设 1KB 绝对下限
- **真 OS 级拖拽**（tkinterdnd2 / tkdnd 2.10.3），不是程序内部的伪拖
- 支持 `jpg` `jpeg` `png` `bmp` `webp` `tif` `tiff`，默认保持原格式

### 前提

Windows 10 / 11 64 位。**不需要装 Python。**

⚠️ exe 没做代码签名，第一次运行可能弹 SmartScreen，点「更多信息 → 仍要运行」即可。

### 已知限制

- **全局自定义快捷键暂未提供**（计划 v10.1）。目前走资源管理器右键 / 文件夹右键 / SendTo / 桌面与开始菜单这五条官方支持的路径。
"""

NOTES_V11 = """## 图瘦身 (PicShrink) v11 — 设置能被记住，压缩结果能还原

完全跑在本机的 Windows 图片压缩工具。**不上传、不联网**。

### 下载

| 资产 | 说明 |
|---|---|
| `PicShrink-Setup-v11.exe` | **向导式安装包（推荐）**，约 21.2 MB |
| `PicShrink-v11-portable.zip` | 便携版，解压即用（含 install.bat / uninstall.bat）|
| `PicShrink.exe` | 单文件主程序，免安装直接双击 |
| `app.ico` | 品牌图标 |

### 怎么装

双击 `PicShrink-Setup-v11.exe`，一路点「下一步」到「安装」。

- 安装位置 `%LOCALAPPDATA%\\图瘦身\\`，**不需要管理员权限**
- 桌面和开始菜单都有「图瘦身」
- 设置 → 应用 → 找到「图瘦身 (PicShrink) v11」→ **可点击的真卸载器**
- 安装只写 `HKCU`，不影响别的 Windows 账号

### v11 最大的变化：右键菜单终于听话了

**批量多选真的能用了。** 选中十几张图 → 右键 → 「用图瘦身处理」 → 一次全压完。

v9 把 `MultiSelectModel` 设成了 `Single`，微软文档写明它**只支持单选**，选中数量对不上时 Explorer 直接不显示这个菜单项 —— 表现就是「单选有、多选没了」。v11 改成 `Player` + 命令行 `"%*"`。

### 你的默认设置会被记住

点主界面右上角 **⚙ 设置**，改一次长期有效（存在 `%LOCALAPPDATA%\\图瘦身\\settings.json`）：

| 设置项 | 可选值 | 默认 |
|---|---|---|
| 右键菜单默认压缩程度 | 7 个预设任选 | ⚡ 推荐压缩 |
| 默认输出格式 | 保持原格式 / JPG / PNG / WebP | 保持原格式 |
| 默认输出位置 | 见下 | 原文件夹加后缀 |

**三种输出位置：**

1. **原文件夹导出，名字后加 `_compressed`**（默认，最安全）—— 原图一个字节都不动
2. **统一导出到指定文件夹** —— 平铺过去，不同来源的同名图自动加序号，绝不互相覆盖
3. **直接覆盖原图** —— 覆盖前强制弹框确认 + 自动备份。没确认过就退一步，谁也别想动你的原图

### 备份能还原

主界面「↩︎ 备份/还原」列出所有历史批次，点一下就还原。还原前还会再存一次「还原前」版本 —— **让还原本身也可逆**，还原错了还能再退回去。

### 这次修的真 bug

- **透明 PNG 一压就崩**（`cannot write mode PA as PNG`）—— 带 alpha 的图不再做调色板量化，走 RGBA + zlib 优化
- **「保持原格式」只看扩展名** —— 后缀骗人的图不再崩，改按文件真实内容判断
- **目标体积模式「越压越大」** —— 压不到目标而且反而更大时，保留原图并说明原因
- **固定目录同名图互相覆盖** —— 改成自动加序号
- **安装器装出两份 exe** —— 强制安装目录回到 `%LOCALAPPDATA%`，右键菜单和安装目录永远指向同一份

### 核心能力（v7 起未变）

- **7 个预设**，含「主图 ≤ 200KB / ≤ 120KB」两个目标体积预设，自动二分搜索质量
- **2 个无损预设**产出**数学零差异**图片（验证用 `ImageChops.difference(a,b).getbbox() is None`）
- **原图在任何默认路径下都不会被改动**
- 压完反而更大就保留原图；小于 50KB 的图直接跳过
- **真 OS 级拖拽**（tkinterdnd2 / tkdnd 2.10.3）
- 支持 `jpg` `jpeg` `png` `bmp` `webp` `tif` `tiff`

### 前提

Windows 10 / 11 64 位。**不需要装 Python。**

⚠️ exe 没做代码签名，第一次运行可能弹 SmartScreen，点「更多信息 → 仍要运行」即可。

### 已知限制

- **全局自定义快捷键暂未提供**（计划 v11.1）。目前走资源管理器右键 / 文件夹右键 / SendTo / 桌面与开始菜单这五条官方支持的路径。
"""

DESCRIPTION = ("Windows 图片压缩工具：拖进去就压，原图永不覆盖，"
               "无损预设像素零差异，多选右键一次压完。纯本地运行，不上传、不联网。")

TOPICS = ["python", "image-compression", "image-optimization",
          "pillow", "tkinter", "windows", "photo-editor",
          "bulk-image-compressor", "lossless", "amazon-seller"]


def main() -> None:
    print("=== 1) Release ===")
    v9_assets = [BASE / "dist/PicShrink-v9-portable.zip",
                 BASE / "dist/PicShrink.exe",
                 BASE / "app.ico"]
    v10_assets = [BASE / "_setup_out/PicShrink-Setup-v10.exe",
                  BASE / "dist/PicShrink.exe",
                  BASE / "app.ico"]
    v11_assets = [BASE / "_setup_out/PicShrink-Setup-v11.exe",
                  BASE / "dist/PicShrink-v11-portable.zip",
                  BASE / "dist/PicShrink.exe",
                  BASE / "app.ico"]

    for tag, name, notes, assets in (
        ("v9", "v9 — 右键快捷入口 + 便携版", NOTES_V9, v9_assets),
        ("v10", "v10 — 标准 Windows 安装器", NOTES_V10, v10_assets),
        ("v11", "v11 — 设置可自定义 + 备份可还原 + 多选右键修复",
         NOTES_V11, v11_assets),
    ):
        print(f"\n[{tag}]")
        rid, upload_base = ensure_release(tag, name, notes)
        for p in assets:
            sync_asset(rid, upload_base, p)

    print("\n=== 2) 仓库 description ===")
    st, data = api("PATCH", API, {"description": DESCRIPTION})
    print(f"  HTTP {st}: {data.get('description') if isinstance(data, dict) else data}")

    print("\n=== 3) 仓库 topics ===")
    st, data = api("PUT", f"{API}/topics",
                   {"names": TOPICS}, )
    if st in (200, 422):
        # 422 通常是已经一样, 不算失败
        st2, cur = api("GET", f"{API}/topics")
        print(f"  当前 topics: {(cur or {}).get('names')}")
    else:
        print(f"  HTTP {st}: {data}")

    print("\n=== 4) 删诊断 milestone ===")
    st, data = api("GET", f"{API}/milestones?state=all")
    for m in (data or []):
        n = m["number"]
        st2, d2 = api("DELETE", f"{API}/milestones/{n}")
        print(f"  #{n} {m['title']}: HTTP {st2}")

    print("\n=== 5) 收尾核对 ===")
    st, data = api("GET", f"{API}/releases?per_page=20")
    for r in (data or []):
        print(f"  {r['tag_name']:<6} {r['name']}  "
              f"({len(r['assets'])} 个资产, draft={r['draft']})")
    st, data = api("GET", f"{API}/milestones?state=all")
    print(f"  剩余 milestone: {[(m['number'], m['title']) for m in (data or [])]}")


if __name__ == "__main__":
    main()