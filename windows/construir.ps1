# Arma el instalador en una PC con Windows (lo mismo que hace GitHub Actions).
# Requisitos: Python 3.12 e Inno Setup 6 (https://jrsoftware.org/isinfo.php).
# Uso, desde la raíz del proyecto, en PowerShell:   .\windows\construir.ps1
$ErrorActionPreference = "Stop"
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements.txt -r windows\requirements-windows.txt
.\.venv-build\Scripts\python.exe -m pytest -q -o addopts=""
.\.venv-build\Scripts\pyinstaller.exe windows\gimnasio.spec --noconfirm
.\dist\GestionGimnasio\GestionGimnasio.exe --autocomprobar
$version = (.\.venv-build\Scripts\python.exe -c "from app.version import __version__; print(__version__)").Trim()
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
& $iscc "/DAppVersion=$version" windows\instalador.iss
Write-Host "Listo: windows\Salida\GestionGimnasio-Instalador-$version.exe"
