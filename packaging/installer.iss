#define AppVersion "0.1.0"
#define AppExe "FileHub.exe"
#define Owner "FileHub.Windows.v1"
#ifndef PayloadRoot
  #define PayloadRoot "..\dist\FileHub"
#endif

[Setup]
AppId={{E5C1A2EB-0E1D-46D8-9D39-1056D8661DD5}
AppName=FileHub
AppVersion={#AppVersion}
AppPublisher=FileHub
DefaultDirName={localappdata}\Programs\FileHub
DefaultGroupName=FileHub
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
OutputDir=..\dist\installer
OutputBaseFilename=FileHub-{#AppVersion}-windows-x64-setup
SetupIconFile=..\resources\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
AppMutex=Local\FileHub.Windows.v1.ProgramInUse
DisableProgramGroupPage=yes
DisableWelcomePage=no
UsePreviousAppDir=yes
UsePreviousTasks=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Messages]
SetupAppRunningError=请先从托盘退出 FileHub，等待正在进行的整理完成后重试。
UninstallAppRunningError=请先从托盘退出 FileHub，等待正在进行的整理完成后重试。

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked
Name: "contextmenu"; Description: "添加当前用户右键“送进项目…”（Windows 11 位于显示更多选项）"; Flags: unchecked
Name: "autostart"; Description: "登录后在托盘运行（未配置或暂停时不会整理）"; Flags: unchecked

[Files]
Source: "{#PayloadRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FileHub"; Filename: "{app}\{#AppExe}"
Name: "{group}\FileHub 演示（隔离示例）"; Filename: "{app}\{#AppExe}"; Parameters: "--demo"
Name: "{autodesktop}\FileHub"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

; No [Run]: installing/upgrading never starts normal state implicitly.
; No unconditional [Registry] deletion: preserve entries modified by others.
; No [UninstallDelete]: user state/projects are outside the program manifest.
[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

function ExePath: String;
begin
  Result := ExpandConstant('{app}\{#AppExe}');
end;

function MenuKey(Kind: String): String;
begin
  Result := 'Software\Classes\' + Kind + '\shell\FileHub.Send';
end;

function SendCommand: String;
begin
  Result := '"' + ExePath + '" --send "%1"';
end;

function StartupCommand: String;
begin
  Result := '"' + ExePath + '" --background';
end;

function OwnedMenu(Key: String): Boolean;
var Value: String;
begin
  Result := RegQueryStringValue(HKCU, Key, 'FileHubOwner', Value) and (Value = '{#Owner}');
end;

procedure DeleteMatching(Key, Name, Expected: String);
var Value: String;
begin
  if RegQueryStringValue(HKCU, Key, Name, Value) and (Value = Expected) then
    RegDeleteValue(HKCU, Key, Name);
end;

function MenuConflict(Key: String): Boolean;
var Current, Expected: String;
begin
  Result := False;
  if not RegKeyExists(HKCU, Key) then exit;
  if not OwnedMenu(Key) then begin Result := True; exit; end;
  if RegQueryStringValue(HKCU, Key + '\command', '', Current) then
    Result := not RegQueryStringValue(HKCU, Key, 'FileHubCommand', Expected) or
      (Current <> Expected) or (Current <> SendCommand);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Old: String;
begin
  Result := '';
  if WizardIsTaskSelected('contextmenu') and
     (MenuConflict(MenuKey('*')) or MenuConflict(MenuKey('Directory'))) then
    Result := '右键项已被其他程序占用或修改，请取消此选项后重试。';
  if WizardIsTaskSelected('autostart') and
     RegQueryStringValue(HKCU, RunKey, 'FileHub', Old) and (Old <> StartupCommand) then
    Result := '同名登录启动项不属于此安装，请取消此选项后重试。';
end;

procedure RegisterMenu(Key: String);
begin
  if MenuConflict(Key) then RaiseException('右键项所有权发生变化，已停止注册。');
  if not RegWriteStringValue(HKCU, Key, 'FileHubOwner', '{#Owner}') or
     not RegWriteStringValue(HKCU, Key, '', '送进项目…') or
     not RegWriteStringValue(HKCU, Key, 'MultiSelectModel', 'Player') or
     not RegWriteStringValue(HKCU, Key, 'FileHubCommand', SendCommand) or
     not RegWriteStringValue(HKCU, Key + '\command', '', SendCommand) then
    RaiseException('无法写入当前用户右键设置。');
end;

procedure RemoveMenu(Key: String);
var Expected, Current: String;
begin
  if not OwnedMenu(Key) then exit;
  // A changed executable/command belongs to another installation or actor.
  if not RegQueryStringValue(HKCU, Key, 'FileHubCommand', Expected) or
     (Expected <> SendCommand) then exit;
  if RegQueryStringValue(HKCU, Key + '\command', '', Current) and
     (Current <> Expected) then exit;
  DeleteMatching(Key + '\command', '', Expected);
  RegDeleteKeyIfEmpty(HKCU, Key + '\command');
  DeleteMatching(Key, '', '送进项目…');
  DeleteMatching(Key, 'MultiSelectModel', 'Player');
  DeleteMatching(Key, 'FileHubCommand', Expected);
  DeleteMatching(Key, 'FileHubOwner', '{#Owner}');
  RegDeleteKeyIfEmpty(HKCU, Key);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Old: String;
begin
  if CurStep <> ssPostInstall then exit;
  if WizardIsTaskSelected('contextmenu') then begin
    RegisterMenu(MenuKey('*'));
    RegisterMenu(MenuKey('Directory'));
  end else begin
    RemoveMenu(MenuKey('*'));
    RemoveMenu(MenuKey('Directory'));
  end;
  if WizardIsTaskSelected('autostart') then begin
    if RegQueryStringValue(HKCU, RunKey, 'FileHub', Old) and
       (Old <> StartupCommand) then RaiseException('登录启动项所有权发生变化。');
    if not RegWriteStringValue(HKCU, RunKey, 'FileHub', StartupCommand) then
      RaiseException('无法写入登录启动设置。');
  end else DeleteMatching(RunKey, 'FileHub', StartupCommand);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usUninstall then exit;
  RemoveMenu(MenuKey('*'));
  RemoveMenu(MenuKey('Directory'));
  DeleteMatching(RunKey, 'FileHub', StartupCommand);
end;
