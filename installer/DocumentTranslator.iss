; Document Translator - Inno Setup 6 definition
; This file is compiled by scripts\build_release.ps1 with /D values.

#ifndef MyAppVersion
  #define MyAppVersion "1.3.0"
#endif
#ifndef SourceDir
  #error SourceDir must point to the verified Portable Full staging directory.
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\release"
#endif
#ifndef OutputBaseName
  #define OutputBaseName "DocumentTranslator-v1.3.0-Windows-Setup-Full"
#endif

#define MyAppName "Document Translator"
#define MyAppPublisher "Document Translator Contributors"
#define MyAppURL "https://github.com/WANG40929/engineering-document-translator"
#define MyAppExeName "DocumentTranslator.exe"

[Setup]
AppId={{57E46738-9460-4DE4-B3E8-65E00A68BAED}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\DocumentTranslator
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#ReleaseDir}
OutputBaseFilename={#OutputBaseName}
SetupIconFile=..\translator_app\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile={#SourceDir}\Legal\LICENSE.txt
InfoBeforeFile={#SourceDir}\ReadMe.txt
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupLogging=yes
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no
UsePreviousAppDir=yes
; Detect the Windows UI language every time. This avoids carrying forward a
; non-Chinese choice made with an older installer that did not offer Chinese.
UsePreviousLanguage=no
LanguageDetectionMethod=uilanguage
ChangesAssociations=no
ChangesEnvironment=no
DisableWelcomePage=no
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Layout-preserving document translation application
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (c) 2026

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Vendor the Inno Setup 6.5.0+ Simplified Chinese catalog with the project so
; every developer and CI build produces the same six-language installer.
; Default.isl is the forward-compatible fallback if a future Inno version adds
; messages that the translated catalog has not received yet.
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl,languages\ChineseSimplified.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\User Guide"; Filename: "{app}\ReadMe.html"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Python recreates bytecode and an empty BabelDOC database during use. These
; files are not in Inno's installed-file manifest, so explicitly remove only
; the bundled engine tree. User documents and app settings live elsewhere.
Type: filesandordirs; Name: "{app}\TranslationEngine"
