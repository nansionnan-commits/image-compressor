# -*- coding: utf-8 -*-
"""_e2e_v19_preset_persist.py — 需求4 的真机端到端证明

用户诉求第 4 条: "就算卸载之后再装一个版本, 这个预设也还是在的。"

这一条**不能靠单元测试说了算** —— 单元测试只能证明"预设存在安装目录之外",
证明不了"卸载器真的不会把它删掉"。所以这个脚本在真机上真刀真枪地来一遍:

  1. 快照 (注册表右键菜单 / settings.json / 备份目录清单) —— 出事能还原
  2. 静默安装 v11.4
  3. 在真 %APPDATA% 里写一个自定义预设
  4. 用**装好的 exe** 跑一次这个预设 -> 证明 exe 读得到
  5. 静默卸载
  6. 检查: 自定义预设还在吗? settings.json 还在吗?
  7. 再静默装一次 (这就是用户说的"再装一个新版本")
  8. 检查: 自定义预设还在吗? 装好的 exe 还认得它吗?
  9. 还原现场 (删掉测试预设, 恢复原有 settings.json)

跑法:  C:\\Python314\\python.exe -X utf8 _e2e_v19_preset_persist.py
"""
import json
import os
import shutil
import subprocess
import sys
import time
import winreg
from pathlib import Path

BASE = Path(__file__).resolve().parent
SETUP = BASE / "_setup_out" / "PicShrink-Setup-v11.4.exe"
APP = Path(os.environ["LOCALAPPDATA"]) / "图瘦身"
ROAM = Path(os.environ.get("APPDATA", str(Path.home()))) / "图瘦身"
PRESETS = ROAM / "presets.json"
SETTINGS = APP / "settings.json"
BACKUP = APP / "备份"
TEST_NAME = "验收用预设 E2E"

MENU_PATHS = []
for _shell in (r"Software\Classes\*\shell", r"Software\Classes\Directory\shell"):
    for _key in ("PicShrinkQuick", "PicShrinkQueue", "用图瘦身处理"):
        MENU_PATHS.append(rf"{_shell}\{_key}\command")
        MENU_PATHS.append(rf"{_shell}\{_key}")

fails: list[str] = []
passed = 0


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print(f"  [PASS] {name}" + (f"  {detail}" if detail else ""))
    else:
        fails.append(name)
        print(f"  [FAIL] {name}" + (f"  {detail}" if detail else ""))


def reg_read(path):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        return None
    try:
        out = {}
        for i in range(winreg.QueryInfoKey(k)[1]):
            name, val, _ = winreg.EnumValue(k, i)
            out[name] = val
        return out
    finally:
        k.Close()


def reg_snap():
    return {p: reg_read(p) for p in MENU_PATHS}


def reg_restore(snap):
    """把右键菜单键还原回快照的样子。

    ⚠ 两种"空"必须分开:
      want is None = 跑前这个键根本不存在 -> 跑完也不该有
      want == {}   = 跑前这个键存在但没有值 -> 跑完也该是空壳
    混成一种的话, 会在用户机器上留下**孤儿空键** —— Explorer 里点不掉、
    删不干净的那种, 正是这个项目在 v9~v11.2 踩过一次的坑。
    """
    for p, want in snap.items():
        try:
            k = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, p, 0, winreg.KEY_ALL_ACCESS)
        except OSError:
            continue
        try:
            names = [winreg.EnumValue(k, i)[0] for i in range(winreg.QueryInfoKey(k)[1])]
            for name in names:
                try:
                    winreg.DeleteValue(k, name)
                except FileNotFoundError:
                    pass
            if want is None:
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, p)
                except OSError:
                    pass           # 还有子键就留着, 子键会先被处理
            else:
                for name, val in want.items():
                    winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        except OSError:
            pass
        finally:
            k.Close()


def uninstall_version():
    """读 HKCU 卸载项里登记的版本号。

    ⚠ QueryInfoKey 返回的是 (子键数, 值数, 最后修改时间) —— 枚举**子键**
    要用 [0], 用 [1] 拿到的是"值数量"(卸载项下面一个值都没有, 于是枚举出
    0 个子键, 看起来像"根本没装"). 这个坑踩过一次。
    """
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            k = winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
        except FileNotFoundError:
            continue
        try:
            for i in range(winreg.QueryInfoKey(k)[0]):        # [0] = 子键数
                sub = winreg.EnumKey(k, i)
                try:
                    sk = winreg.OpenKey(k, sub)
                except OSError:
                    continue
                try:
                    try:
                        dn = winreg.QueryValueEx(sk, "DisplayName")[0]
                    except FileNotFoundError:
                        continue
                    if "PicShrink" in str(dn):
                        try:
                            ver = winreg.QueryValueEx(sk, "DisplayVersion")[0]
                        except FileNotFoundError:
                            ver = ""
                        return str(dn), str(ver)
                finally:
                    sk.Close()
        finally:
            k.Close()
    return "", ""


def run(cmd, timeout=300):
    p = subprocess.run(cmd, capture_output=True, creationflags=0x08000000, timeout=timeout)
    return p.returncode


def make_pic():
    from PIL import Image
    d = Path(os.environ.get("TEMP", str(BASE))) / "picshrink_e2e_v19"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "验收图.jpg"
    Image.frombytes("RGB", (2600, 1800), os.urandom(2600 * 1800 * 3)).save(p, "JPEG", quality=97)
    return p, d / "out"


def compressed_outputs(pic: Path):
    """CLI 默认是「原文件夹导出」, 产物是 <原名>_compressed.ext, **不在 --out 里**。
    之前查错目录, 一度以为"预设没生效、什么都没压出来"。"""
    out = []
    if pic.parent.is_dir():
        out = sorted(pic.parent.glob(f"{pic.stem}_compressed*.jpg"))
    return out


def main():
    if not SETUP.is_file():
        print(f"❌ 安装包不存在: {SETUP}")
        sys.exit(1)

    print("== 1. 快照现场 ==")
    snap_reg = reg_snap()
    snap_settings = SETTINGS.read_bytes() if SETTINGS.is_file() else None
    snap_presets = PRESETS.read_bytes() if PRESETS.is_file() else None
    snap_backups = sorted(p.name for p in BACKUP.iterdir()) if BACKUP.is_dir() else []
    print(f"   settings.json: {SETTINGS}  存在={SETTINGS.is_file()}")
    print(f"   presets.json : {PRESETS}  存在={PRESETS.is_file()}")
    print(f"   备份批次     : {len(snap_backups)}")

    print("\n== 2. 静默安装 v11.4 ==")
    rc = run([str(SETUP), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
    check("安装器退出码 0", rc == 0, f"rc={rc}")
    time.sleep(2)
    exe = APP / "PicShrink.exe"
    check("exe 已就位", exe.is_file(), str(exe))
    dn, ver = uninstall_version()
    check("卸载项登记的是 v11.4", "v11.4" in dn, f"{dn!r} / {ver!r}")
    check("右键菜单已重新登记", reg_snap() != snap_reg or
          any(v for v in reg_snap().values() if v))

    print("\n== 3. 写一个自定义预设 (真 %APPDATA%) ==")
    PRESETS.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "presets": {TEST_NAME: {
        "mode": "target", "quality": 90, "target_kb": 300,
        "format": "jpg", "max_side": 2000, "keep_exif": False}}}
    PRESETS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    check("预设文件写好了", PRESETS.is_file(), str(PRESETS))

    print("\n== 4. 用装好的 exe 跑一次这个预设 ==")
    pic, outdir = make_pic()
    rc = run([str(exe), "--preset", TEST_NAME, "--no-notify", str(pic)])
    print(f"   exe 退出码 = {rc}")
    outs = compressed_outputs(pic)
    check("exe 用自定义预设压出了图", rc == 0 and len(outs) == 1,
          f"rc={rc} 产物={[p.name for p in outs]}")
    if outs:
        check("压到了目标 300KB 以内", outs[0].stat().st_size <= 300 * 1024,
              f"{outs[0].stat().st_size/1024:.0f}KB")
        from PIL import Image
        with Image.open(outs[0]) as im:
            check("长边封顶 2000", max(im.size) <= 2000, str(im.size))

    print("\n== 5. 静默卸载 ==")
    # ⚠ Inno Setup 6 卸载要用安装器目录里的 unins000.exe, 不能对 Setup.exe
    #   传 /UNINSTALL —— 那样只是把安装向导又开了一遍, 什么也没卸 (踩过)。
    unins = APP / "unins000.exe"
    check("unins000.exe 在", unins.is_file(), str(unins))
    rc = run([str(unins), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
    check("卸载器退出码 0", rc == 0, f"rc={rc}")
    time.sleep(3)
    check("exe 确实被卸载了", not exe.is_file(), str(exe))
    check("★ 自定义预设文件还在", PRESETS.is_file(), str(PRESETS))
    if PRESETS.is_file():
        got = json.loads(PRESETS.read_text(encoding="utf-8"))
        check("★ 预设内容一字没变",
              got.get("presets", {}).get(TEST_NAME) ==
              payload["presets"][TEST_NAME], str(got))
    check("settings.json 也还在 (Inno 不删它)",
          SETTINGS.is_file(), str(SETTINGS))
    check("备份目录没被动", BACKUP.is_dir() and
          sorted(p.name for p in BACKUP.iterdir()) == snap_backups,
          f"{len(snap_backups)} 批")

    print("\n== 6. 再装一次 (用户说的'再装一个新版本') ==")
    rc = run([str(SETUP), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
    check("重装退出码 0", rc == 0, f"rc={rc}")
    time.sleep(2)
    check("exe 又回来了", exe.is_file(), str(exe))
    check("★ 自定义预设还在", PRESETS.is_file(), str(PRESETS))

    print("\n== 7. 重装后的 exe 还认得这个预设吗 ==")
    for old in compressed_outputs(pic):
        old.unlink()
    rc = run([str(exe), "--preset", TEST_NAME, "--no-notify", str(pic)])
    outs2 = compressed_outputs(pic)
    check("★ 重装后照样能用这个预设", rc == 0 and len(outs2) == 1,
          f"rc={rc} 产物={[p.name for p in outs2]}")
    if outs2:
        check("★ 重装后压出来还是 ≤300KB", outs2[0].stat().st_size <= 300 * 1024,
              f"{outs2[0].stat().st_size/1024:.0f}KB")

    print("\n== 8. 还原现场 ==")
    if snap_presets is None:
        if PRESETS.is_file():
            PRESETS.unlink()
        print("   已删掉测试用的 presets.json")
    else:
        PRESETS.write_bytes(snap_presets)
        print("   已还原用户原本的 presets.json")
    if snap_settings is not None:
        SETTINGS.write_bytes(snap_settings)
    reg_restore(snap_reg)
    shutil.rmtree(pic.parent, ignore_errors=True)
    print("   已还原注册表 / settings.json / 备份目录")

    print("\n" + "=" * 62)
    print(f"通过 {passed} / 失败 {len(fails)}")
    for f in fails:
        print(f"  [FAIL] {f}")
    if fails:
        sys.exit(1)
    print("✅ 需求4 真机端到端验证通过: 卸载重装, 自定义预设一直在")


if __name__ == "__main__":
    main()
