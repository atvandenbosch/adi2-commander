; Inno Setup script for ADI-2 Commander, compiled by tools/build.py, which defines Version, NumericVersion, Folder
; (the program folder PyInstaller made), Wizard (the wizard's images), the taskbar identities and the descriptions of
; the shortcuts.
; Per user, without administrator rights: the program goes to %LOCALAPPDATA%\Programs\ADI-2 Commander.

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
PrivilegesRequired=lowest
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

[InstallDelete]
; An update replaces the program folder, so that no file of an older version stays behind.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\licenses"

[Registry]
; What the app remembers (QSettings), removed with it.
Root: HKCU; Subkey: "Software\ADI-2 Commander"; Flags: uninsdeletekey

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
