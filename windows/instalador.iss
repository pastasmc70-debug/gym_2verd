; Instalador con Inno Setup 6 ("Siguiente, Siguiente, Finalizar").
; Compilar (después de PyInstaller):  ISCC.exe /DAppVersion=1.0.0 windows\instalador.iss
; Resultado: windows\Salida\GestionGimnasio-Instalador-<versión>.exe
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
; Este AppId no se cambia nunca: es lo que hace que un instalador nuevo ACTUALICE el programa en lugar de duplicarlo.
AppId={{6D1F7B3A-52C8-4E0B-9A37-C4E81B2F9D05}
AppName=Gestión de Gimnasio
AppVersion={#AppVersion}
AppVerName=Gestión de Gimnasio {#AppVersion}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\Gestion de Gimnasio
DefaultGroupName=Gestión de Gimnasio
UninstallDisplayIcon={app}\GestionGimnasio.exe
SetupIconFile=icono.ico
OutputDir=Salida
OutputBaseFilename=GestionGimnasio-Instalador-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\GestionGimnasio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; La carpeta de DATOS (base, fotos, copias, registros) queda aparte del programa. Todos los usuarios de la PC pueden
; escribir en ella, y "uninsneveruninstall" hace que el desinstalador NUNCA la borre.
Name: "{commonappdata}\GestionGimnasio"; Permissions: users-modify; Flags: uninsneveruninstall

[Icons]
Name: "{group}\Gestión de Gimnasio"; Filename: "{app}\GestionGimnasio.exe"
Name: "{group}\Desinstalar Gestión de Gimnasio"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Gestión de Gimnasio"; Filename: "{app}\GestionGimnasio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GestionGimnasio.exe"; Description: "Abrir Gestión de Gimnasio"; Flags: nowait postinstall skipifsilent

; Nota: no hay sección [UninstallDelete] para los datos a propósito.

[Code]
function WebView2Instalado(): Boolean;
var
  version: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', version) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', version);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not WebView2Instalado() then
    MsgBox('Este equipo no tiene "Microsoft Edge WebView2 Runtime", que el programa usa para mostrar la ventana. ' +
           'Descargalo gratis desde microsoft.com (buscá "WebView2 Runtime") e instalalo antes de abrir el programa.',
           mbInformation, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    MsgBox('Se desinstaló el programa. Tus datos (socios, pagos, fotos y copias) NO se borraron: siguen en ' +
           ExpandConstant('{commonappdata}\GestionGimnasio') + '. Si instalás de nuevo, los vas a encontrar.',
           mbInformation, MB_OK);
end;
