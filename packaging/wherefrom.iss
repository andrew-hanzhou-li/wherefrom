; The Windows installer: wherefrom-setup.exe. Built by CI with Inno Setup:
;   pyinstaller packaging\wherefrom.spec --distpath dist\app      (the folder build)
;   iscc /DAppVersion=0.4.0 /DDistDir=dist\app\wherefrom /O<output folder> packaging\wherefrom.iss
;
; Per user, no admin rights. It installs the two programs, runs
; "wherefrom setup" (menu entry, start at sign-in, browser connection), then
; reads the browsers' download history and starts the watcher in the
; background. Uninstalling (Settings > Apps) undoes all of that and keeps the
; database of recorded downloads.

#ifndef AppVersion
  #error Pass the version: /DAppVersion=x.y.z
#endif
#ifndef DistDir
  #define DistDir "..\dist\app\wherefrom"
#endif

[Setup]
; Never change AppId: upgrades and the uninstall entry depend on it
AppId={{7C3BDB2F-EBD8-4BDC-A175-DB3BD43452B7}
AppName=wherefrom
AppVersion={#AppVersion}
AppVerName=wherefrom {#AppVersion}
AppPublisher=andrew-hanzhou-li
AppPublisherURL=https://github.com/andrew-hanzhou-li/wherefrom
AppSupportURL=https://github.com/andrew-hanzhou-li/wherefrom/issues
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\wherefrom
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=yes
CloseApplications=no
OutputBaseFilename=wherefrom-setup
SetupIconFile=wherefrom.ico
UninstallDisplayIcon={app}\wherefrom.exe
UninstallDisplayName=wherefrom
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[InstallDelete]
; The libraries are replaced as a whole, so an upgrade never mixes old and new ones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; The folder build: wherefrom.exe, wherefromw.exe and their shared _internal folder
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\wherefrom"; Filename: "{app}\wherefromw.exe"; Parameters: "app"; Comment: "Browse and search where your downloads came from"

[Run]
Filename: "{app}\wherefromw.exe"; Parameters: "app"; Description: "Open wherefrom"; Flags: postinstall nowait skipifsilent
Filename: "https://github.com/andrew-hanzhou-li/wherefrom#optional-the-browser-extension"; Description: "Show how to add the browser extension (optional)"; Flags: postinstall shellexec nowait skipifsilent unchecked

[UninstallDelete]
Type: files; Name: "{app}\setup.log"

[Code]
procedure StopWherefrom();
var
  ResultCode: Integer;
begin
  { The watcher, open windows, a terminal "wherefrom watch", the browser's
    helper: anything running from the old files would keep them locked.
    /F because the windowless program has no window to ask politely. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM wherefromw.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM wherefrom.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);  { let Windows release the files }
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopWherefrom();
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Exe, Quiet, LogFile: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  Exe := ExpandConstant('{app}\wherefrom.exe');
  Quiet := ExpandConstant('{app}\wherefromw.exe');
  LogFile := ExpandConstant('{app}\setup.log');
  WizardForm.StatusLabel.Caption := 'Adding the right-click menu entry and connecting your browsers...';
  { Fast steps only, so the installer never looks stuck; output goes to setup.log }
  if not Exec(ExpandConstant('{cmd}'), '/c ""' + Exe + '" setup --no-start --no-import > "' + LogFile + '" 2>&1"',
              ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    SuppressibleMsgBox('Part of the setup didn''t work. The details are in' + #13#10 + LogFile + #13#10#13#10 +
                       'You can try again later by running: wherefrom setup', mbError, MB_OK, IDOK);
  Log('wherefrom setup exit code: ' + IntToStr(ResultCode));
  { Reading the download history can take a while (every file is fingerprinted),
    so it runs in the background, next to the watcher }
  Exec(Quiet, 'import-browsers', ExpandConstant('{app}'), SW_HIDE, ewNoWait, ResultCode);
  Exec(Quiet, 'watch', ExpandConstant('{app}'), SW_HIDE, ewNoWait, ResultCode);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  Exe: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  StopWherefrom();
  Exe := ExpandConstant('{app}\wherefrom.exe');
  { Remove the menu entry, start at sign-in and the browser connection. The
    database of recorded downloads stays. }
  Exec(Exe, 'uninstall', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(Exe, 'browser remove', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1000);  { let Windows release the files before they are deleted }
end;
