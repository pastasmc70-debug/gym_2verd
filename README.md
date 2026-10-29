# Gestión de gimnasio

Sistema web para gimnasios chicos: socios, planes, membresías, pagos (con parciales y anulaciones), asistencia, modo kiosco para la puerta, alertas de cobranza por WhatsApp, caja diaria, tienda opcional, importación y exportación CSV y copias de seguridad. Dos roles (administrador y recepción), sin registro público.

> **Esto es solo software: no abre molinetes ni puertas físicas.** El modo kiosco muestra una pantalla verde o roja; conectarla a un molinete requiere hardware aparte que este sistema no incluye.

Para instalar en Windows sin conocimientos técnicos mirá [INSTALACION.md](INSTALACION.md).

Python 3.11+ · Flask · SQLite · Jinja2 · Bootstrap (por CDN, hace falta internet en el navegador).

## Instalación

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt     # para producción alcanza con requirements.txt
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Si PowerShell dice que «la ejecución de scripts está deshabilitada», habilitala solo para esta ventana con `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y volvé a correr `Activate.ps1`.

## Primera vez: asistente de configuración

Si no hay administrador (ni por variables de entorno ni guardado), al abrir la app en el navegador aparece un asistente de 4 pasos: (1) nombre del gimnasio, (2) usuario y clave del administrador (mínimo 10 caracteres, con confirmación), (3) planes con precio y duración, (4) activar o no la tienda de suplementos. No hace falta tocar variables de entorno.

- La clave secreta de las sesiones se genera sola y se guarda en el archivo `secret_key` de la carpeta de la base (nadie la ve ni la escribe). **Incluila en las copias de la carpeta de datos**; si se pierde, se genera otra y solo se cierran las sesiones abiertas.
- El asistente se puede usar una sola vez: con un administrador creado ya no se puede repetir.
- Hacelo apenas instales: mientras no exista administrador, cualquiera que llegue a la app puede completarlo. Por defecto la app solo escucha en la propia computadora.
- La clave del administrador no se puede recuperar desde la pantalla (todavía no hay pantalla de cambio de clave).

### Pantalla «Configuración» (administrador)

Nombre del gimnasio, tienda, reglas de ingreso (acceso sin pago, reingreso, tope semanal de clases) y kiosco (sonido, teclado en pantalla y su clave) se cambian desde **Configuración** y se guardan en la base. Orden de prioridad: lo guardado en la pantalla, después la variable de entorno `GYM_*` y por último el valor por defecto. Las variables de entorno siguen funcionando como alternativa. Quedan solo por variable de entorno: días de alerta, rutas, cookie segura y los límites del kiosco.

## Configuración por variables de entorno (alternativa)

Si preferís no usar el asistente, definí el administrador con estas variables (si solo definís una de las dos, la app no arranca). Con ellas el asistente no aparece. Sin `GYM_SECRET_KEY` la clave secreta se genera sola. La clave **no** se guarda en texto plano: se guarda su hash.

1. Generá el hash de la clave de administrador (te la pide por teclado):

   ```bash
   python crear_hash.py
   ```

2. Generá la clave secreta de las sesiones:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

3. Cargá las variables. Los valores con `$` (como el hash) van entre **comillas simples**.

   Linux / macOS:

   ```bash
   export GYM_SECRET_KEY='<la clave secreta del paso 2>'
   export GYM_ADMIN_USER='admin'
   export GYM_ADMIN_PASSWORD_HASH='<el hash del paso 1>'
   export GYM_NOMBRE='Gimnasio Don Juan'      # opcional, aparece en pantalla y en los mensajes de WhatsApp
   ```

   Windows (PowerShell):

   ```powershell
   $env:GYM_SECRET_KEY = '<la clave secreta del paso 2>'
   $env:GYM_ADMIN_USER = 'admin'
   $env:GYM_ADMIN_PASSWORD_HASH = '<el hash del paso 1>'
   $env:GYM_NOMBRE = 'Gimnasio Don Juan'
   ```

### Variables opcionales

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `GYM_NOMBRE` | Mi Gimnasio | (también en Configuración) Nombre en pantalla y en los mensajes de WhatsApp |
| `GYM_DIAS_ALERTA` | 7 | Días de aviso antes del vencimiento |
| `GYM_DB_PATH` | `instance/gimnasio.db` | Ruta de la base |
| `GYM_UPLOAD_DIR` | `instance/fotos` | Carpeta de fotos |
| `GYM_IMPORT_DIR` | `instance/importaciones` | Archivos temporales de la vista previa de importación |
| `GYM_COOKIE_SECURE` | apagado | `1` cuando lo sirvas por HTTPS |
| `GYM_RECEPCION_USER` / `GYM_RECEPCION_PASSWORD_HASH` | sin recepción | Opcional y solo de compatibilidad: si están, se importan **una vez** como la primera cuenta de recepción de la base (hash con `python crear_hash.py recepcion`). Después las cuentas se manejan desde *Usuarios* |
| `GYM_ACCESO_SIN_PAGO` | `0` | `1` permite ingresar a quien tiene el plan asignado pero todavía no pagó el período inicial |
| `GYM_PERMITIR_REINGRESO` | `0` | `1` permite registrar más de un ingreso por día |
| `GYM_LIMITAR_CLASES_SEMANA` | `1` | Rechaza el ingreso cuando se agotaron las clases semanales del plan (semana lunes a domingo) |
| `GYM_HORAS_ADENTRO` | `2` | Horas (1 a 12) que se considera que un socio sigue adentro, para «Adentro ahora (aprox.)». También se cambia en *Configuración* |
| `GYM_BACKUP_DIR` | sin copia automática | (también en Configuración) Carpeta de la copia de seguridad diaria |
| `GYM_MODULO_TIENDA` | `0` | `1` activa la tienda (ver más abajo) |
| `GYM_KIOSCO_CLAVE_HASH` | sin kiosco | Clave propia del kiosco (hash con `python crear_hash.py kiosco`) |
| `GYM_KIOSCO_SONIDO` | `1` | Pitido de aceptado / rechazado |
| `GYM_KIOSCO_TECLADO` | `0` | `1` muestra un teclado numérico en pantalla (tablets) |
| `GYM_KIOSCO_MAX_POR_MINUTO` | 15 | Límite de consultas por minuto desde un mismo dispositivo |
| `GYM_KIOSCO_SESION_DIAS` | 30 | Duración de la sesión del kiosco |

Hay un ejemplo en `.env.example`.

## Roles

- **Administrador:** todo, incluyendo anular pagos y membresías, planes, exportar, importar, respaldo, y la administración de la tienda.
- **Recepción:** socios, cobros, asistencia, caja y venta en el mostrador. No anula, no edita planes, no exporta, no cambia la configuración ni administra usuarios. **Cada persona tiene su propia cuenta**, guardada en la base con la clave siempre con hash: el administrador las crea, las desactiva y cambia sus claves desde el menú *Usuarios* (mínimo 10 caracteres, con confirmación). Las cuentas **no se borran**, se desactivan: así los pagos, ingresos, ventas e importaciones viejos siguen a nombre de quien los hizo y el nombre no se reutiliza. Si una cuenta se desactiva o le cambian la clave, su sesión abierta se cierra en el siguiente clic. Cada pago, anulación, venta, ingreso e importación guarda el nombre de quien lo hizo y se ve en las pantallas de pagos, asistencia, tienda, caja e importación.
- **Kiosco:** sesión aparte con su propia clave, limitada a la pantalla de ingreso.

## Modo kiosco (puerta)

1. `python crear_hash.py kiosco` y cargá el resultado en `GYM_KIOSCO_CLAVE_HASH`.
2. En la computadora o tablet de la puerta abrí `/kiosco/` y poné la clave del kiosco.
3. Poné el navegador en pantalla completa (F11). El campo de DNI mantiene el foco: sirve un teclado numérico USB o el teclado en pantalla (`GYM_KIOSCO_TECLADO=1`).
4. El socio ingresa su DNI: pantalla verde o roja durante 5 segundos y vuelve sola.

Privacidad: solo muestra nombre, foto, estado y días restantes. Nunca teléfono, email, notas, deudas ni pagos; un rechazo no dice el motivo económico. Hay límite de intentos por minuto para que nadie pueda averiguar quién es socio probando DNI. La sesión del kiosco no puede entrar a ninguna otra pantalla.

## «Adentro ahora (aprox.)»

En el panel de inicio se muestra cuántos socios hay adentro **de forma aproximada**: los que tuvieron un ingreso en las últimas N horas (por defecto 2; se cambia en *Configuración* o con `GYM_HORAS_ADENTRO`). **No se registra la salida**: nadie tiene que marcarla, por eso es una estimación y no un conteo exacto (alguien que se fue enseguida figura hasta que pasan las N horas, y alguien que entrena más de N horas deja de figurar). Cada socio cuenta una sola vez aunque haya ingresado varias veces, y se muestra solo el nombre y la hora de ingreso, nunca teléfono, email ni deudas.

## Tienda (opcional)

Con `GYM_MODULO_TIENDA=1` aparece en el menú: productos (nombre, marca, categoría, precio, costo opcional, stock y stock mínimo), venta de mostrador con socio opcional y medio de pago, aviso si el stock no alcanza, entradas y ajustes de stock con motivo, lista de faltantes, más vendidos y anulación de ventas (devuelve el stock). Los ingresos de la tienda se muestran **separados** de las cuotas en el panel y en la caja diaria. Apagada, no hay menú ni pantallas (404). No emite facturas: no hay facturación electrónica.

## Importar, exportar y respaldo

- **Importar socios:** desde *Datos*, subí un CSV (`nombre;dni;telefono` obligatorios; `email`, `fecha_alta`, `estado`, `notas` opcionales; acepta `;` `,` o tabulación y fechas dd/mm/aaaa). Primero muestra una vista previa con los errores por línea y recién al confirmar importa las filas válidas.
- **Exportar:** socios y pagos en CSV (los pagos anulados salen marcados y con monto que cuenta en 0).
- **Respaldo:** *Datos → Descargar copia de seguridad* baja un zip con la base y las fotos. Para automatizarlo:

  ```bash
  python backup.py --destino /ruta/respaldos --conservar 14
  ```

  En Windows: `python backup.py --destino D:\respaldos --conservar 14`. Para el Programador de tareas: acción «Iniciar un programa», programa `C:\ruta\al\proyecto\.venv\Scripts\python.exe`, argumentos `backup.py --destino D:\respaldos --conservar 14`, y en «Iniciar en» la carpeta del proyecto.

  Programalo con cron (Linux) o el Programador de tareas (Windows). **Restaurar:** con la app detenida, descomprimí el zip y reemplazá `gimnasio.db` y la carpeta `fotos`.

### Copia de seguridad automática diaria

En **Configuración → Copia de seguridad automática** elegí una carpeta (ruta completa, por ejemplo `D:\Copias`; puede ser una carpeta sincronizada de Google Drive u OneDrive, o un pendrive). Al guardar se hace la primera copia en el momento; después el sistema hace **una por día** (una revisión cada 15 minutos mientras esté abierto) y conserva **las últimas 14** (`copia-seguridad_AAAA-MM-DD_HHMMSS.zip`; no toca otros archivos de esa carpeta). Dejar la carpeta vacía la apaga. También se puede definir con `GYM_BACKUP_DIR`.

- **Panel (solo administrador):** muestra la fecha de la última copia y avisa en rojo si hace **más de 3 días** que no se hace (también avisa si nunca se hizo, si no está configurada o si la última falló, por ejemplo con el pendrive desenchufado).
- La copia solo se hace si el sistema está abierto en algún momento del día: **si la computadora está apagada todo el día, ese día no hay copia**. Una copia en la misma computadora no protege de que se rompa o se la roben: usá un pendrive o una carpeta sincronizada en la nube.
- La copia es consistente aunque el sistema esté en uso y se escribe primero como archivo temporal: nunca queda una copia a medias.
- `backup.py` sigue sirviendo para programarlo por fuera con el Programador de tareas.

## Cómo correrlo

```bash
python run.py
```

Abrí <http://127.0.0.1:5000> e ingresá con el usuario y la clave que elegiste. Por defecto solo escucha en esa computadora; para abrirlo a la red local usá `HOST=0.0.0.0 python run.py` (Linux / macOS) o, en PowerShell, `$env:HOST = '0.0.0.0'; python run.py` (Windows puede pedir permiso en el Firewall).

La base de datos se crea sola en `instance/gimnasio.db` la primera vez.

## Datos de ejemplo

```bash
python seed.py            # carga 3 planes, 30 socios con membresías en distintos estados, pagos y asistencias
python seed.py --reset    # BORRA la base y la recarga con los datos de ejemplo
```

Sin `--reset`, el script se niega a tocar una base que ya tiene datos. Los vencimientos se acomodan respecto de la fecha de hoy: hay socios vigentes, por vencer, vencidos, pausados, de baja y sin plan.

## Tests

```bash
pytest
```

Recorrido de punta a punta contra un servidor real (login, socio, membresía, pagos, anulación, asistencia, kiosco, tienda, caja y respaldo), con tienda apagada y encendida:

```bash
python scripts/recorrido_http.py
```

Los tests usan una base temporal y no tocan tus datos.

## Reglas de negocio

- **Vencimiento:** inicio + duración del plan en días. Un plan de 30 días que arranca el 1/10 vence el 31/10; el socio puede entrar ese día inclusive y desde el 1/11 figura vencido.
- **Por vencer:** quedan 7 días o menos (configurable con `GYM_DIAS_ALERTA`).
- **Pagos:**
  - El *primer* período pago de una membresía confirma el período inicial: el vencimiento no cambia.
  - Los períodos siguientes suman la duración del plan desde el vencimiento actual, o desde la fecha de pago si ya estaba vencida.
  - **Pagos parciales:** un monto menor al precio pide confirmación y deja saldo pendiente; los pagos se acumulan hasta completar el período y el excedente queda a favor.
  - **Varios períodos:** el formulario de pago tiene «Cuántos períodos paga» (1, 2, 3, 6, 12 y anual). El monto se calcula solo (precio del plan × períodos, menos lo que el socio ya tenga acumulado) y se puede editar. Si el monto **no es un múltiplo exacto** del precio, aparece una pantalla de confirmación («Esto cubre X períodos y sobra $Y a favor» o «Falta $Z para el próximo período») y no se guarda nada hasta confirmar. Al guardar, la ficha del socio muestra vencimiento anterior, vencimiento nuevo, períodos cubiertos y saldo; el saldo a favor queda visible en la ficha y se descuenta del próximo pago.
  - **Pago anual:** «anual» son los períodos que hacen un año (12 para un plan de 30 días; 365 ÷ duración, redondeado). Cada plan puede tener un descuento anual (porcentaje o monto fijo) que el administrador carga al crear o editar el plan. El descuento se aplica solo si se elige «Anual» y el monto alcanza el precio anual con descuento; en la caja y los CSV figura lo que se cobró de verdad (el descuento se guarda aparte, en cada pago).
  - **Anular:** pagos y membresías no se borran; se anulan con motivo y autor, el vencimiento se recalcula y dejan de contar en panel, caja y CSV. Para anular una membresía hay que anular antes sus pagos.
- **Elegir un socio:** en nuevo pago, asignar o renovar plan (Socios → «Asignar o renovar plan»), registrar ingreso y venta de tienda hay una lista de socios para elegir con un clic (foto, nombre, DNI, plan y estado con color). Orden por defecto: vencidos, por vencer y el resto, cada grupo alfabético; se puede pasar a «Solo A–Z». El buscador la filtra mientras se escribe (por nombre o DNI), de a 50 con «Mostrar más». Solo la ven administrador y recepción: el kiosco nunca la tiene.
- **Planes:** se desactivan en vez de borrarse; los ya vendidos conservan precio y duración. Al reasignar un plan, los días que sobraban se acumulan.
- **Ingreso:** se rechaza si la membresía está vencida, sin plan, pausado, de baja, sin pago (salvo `GYM_ACCESO_SIN_PAGO`), con reingreso el mismo día (salvo `GYM_PERMITIR_REINGRESO`) o con clases semanales agotadas.
- **Alertas:** solo socios en estado *activo*.
- **Fechas:** siempre en `America/Argentina/Buenos_Aires`.
- **Montos:** se guardan en centavos; los formularios aceptan `25000`, `25.000` o `25.000,50`.
- **Base de datos:** se actualiza sola al arrancar (migraciones numeradas con `PRAGMA user_version`); una base de la versión anterior se conserva con todos sus datos (la versión 5 agrega las cuentas de usuario y el registro de importaciones).

## Instalador de Windows (programa de escritorio)

Para quien no sabe de programación: un instalador «Siguiente, Siguiente, Finalizar» que no requiere Python. Instala el programa con acceso directo en el escritorio y en el menú Inicio, y lo abre en **su propia ventana** (sin barra de navegador). Al cerrar la ventana se apaga el servidor.

- **Los datos van aparte del programa:** base, fotos, copias, registros y la clave secreta viven en `C:\ProgramData\GestionGimnasio` (si esa carpeta no se puede escribir, en `%APPDATA%\GestionGimnasio`). Nunca dentro de `Program Files`. Se puede elegir otra con la variable `GYM_DATA_DIR`.
- **Actualizar:** se ejecuta el instalador de la versión nueva encima. Mismo `AppId` = se actualiza en lugar de duplicar, y los datos no se tocan. La versión figura al pie de todas las pantallas (y en el título de la ventana).
- **Desinstalar:** borra el programa pero **no los datos** (el desinstalador avisa dónde quedan). Para borrarlos de verdad, borrá a mano esa carpeta.
- **Requisito de Windows:** *Microsoft Edge WebView2 Runtime* (viene con Windows 11 y con Windows 10 actualizado; el instalador avisa si falta).
- **Primera vez:** se abre el asistente de configuración (ver arriba) y no hace falta tocar variables de entorno.

### Cómo se arma el instalador

No se puede armar desde Linux ni macOS: se necesita Windows (o GitHub Actions).

1. **Con GitHub Actions (recomendado):** subí el proyecto a un repositorio de GitHub. En la pestaña **Actions → «Instalador de Windows» → Run workflow** (o subiendo una etiqueta `v1.0.0`). Corre en `windows-latest`: ejecuta los tests, arma el `.exe` con PyInstaller, lo autocomprueba (`--autocomprobar`) y compila el instalador con Inno Setup. Al terminar, el instalador queda como **artefacto descargable** al final de la página de esa ejecución (`GestionGimnasio-Instalador-<versión>`).
2. **En una PC con Windows:** instalá Python 3.12 e [Inno Setup 6](https://jrsoftware.org/isinfo.php) y, en PowerShell desde la carpeta del proyecto, ejecutá `.\windows\construir.ps1`. El instalador queda en `windows\Salida\`.

Para sacar una versión nueva: cambiá `__version__` en `app/version.py` (única fuente: la usan la pantalla, el instalador y el workflow) y volvé a correr el workflow.

Dependencias solo de empaquetado (no entran en `requirements.txt`; están en `windows/requirements-windows.txt`): `pyinstaller` (arma el `.exe` sin Python instalado) y `pywebview` (la ventana propia). Android (APK) y PWA **no están hechos**: quedan para más adelante.

### PENDIENTE: prueba manual en un Windows real

Nada de esto se pudo ejecutar acá (no hay Windows, PyInstaller ni Inno Setup en este entorno). Qué hay que verificar a mano, en una PC con Windows 10/11 limpia (sin Python):

1. Correr el workflow y descargar el artefacto. Si algún paso falla, ese es el primer dato a revisar.
2. Ejecutar `GestionGimnasio-Instalador-<versión>.exe`: el asistente está en español, crea el acceso directo del escritorio y el del menú Inicio.
3. Abrir el programa: debe aparecer una ventana sin barra de navegador con el asistente de primera vez. Completarlo.
4. Comprobar que `C:\ProgramData\GestionGimnasio` tiene `gimnasio.db`, `fotos`, `registros\gimnasio.log` y que **no** hay datos dentro de `Program Files`.
5. Cargar un socio, cerrar la ventana y comprobar en el Administrador de tareas que no queda ningún proceso `GestionGimnasio.exe`.
6. Volver a abrir: el socio sigue ahí.
7. Ejecutar un instalador con versión mayor (cambiando `__version__`): debe actualizar sin duplicar el programa y sin perder el socio; el pie de pantalla muestra la versión nueva.
8. Desinstalar desde «Aplicaciones»: el programa desaparece, el mensaje final avisa que los datos siguen, y la carpeta de datos sigue existiendo.
9. Instalar de nuevo: el socio sigue ahí.
10. Probar en una PC sin WebView2 (o con el instalador de `WebView2` quitado): el instalador debe mostrar el aviso.
11. Probar con otro usuario de Windows (por ejemplo, la recepción): puede abrir el programa y ve los mismos datos.
12. Comprobar que el ícono (la pesa azul) aparece en el escritorio, en el menú Inicio y en la barra de tareas.

## Windows: diferencias a tener en cuenta

- Usá `py -m venv .venv` y `.venv\Scripts\Activate.ps1` (ver arriba) en lugar de `python3` y `source`.
- Las variables se cargan con `$env:NOMBRE = 'valor'` y duran mientras la ventana esté abierta. Para que queden guardadas: `setx NOMBRE "valor"` y abrir una ventana nueva de PowerShell. Con `setx`, un hash con `$` tiene que ir entre comillas simples dentro de PowerShell.
- `crear_hash.py` no muestra lo que escribís al teclear la clave (es normal).
- La base de zonas horarias (`tzdata`) se instala sola desde `requirements.txt` en Windows.
- El código usa `pathlib` para las rutas, sin barras fijas; las rutas que configurás (`GYM_DB_PATH`, etc.) pueden llevar `\`.
- Los CSV se exportan en UTF-8 con BOM, para que Excel abra bien las tildes.
- **No se probó en un Windows real** (ver «Lo que no se pudo probar»).

## Lo que no se pudo probar

- **PENDIENTE: prueba manual en navegador real** del sonido y de la pantalla completa del kiosco (en un navegador sin pantalla no se pueden verificar). Pasos:
  1. Cargá `GYM_KIOSCO_CLAVE_HASH` y `GYM_KIOSCO_SONIDO=1`, corré `python seed.py --reset` y `python run.py`.
  2. En Chrome o Edge abrí `http://127.0.0.1:5000/kiosco/` e ingresá la clave del kiosco.
  3. **Sonido:** subí el volumen, tocá una vez la pantalla (los navegadores no suenan sin una interacción previa) y escribí el DNI de un socio vigente y el de uno vencido: tienen que sonar dos pitidos distintos.
  4. **Pantalla completa:** apretá F11. El campo del DNI tiene que seguir con el cursor y la pantalla verde o roja tiene que ocupar todo y volver sola a los 5 segundos.
  5. Probá con la pantalla y el teclado numérico reales de la puerta y mirá si el nombre se lee a 1 metro.
- **PENDIENTE: prueba en una PC con Windows** (instalación, `Activate.ps1`, `setx`, Programador de tareas) y del **instalador** (lista de 12 pasos en «Instalador de Windows»).
- **PENDIENTE:** celular o tablet reales, y mirar las pantallas nuevas en un navegador real.

## Estructura

```
app/
  __init__.py      fábrica de la app, seguridad (login y CSRF), filtros de plantillas
  config.py        variables de entorno
  db.py            conexión a SQLite
  schema.sql       esquema de la base
  models.py        consultas SQL
  services/        lógica de negocio: membresías, pagos, asistencia, panel, WhatsApp, CSV, validaciones
  routes/          una pantalla por archivo (socios, planes, pagos, asistencia, kiosco, caja, tienda, importar…)
  migraciones.py   actualizaciones de la base por versión
  templates/       HTML con Jinja2
  static/          CSS
tests/             pruebas con pytest
seed.py            datos de ejemplo
windows/           instalador de Windows: lanzador (ventana), .spec de PyInstaller, script de Inno Setup, ícono
.github/workflows/ armado automático del instalador (GitHub Actions)
scripts/           recorrido_http.py: prueba de punta a punta con servidor real
crear_hash.py      genera el hash de la clave (admin, recepcion o kiosco)
backup.py          copia de seguridad por línea de comandos
PROGRESO.md        estado de las tareas de desarrollo
run.py             arranque local
```
