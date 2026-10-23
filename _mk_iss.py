# -*- coding: utf-8 -*-
"""写 setup.iss (UTF-8 BOM, Inno Setup 6 需要)."""
from pathlib import Path

ISS = r'''; 图瘦身 (PicShrink) v11.3 — Inno Setup 安装器脚本
; 设计原则:
;   Inno 只负责 文件 / 图标 / 开始菜单 / 卸载器 登记
;   资源管理器右键 / 发送到 / 桌面快捷方式 仍由 PicShrink.exe --install 负责
;   (那段逻辑已过多轮安装 / E2E 回归, 不重复实现)

#define AppName "图瘦身"
#define AppNameEn "PicShrink"
#define AppVer "11.3.0"
#define AppVerShort "v11.3"
#define AppPublisher "图瘦身 (PicShrink) contributors"
#define AppExeName "PicShrink.exe"

[Setup]
AppId={{6B3F1C42-9A5E-4D7B-8E21-9C3A5E01B410}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppNameEn} {#AppVerShort}
AppPublisher={#AppPublisher}
VersionInfoVersion=11.3.0.0

; 与 v9_install() 的 _v9_install_dir() 完全一致, 避免出现两份安装目录
; UsePreviousAppDir=no 是 v11 实测踩出来的坑:
;   Inno 默认会用 HKCU 卸载项里记的 InstallLocation 覆盖 DefaultDirName,
;   一旦历史装到过别的盘 (比如 D:\图瘦身), {app} 就跟 %LOCALAPPDATA%\图瘦身 分家,
;   结果磁盘上留两份 PicShrink.exe, 而右键菜单只指向 --install 复制的 LOCALAPPDATA 那份.
;   禁掉记忆, 强制回到默认目录, {app} 恒等于 LOCALAPPDATA, exe 全程只有一份.
UsePreviousAppDir=no
DefaultDirName={localappdata}\图瘦身
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName} ({#AppNameEn}) {#AppVerShort}
UninstallDisplayIcon={app}\app.ico

OutputDir=_setup_out
OutputBaseFilename=PicShrink-Setup-{#AppVerShort}
SetupIconFile=app.ico
WizardStyle=modern

; 免管理员: 和 v9 一样只写 HKCU
PrivilegesRequired=lowest

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

Compression=lzma2/max
SolidCompression=yes
SetupLogging=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\PicShrink.exe";   DestDir: "{app}"; Flags: ignoreversion
Source: "app.ico";              DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall.bat";        DestDir: "{app}"; Flags: ignoreversion
Source: "README.md";            DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "LICENSE";              DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 用 userdesktop 不是 autodesktop — 免管理员模式下 autodesktop 指向公共桌面
Name: "{userdesktop}\图瘦身"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\app.ico"; Comment: "打开图瘦身图形界面"
Name: "{group}\图瘦身";       Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\app.ico"
Name: "{group}\{cm:UninstallProgram,图瘦身}"; Filename: "{uninstallexe}"

[Run]
; 装完调 --install --quiet: 写 HKCU 右键菜单 + 发送到 + 桌面快捷方式
; (v9_install 在 quiet 下不弹窗; exe 就是 {app} 里那份, 自复制会跳过)
Filename: "{app}\{#AppExeName}"; Parameters: "--install --quiet"; Flags: runhidden waituntilterminated; StatusMsg: "正在配置资源管理器右键菜单..."

[UninstallRun]
; 卸载前先让 exe 自己清 HKCU / 发送到 / 桌面快捷方式
; quiet=True 时它保留安装目录, 由 Inno 自己删 — 正好分工
Filename: "{app}\{#AppExeName}"; Parameters: "--uninstall --quiet"; Flags: runhidden waituntilterminated; RunOnceId: "CleanShellIntegration"
'''

p = Path(__file__).with_name('setup.iss')
p.write_bytes(ISS.encode('utf-8-sig'))
print('setup.iss written:', p, p.stat().st_size, 'bytes')
print('BOM:', p.read_bytes()[:3] == b'\xef\xbb\xbf')