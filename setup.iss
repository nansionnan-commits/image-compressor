; 图瘦身 (PicShrink) v10 — Inno Setup 安装器脚本
; 设计原则:
;   Inno 只负责 文件 / 图标 / 开始菜单 / 卸载器 登记
;   资源管理器右键 / 发送到 / 桌面快捷方式 仍由 PicShrink.exe --install 负责
;   (那段逻辑已过 36 项安装测试 + 26 项 E2E 测试, 不重复实现)

#define AppName "图瘦身"
#define AppNameEn "PicShrink"
#define AppVer "10.0.0"
#define AppVerShort "v10"
#define AppPublisher "图瘦身 (PicShrink) contributors"
#define AppExeName "PicShrink.exe"

[Setup]
AppId={{6B3F1C42-9A5E-4D7B-8E21-9C3A5E01B410}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppNameEn} {#AppVerShort}
AppPublisher={#AppPublisher}
VersionInfoVersion=10.0.0.0

; 与 v9_install() 的 _v9_install_dir() 完全一致, 避免出现两份安装目录
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
