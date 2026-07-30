#define MyAppName "SDM - Smart Download Manager"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "ZPD8X"
#define MyAppExeName "SDM.exe"
#define SourceRoot "..\\.."
#define BuildRoot SourceRoot + "\\build\\windows"

[Setup]
AppId={{D50150CE-8D4B-4CB5-A41E-BC753C540200}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\\SDM
DefaultGroupName=SDM
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir={#SourceRoot}\\release
OutputBaseFilename=SDM_v2.0.0_Setup_x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\\SDM.exe
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#BuildRoot}\\SDM\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BuildRoot}\\native_host\\SDMNativeHost.exe"; DestDir: "{app}\\browser_host"; Flags: ignoreversion
Source: "{#SourceRoot}\\browser_extension\\*"; DestDir: "{app}\\browser_extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\\BROWSER_SETUP_AR.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\\Tools\\*"; DestDir: "{app}\\Tools"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{localappdata}\\SDM"
Name: "{localappdata}\\SDM\\NativeHost"

[Icons]
Name: "{autoprograms}\\SDM"; Filename: "{app}\\SDM.exe"
Name: "{autodesktop}\\SDM"; Filename: "{app}\\SDM.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "browserintegration"; Description: "Install Chrome and Edge browser integration"; GroupDescription: "Browser integration:"; Flags: checkedonce
Name: "launchapp"; Description: "Launch SDM after installation"; GroupDescription: "Finish:"; Flags: checkedonce

[Run]
Filename: "{app}\\SDM.exe"; Parameters: "--install-browser-host"; Description: "Install browser integration"; Flags: runhidden waituntilterminated; Tasks: browserintegration
Filename: "{app}\\SDM.exe"; Description: "Launch SDM"; Flags: nowait postinstall skipifsilent; Tasks: launchapp

[UninstallRun]
Filename: "{app}\\SDM.exe"; Parameters: "--uninstall-browser-host"; Flags: runhidden waituntilterminated skipifdoesntexist

[Registry]
Root: HKCU; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Run"; ValueType: string; ValueName: "SDM"; ValueData: """{app}\SDM.exe"" --capture-only"; Flags: uninsdeletevalue; Tasks: browserintegration

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
