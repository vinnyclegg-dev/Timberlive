; TimberLive installer (Inno Setup 6). Built by packaging/build.py, which passes:
;   /DStage=<packaging\stage\TimberLive>  /DAppVersion=<timberlive_app.__version__>
; Per-user install: no admin prompt, and the folder stays writable (it is also the AI's workspace).

#ifndef Stage
  #define Stage "stage\TimberLive"
#endif
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C0B6A52-2F7E-4C55-9D1B-7B3E1A4F2C11}
AppName=TimberLive
AppVersion={#AppVersion}
AppPublisher=TimberLive
DefaultDirName={localappdata}\Programs\TimberLive
DefaultGroupName=TimberLive
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=TimberLive-Setup-{#AppVersion}
SetupIconFile={#Stage}\app\timberlive_app\ui\icon.ico
UninstallDisplayIcon={app}\app\timberlive_app\ui\icon.ico
UninstallDisplayName=TimberLive
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The AI writes to these as it plays, so an update never overwrites them.
Source: "{#Stage}\*"; DestDir: "{app}"; Excludes: "\knowledge\goals.md,\knowledge\08-lessons-next-playthrough.md"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Stage}\knowledge\goals.md"; DestDir: "{app}\knowledge"; Flags: onlyifdoesntexist
Source: "{#Stage}\knowledge\08-lessons-next-playthrough.md"; DestDir: "{app}\knowledge"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\TimberLive"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m timberlive_app"; WorkingDir: "{app}"; IconFilename: "{app}\app\timberlive_app\ui\icon.ico"; AppUserModelID: "TimberLive.App"
Name: "{group}\TimberLive workspace"; Filename: "{app}"
Name: "{autodesktop}\TimberLive"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m timberlive_app"; WorkingDir: "{app}"; IconFilename: "{app}\app\timberlive_app\ui\icon.ico"; AppUserModelID: "TimberLive.App"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m timberlive_app"; WorkingDir: "{app}"; Description: "Open TimberLive"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the app's services (Foreman, overlay, poll counter) so their files can be removed.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -Command ""Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -like '{app}\runtime\*' } | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }"""; Flags: runhidden; RunOnceId: "StopTimberLive"

[UninstallDelete]
; Everything the app and the AI wrote in the workspace (checkpoints, caches, logs, MCP config).
; Settings in %LOCALAPPDATA%\TimberLive and the mod in Documents\Timberborn\Mods are kept.
Type: filesandordirs; Name: "{app}"
