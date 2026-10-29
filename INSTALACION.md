# Instalar el sistema del gimnasio en Windows

> **Lo más fácil: el instalador.** Si te pasaron el archivo `GestionGimnasio-Instalador-….exe`, hacé doble clic, tocá «Siguiente» hasta «Finalizar» y abrí «Gestión de Gimnasio» desde el escritorio: se abre en su propia ventana y te pide los datos del gimnasio la primera vez. Para actualizar, ejecutá el instalador nuevo (no pierde datos). Al desinstalar, tus datos **no** se borran. Cómo se arma ese instalador: ver `README.md`, sección «Instalador de Windows». *Todavía no se probó en una PC con Windows real.*
>
> Lo que sigue es la **instalación manual con Python**, para quien no tiene el instalador.

Tiempo: unos 15 minutos. No hace falta saber programar: solo copiar y pegar los comandos tal cual.

## 1. Instalar Python (una sola vez)
1. Entrá a **python.org/downloads** y bajá la versión más nueva (tiene que ser 3.11 o superior).
2. Abrí el instalador. **Tildá la casilla «Add python.exe to PATH»** (abajo de todo) y tocá **Install Now**.
3. Al terminar dice «Setup was successful». Cerrá la ventana.

## 2. Abrir la carpeta del sistema en PowerShell
1. Descomprimí `gimnasio.zip` (clic derecho → «Extraer todo»), por ejemplo en `C:\gimnasio`.
2. Entrá a la carpeta `gimnasio` hasta ver los archivos `run.py` y `README.md`.
3. Hacé clic en la barra de arriba del Explorador (donde dice la ruta), escribí `powershell` y apretá **Enter**.
   Se abre una **ventana azul o negra** con una línea que termina en `gimnasio>`. Esa es la que vas a usar.

## 3. Instalar el sistema (una sola vez)
Pegá estas líneas de a una (clic derecho pega en PowerShell) y apretá Enter después de cada una:
```
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
- Si tras la segunda dice que «la ejecución de scripts está deshabilitada», pegá `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, apretá Enter, escribí `S` y repetí la segunda línea.
- Cuando funciona, la línea empieza con **(.venv)**. La tercera línea tarda un minuto y termina con «Successfully installed…».

## 4. Elegir tu clave
1. Pegá `python crear_hash.py` y apretá Enter.
2. Escribí la clave que quieras (mínimo 10 caracteres) y Enter. **No se ve lo que escribís: es normal.** Repetila y Enter.
3. Aparece una línea larga que empieza con `GYM_ADMIN_PASSWORD_HASH='scrypt:…'`. **Copiá el texto largo que está entre las comillas simples** (sin las comillas).

## 5. Guardar la configuración (una sola vez)
Pegá estas tres líneas, cambiando lo que está entre `<` y `>`. En la tercera línea, pegá el texto largo del paso anterior entre comillas simples:
```
setx GYM_SECRET_KEY "<inventá-un-texto-largo-sin-espacios-de-40-letras-y-números>"
setx GYM_ADMIN_USER "admin"
setx GYM_ADMIN_PASSWORD_HASH '<el hash que copiaste>'
setx GYM_NOMBRE "Gimnasio Don Juan"
```
Cada una responde **«CORRECTO: se guardó el valor especificado»**. Después **cerrá la ventana azul y repetí el paso 2** (abrir PowerShell en la carpeta) y escribí `.venv\Scripts\Activate.ps1` otra vez. Hace falta para que tome los valores.

## 6. Arrancar
```
python run.py
```
Tiene que quedar la ventana sin cerrarse y sin mensajes de error. Abrí el navegador en **http://127.0.0.1:5000**: aparece la pantalla **«Iniciar sesión»** con el nombre de tu gimnasio. Entrá con `admin` y la clave del paso 4. Se ve el **Panel** con el menú arriba (Socios, Planes, Pagos, Asistencia…).

La base de datos se crea sola. **Mientras la ventana de PowerShell esté abierta, el sistema funciona.** Para apagarlo: `Ctrl + C`.

## Cada día
Abrí PowerShell en la carpeta (paso 2), escribí `.venv\Scripts\Activate.ps1`, luego `python run.py` y abrí el navegador.

## Primeros pasos y cuidados
- Creá primero los **Planes**, después los **Socios** (o importalos desde *Datos → Importar*).
- Para probar con datos inventados antes de usarlo de verdad: `python seed.py --reset` (**borra todo**, usalo solo al principio).
- **Copia de seguridad:** *Datos → Descargar copia de seguridad*. Hacela seguido y guardala fuera de esta computadora (pendrive o nube).

## Si algo falla
- «py no se reconoce»: reinstalá Python y no te olvides de tildar «Add python.exe to PATH».
- «No se pudo iniciar: Falta la variable GYM_ADMIN_…»: definiste solo una de las dos variables del administrador. Definí las dos (paso 5) o borrá ambas y usá el asistente de la primera vez, que aparece al abrir la app. Abrí una ventana nueva de PowerShell después de cambiar variables.
- La página no abre: fijate que la ventana de `python run.py` siga abierta.

> Esta guía **no pudo probarse en una PC con Windows real**; si algún paso no se ve como se describe, avisá en qué paso y qué dice la pantalla.
