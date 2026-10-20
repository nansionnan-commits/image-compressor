"""
compress_images_flet.py — v5 桌面应用 (Flet Material 3)

双击 .bat → 弹出原生窗口, Material 3 风格, 看起来像现代 App。
所有压缩逻辑在 _core.py 里, 这里只负责界面。

启动方式:
    flet run compress_images_flet.py
    或直接 python compress_images_flet.py
"""

import asyncio
import json
import os
import sys
import threading
from pathlib import Path

# 把当前脚本所在目录加到 sys.path, 让 from _core import 能找到 _core.py
# (Py 3.11+ 双击 .py 不自动加 cwd, 必须手动加)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flet as ft

from _core import (
    PRESETS,
    SUPPORTED,
    DEFAULT_OUTPUT_DIR,
    human_size,
    preview_size,
    batch_compress,
)


# ============== 配置 ==============
CONFIG_PATH = Path(os.environ.get("APPDATA", str(Path.home()))) / "image-compressor" / "config.json"


def load_config() -> dict:
    default = {
        "default_output_dir": str(Path.cwd() / DEFAULT_OUTPUT_DIR),
        "default_preset": "⚡ 推荐压缩",
        "window_size": {"w": 1180, "h": 760},
        "show_advanced": False,
    }
    if not CONFIG_PATH.exists():
        return default
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for k, v in default.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return default


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ============== 应用入口 ==============
async def main(page: ft.Page):
    cfg = load_config()
    page.title = "图片一键压缩"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE, use_material3=True)
    page.window.width = cfg["window_size"]["w"]
    page.window.height = cfg["window_size"]["h"]
    page.window.min_width = 980
    page.window.min_height = 680
    page.padding = 0
    page.theme_mode = ft.ThemeMode.LIGHT

    def snack(text, error=False):
        """Flet 1.0.4 没有 page.open(SnackBar), 改用 open=True 手动管。"""
        sb = ft.SnackBar(
            content=ft.Text(text),
            bgcolor=ft.Colors.RED_400 if error else None,
            open=True,
        )
        page.overlay.append(sb)
        page.update()

    state = {
        "files": [],                  # list[Path]
        "selected_preset": cfg["default_preset"],
        "output_dir": Path(cfg["default_output_dir"]),
        "show_advanced": cfg["show_advanced"],
        "running": False,
        "results": [],                 # list[dict]
    }

    save_pending = False

    # ---------- 文件选择器 (Flet 1.0.4: Service 在 page.services, API 直接 await) ----------
    file_picker = ft.FilePicker()
    folder_picker = ft.FilePicker()
    output_dir_picker = ft.FilePicker()
    page.services.extend([file_picker, folder_picker, output_dir_picker])
    page.update()

    async def do_pick_files():
        files = await file_picker.pick_files(allow_multiple=True)
        if not files:
            return
        for f in files:
            p = Path(f.path)
            if p.suffix.lower() in SUPPORTED and p not in state["files"]:
                state["files"].append(p)
        update_file_grid()
        update_preview()
        page.update()

    async def do_pick_folder():
        folder_str = await folder_picker.get_directory_path(dialog_title="选择图片文件夹")
        if not folder_str:
            return
        folder = Path(folder_str)
        for p in folder.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED and p not in state["files"]:
                state["files"].append(p)
        update_file_grid()
        update_preview()
        page.update()

    async def do_pick_output_dir():
        folder_str = await output_dir_picker.get_directory_path(dialog_title="选择输出文件夹")
        if not folder_str:
            return
        state["output_dir"] = Path(folder_str)
        out_dir_field.value = str(state["output_dir"])
        cfg["default_output_dir"] = str(state["output_dir"])
        save_config(cfg)
        page.update()

    # ---------- UI 组件 ----------
    file_count_text = ft.Text("已选 0 张", size=14, color=ft.Colors.GREY_700)
    file_grid = ft.GridView(
        expand=False, runs_count=4, max_extent=260, child_aspect_ratio=0.95,
        spacing=10, run_spacing=10, padding=10,
    )

    def clear_files(e):
        state["files"].clear()
        update_file_grid()
        update_preview()
        page.update()

    def add_more_files(e):
        page.run_task(do_pick_files)

    def add_folder(e):
        page.run_task(do_pick_folder)

    def change_output_dir(e):
        page.run_task(do_pick_output_dir)

    # ---------- 预设按钮组 (SegmentedButton) ----------
    def on_preset_change(e):
        sel = e.control.selected or []
        for label in sel:
            if label in PRESETS:
                state["selected_preset"] = label
                break
        update_preview()
        cfg["default_preset"] = state["selected_preset"]
        save_config(cfg)
        page.update()

    preset_icons = {
        "🎯 无损压缩": ft.Icons.IMAGE,
        "💎 极致保真": ft.Icons.DIAMOND,
        "⚡ 推荐压缩": ft.Icons.BOLT,
        "💾 压最小":   ft.Icons.COMPRESS,
        "🛒 亚马逊主图": ft.Icons.SHOPPING_CART,
    }
    preset_segments = [
        ft.Segment(
            value=name,
            label=ft.Text(name, size=11),
            icon=preset_icons.get(name, ft.Icons.IMAGE),
        )
        for name in PRESETS
    ]

    preset_keys = list(PRESETS.keys())
    initial_idx = preset_keys.index(state["selected_preset"]) \
        if state["selected_preset"] in preset_keys else 2
    preset_seg = ft.SegmentedButton(
        segments=preset_segments,
        selected=[preset_keys[initial_idx]],
        on_change=on_preset_change,
        show_selected_icon=False,
    )

    # ---------- 实时预览 ----------
    preview_card_content = ft.Column([], spacing=4)

    def update_preview():
        preview_card_content.controls.clear()
        if not state["files"]:
            preview_card_content.controls.append(
                ft.Text("(选图后会显示预估)", color=ft.Colors.GREY_500))
            return
        sample = state["files"][0]
        try:
            sz = preview_size(sample, state["selected_preset"])
            if sz is None:
                preview_card_content.controls.append(ft.Text("预览失败", color=ft.Colors.RED))
                return
            src_b = sample.stat().st_size
            diff = src_b - sz
            pct = (diff / src_b * 100) if src_b else 0
            arrow = "↓ 省" if diff > 0 else ("↑ 增" if diff < 0 else "= 原")
            preview_card_content.controls.append(
                ft.Text(sample.name, size=12, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            )
            preview_card_content.controls.append(
                ft.Text(f"原: {human_size(src_b)}", size=12),
            )
            preview_card_content.controls.append(
                ft.Text(f"压后: {human_size(sz)}", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
            )
            color = ft.Colors.GREEN if diff > 0 else (ft.Colors.RED if diff < 0 else ft.Colors.GREY)
            preview_card_content.controls.append(
                ft.Text(f"{arrow} {human_size(abs(diff))} ({pct:+.1f}%)", size=13, color=color),
            )
        except Exception as ex:
            preview_card_content.controls.append(ft.Text(f"预览错误: {ex}", color=ft.Colors.RED))

    def update_file_grid():
        file_grid.controls.clear()
        file_count_text.value = f"已选 {len(state['files'])} 张"
        for p in state["files"]:
            try:
                size_str = human_size(p.stat().st_size)
            except OSError:
                size_str = "?"
            file_grid.controls.append(
                ft.Card(
                    content=ft.Container(
                        content=ft.Column([
                            ft.Container(
                                content=ft.Image(
                                    src=str(p),
                                    width=240, height=160, fit=ft.ImageFit.CONTAIN,
                                    gapless_playback=False,
                                    error_content=ft.Icon(ft.Icons.BROKEN_IMAGE),
                                ),
                                alignment=ft.alignment.center,
                                bgcolor=ft.Colors.GREY_100,
                                border_radius=8,
                                height=170,
                            ),
                            ft.Text(p.name, size=12, weight=ft.FontWeight.BOLD,
                                     max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(size_str, size=11, color=ft.Colors.GREY_700),
                        ], spacing=4),
                        padding=8,
                    ),
                ),
            )

    # ---------- 输出目录 ----------
    out_dir_field = ft.TextField(
        value=str(state["output_dir"]),
        read_only=True, dense=True, expand=True,
        text_style=ft.TextStyle(size=12),
    )

    # ---------- 进度 + 日志 ----------
    progress_bar = ft.ProgressBar(width=400, visible=False)
    progress_text = ft.Text("", size=12, color=ft.Colors.GREY_700)
    log_text = ft.Text(spans=[], selectable=True)

    def append_log(line: str, color=None):
        log_text.spans.append(
            ft.TextSpan(line + "\n",
                        ft.TextStyle(size=12, color=color or ft.Colors.GREY_900))
        )
        page.update()

    # ---------- 开始压缩 ----------
    async def start_compress(e):
        if state["running"]:
            return
        if not state["files"]:
            snack("请先选图", error=True)
            return
        state["running"] = True
        progress_bar.visible = True
        progress_bar.value = 0
        progress_text.value = f"0 / {len(state['files'])}"
        start_btn.disabled = True
        page.update()

        results = []
        total = len(state["files"])

        def on_prog(done, total_, latest):
            results.append(latest)
            results.sort(key=lambda r: str(r["src"]))
            progress_bar.value = done / total_
            progress_text.value = f"{done} / {total_}"
            status = latest["status"]
            color = (ft.Colors.GREEN if status == "ok"
                     else ft.Colors.ORANGE if status in ("kept_original", "no_exif_to_strip")
                     else ft.Colors.RED)
            append_log(
                f"[{done}/{total_}] {latest['src'].name} → {status} "
                f"({human_size(latest['src_bytes'])} → {human_size(latest['out_bytes'])})",
                color,
            )

        state["results"] = batch_compress(
            state["files"], state["selected_preset"], state["output_dir"],
            max_workers=min(4, len(state["files"])),
            on_progress=on_prog,
        )

        ok = sum(1 for r in state["results"] if r["status"] == "ok")
        skip = sum(1 for r in state["results"] if r["status"] in ("kept_original", "no_exif_to_strip", "skipped_small", "skipped_exists"))
        fail = sum(1 for r in state["results"] if r["status"].startswith("failed"))
        saved = sum(max(0, r["saved_bytes"]) for r in state["results"])

        append_log(
            f"\n=== 完成 === 成功 {ok}, 跳过/保留原图 {skip}, 失败 {fail}, 共省 {human_size(saved)}",
            ft.Colors.BLUE,
        )
        progress_bar.visible = False
        progress_text.value = f"共 {total} 张: 成功 {ok}, 跳过 {skip}, 失败 {fail}, 省 {human_size(saved)}"
        state["running"] = False
        start_btn.disabled = False
        page.update()

    start_btn = ft.FilledButton(
        "▶  开始压缩",
        style=ft.ButtonStyle(
            padding=ft.Padding(left=24, top=14, right=24, bottom=14),
            shape=ft.RoundedRectangleBorder(radius=8),
            bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE,
        ),
        on_click=start_compress,
    )

    # ---------- 布局 ----------
    top_bar = ft.Container(
        content=ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.COMPRESS, size=22, color=ft.Colors.BLUE),
                ft.Text("图片一键压缩", size=18, weight=ft.FontWeight.BOLD),
            ], spacing=8),
            ft.Container(expand=True),
            ft.OutlinedButton("选文件", icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                              on_click=lambda e: page.run_task(do_pick_files)),
            ft.OutlinedButton("选文件夹", icon=ft.Icons.FOLDER_OPEN,
                              on_click=add_folder),
            ft.OutlinedButton("清空", icon=ft.Icons.DELETE_OUTLINE, on_click=clear_files),
        ], spacing=8),
        padding=ft.Padding(left=20, top=12, right=20, bottom=12),
        bgcolor=ft.Colors.WHITE,
        border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.GREY_300)),
    )

    def open_settings(e):
        out_dir_field.value = str(state["output_dir"])
        settings_dialog.open = True
        page.update()

    def save_settings(e):
        state["output_dir"] = Path(out_dir_field.value)
        cfg["default_output_dir"] = str(state["output_dir"])
        cfg["default_preset"] = state["selected_preset"]
        save_config(cfg)
        settings_dialog.open = False
        page.update()

    settings_dialog = ft.AlertDialog(
        title=ft.Text("设置"),
        content=ft.Column([
            ft.Text("默认输出目录:"),
            ft.Row([out_dir_field, ft.IconButton(ft.Icons.FOLDER_OPEN, on_click=change_output_dir)]),
            ft.Text(f"配置文件: {CONFIG_PATH}", size=10, color=ft.Colors.GREY_600),
        ], tight=True, width=400),
        actions=[
            ft.TextButton("取消", on_click=lambda e: page.close(settings_dialog)),
            ft.FilledButton("保存", on_click=save_settings),
        ],
    )

    def create_desktop_shortcut(e):
        """在用户桌面创建 .lnk 快捷方式."""
        try:
            import subprocess
            desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
            if not desktop.exists():
                desktop = Path.home() / "Desktop"
            lnk = desktop / "图片一键压缩.lnk"
            target = Path(__file__).resolve()
            py_exe = Path(r"C:\Python311\pythonw.exe")
            if not py_exe.exists():
                py_exe = Path(r"C:\Python311\python.exe")
            # 用 PowerShell 创建 .lnk (不依赖 pywin32), 指向具体 Python 防止调到 3.14
            ps = (
                f'$ws = New-Object -ComObject WScript.Shell; '
                f'$s = $ws.CreateShortcut("{lnk}"); '
                f'$s.TargetPath = "{py_exe}"; '
                f'$s.Arguments = "compress_images_flet.py"; '
                f'$s.WorkingDirectory = "{target.parent}"; '
                f'$s.IconLocation = "{py_exe},0"; '
                f'$s.WindowStyle = 1; '
                f'$s.Description = "图片一键压缩 (Flet)"; '
                f'$s.Save()'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                check=True, capture_output=True, creationflags=0x08000000,
            )
            snack(f"桌面图标已创建: {lnk}")
        except Exception as ex:
            snack(f"创建失败: {ex}", error=True)
        page.update()

    app_bar = ft.AppBar(
        title=ft.Text("图片一键压缩 v5"),
        actions=[
            ft.IconButton(ft.Icons.SETTINGS, tooltip="设置", on_click=open_settings),
            ft.IconButton(ft.Icons.LINK, tooltip="桌面快捷方式", on_click=create_desktop_shortcut),
        ],
        bgcolor=ft.Colors.WHITE,
        elevation=1,
    )

    left_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                preset_seg,
                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.GREY_500),
            ], spacing=10),
            ft.Container(height=10),
            ft.Card(
                content=ft.Container(
                    content=ft.Column([preview_card_content], spacing=4),
                    padding=12, width=380,
                ),
            ),
            ft.Container(height=10),
            preview_card_content_stub := ft.Column(),   # 占位, 不显示
            ft.Container(
                content=ft.Row([
                    start_btn,
                    ft.Container(width=20),
                    ft.Column([progress_bar, progress_text], spacing=4, expand=True),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(left=10, top=10, right=10, bottom=10),
            ),
            ft.Container(
                content=ft.Column([
                    ft.Text("处理日志", size=12, color=ft.Colors.GREY_700, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Column([log_text], scroll=ft.ScrollMode.AUTO),
                        height=180,
                        border=ft.Border.all(1, ft.Colors.GREY_300),
                        border_radius=6,
                        bgcolor=ft.Colors.GREY_50,
                        padding=8,
                    ),
                ], spacing=4),
                padding=ft.Padding(left=10, top=10, right=10, bottom=10),
            ),
        ], spacing=10, expand=True),
        padding=10, width=420,
    )

    right_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                file_count_text,
                ft.Container(expand=True),
                ft.OutlinedButton("+ 加图", icon=ft.Icons.ADD, on_click=add_more_files),
            ]),
            ft.Container(
                content=ft.Column([file_grid], scroll=ft.ScrollMode.AUTO, expand=True),
                expand=True,
                bgcolor=ft.Colors.WHITE,
                border_radius=8,
                border=ft.Border.all(1, ft.Colors.GREY_200),
            ),
        ], spacing=8, expand=True),
        padding=10, expand=True,
    )

    page.add(
        app_bar,
        ft.Container(
            content=ft.Row([
                ft.Container(content=left_panel, bgcolor=ft.Colors.GREY_50, width=440),
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                ft.Container(content=right_panel, expand=True, bgcolor=ft.Colors.WHITE),
            ], expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
            expand=True,
        ),
    )
    page.update()

    update_file_grid()
    update_preview()


if __name__ == "__main__":
    # flet 1.0+ 强制走 Flet App 渲染（不依赖 WebView2 / Edge）
    ft.run(main, view=ft.AppView.FLET_APP)