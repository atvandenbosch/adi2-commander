; Inno Setup script for ADI-2 Commander, compiled by tools/build.py, which defines Version, NumericVersion, Folder
; (the program folder PyInstaller made), Wizard (the wizard's images), the taskbar identities and the descriptions of
; the shortcuts.
; For all users, in Program Files, or for the current user only, in %LOCALAPPDATA%\Programs; an update keeps that
; choice.

#ifndef Version
  #error Compile with tools/build.py
#endif

[Setup]
; The same for every version, so that a new one replaces the old.
AppId={{BB1294AA-F19A-4351-9016-A90717F62522}
AppName=ADI-2 Commander
AppVersion={#Version}
AppPublisher=Alexander van den Bosch
AppCopyright=Copyright (C) 2026 Alexander van den Bosch
VersionInfoVersion={#NumericVersion}
PrivilegesRequired=admin
; A dialog offers both; Setup skips it when it finds an earlier installation and uses that one's mode.
PrivilegesRequiredOverridesAllowed=dialog
; [Registry] writes to HKCU only in an installation for the current user.
UsedUserAreasWarning=no
DefaultDirName={autopf}\ADI-2 Commander
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Qt 6 runs on Windows 10 1809 and later.
MinVersion=10.0.17763
OutputBaseFilename=ADI-2-Commander-{#Version}-setup
SetupIconFile=..\commander\ui\icon.ico
UninstallDisplayIcon={app}\Commander.exe
UninstallDisplayName=ADI-2 Commander
WizardStyle=modern
; The app's icon, in a size for each display scaling
WizardImageFile={#Wizard}\large-*.png
WizardSmallImageFile={#Wizard}\small-*.png
Compression=lzma2/max
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; The two modes as equal choices; all users stays preselected.
PrivilegesRequiredOverrideAllUsersRecommended=Install for &all users

[InstallDelete]
; An update replaces the program folder, so that no file of an older version stays behind. While Commander still runs,
; the folder stays: copying then stops at Commander.exe, the first file, and Cancel leaves the installed version whole.
Type: filesandordirs; Name: "{app}\_internal"; Check: not CommanderRunning
Type: filesandordirs; Name: "{app}\licenses"; Check: not CommanderRunning

[Registry]
; What the app remembers (QSettings), per user: removed with an installation for the current user only. The
; uninstaller of an installation for all users reaches one user's settings only, so it leaves them all.
Root: HKCU; Subkey: "Software\ADI-2 Commander"; Flags: uninsdeletekey; Check: not IsAdminInstallMode

[Files]
Source: "{#Folder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Each with the taskbar identity the app gives itself, so that a pinned shortcut and its window share one button.
Name: "{autoprograms}\ADI-2 Commander"; Filename: "{app}\Commander.exe"; Comment: "{#Description}"; \
    AppUserModelID: "{#AppId}"
Name: "{autoprograms}\ADI-2 Commander (simulated)"; Filename: "{app}\Commander.exe"; Parameters: "--simulate"; \
    IconFilename: "{app}\_internal\commander\ui\icon-simulated.ico"; Comment: "{#SimulatedDescription}"; \
    AppUserModelID: "{#SimulatedAppId}"

[Run]
Filename: "{app}\Commander.exe"; Description: "{cm:LaunchProgram,ADI-2 Commander}"; Flags: nowait postinstall skipifsilent

[Code]
const
  GENERIC_WRITE = $40000000;
  FILE_SHARE_READ = 1;
  FILE_SHARE_WRITE = 2;
  FILE_SHARE_DELETE = 4;
  OPEN_EXISTING = 3;
  INVALID_HANDLE_VALUE = -1;
  ERROR_SHARING_VIOLATION = 32;

function CreateFile(FileName: String; DesiredAccess, ShareMode, SecurityAttributes, CreationDisposition,
  FlagsAndAttributes: Cardinal; TemplateFile: THandle): THandle; external 'CreateFileW@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): BOOL; external 'CloseHandle@kernel32.dll stdcall';

// A running Commander keeps Commander.exe open, in any account or Windows session, also while it starts; Windows then
// refuses to open the file for writing.
function CommanderRunning: Boolean;
var
  Handle: THandle;
begin
  Handle := CreateFile(ExpandConstant('{app}\Commander.exe'), GENERIC_WRITE,
    FILE_SHARE_READ or FILE_SHARE_WRITE or FILE_SHARE_DELETE, 0, OPEN_EXISTING, 0, 0);
  Result := (Handle = INVALID_HANDLE_VALUE) and (DLLGetLastError = ERROR_SHARING_VIOLATION);
  if Handle <> INVALID_HANDLE_VALUE then
    CloseHandle(Handle);
end;

// Asks to close Commander until it is gone: OK looks again; False on Cancel.
function CommanderClosed(Message: TSetupMessageID): Boolean;
begin
  Result := True;
  while Result and CommanderRunning do
    Result := SuppressibleMsgBox(FmtMessage(SetupMessage(Message), ['{#SetupSetting("AppName")}']), mbError,
      MB_OKCANCEL, IDCANCEL) = IDOK;
end;

// Preparing to Install closes the Commanders it lists when the user agrees; with one in another Windows session it
// lists none. Otherwise the user closes them here, before anything is changed.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    if not (WizardForm.PreparingYesRadio.Visible and WizardForm.PreparingYesRadio.Checked) then
      if not CommanderClosed(msgSetupAppRunningError) then
        Abort;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usAppMutexCheck then
    if not CommanderClosed(msgUninstallAppRunningError) then
      Abort;
end;
