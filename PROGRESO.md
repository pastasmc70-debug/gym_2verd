# PROGRESO

> Archivo único del proyecto tras la unión de las versiones de varias IAs. Arriba, el estado consolidado; abajo, el historial detallado
> de cada ronda y tarea tal como lo dejó quien la hizo. Los archivos de progreso de la otra línea (PROGRESO_IA3, CAMBIOS_IA3, TAREAS_IA3)
> están en `docs/historial/`. Cómo se unió todo: `INFORME_UNION.md`.

## Estado consolidado (versión unida)
Suite completa: **739 passed**. Recorrido HTTP real (`scripts/recorrido_http.py`): 28 OK, 0 FALLA. Migraciones: V2 a V6 (`user_version` = 6).

| Tarea | Qué | Estado | Evidencia en el código | Migración |
|---|---|---|---|---|
| E | Montos del panel en celular (390 px) | probada | regla CSS en `static/css/app.css`, test en `test_panel_y_alertas.py` | – |
| F | Asistente de primera vez + pantalla Configuración | probada (tests + servidor real) | `services/configuracion.py`, `routes/asistente.py`, `routes/configuracion.py` | V4 |
| A | Cuentas de usuario (recepción) en la base | probada (tests + servidor real) | `services/usuarios.py`, `routes/usuarios.py`, `templates/usuarios/` | V5 |
| B | Socios adentro ahora (aprox.) | probada | `dashboard.adentro_ahora`, `GYM_HORAS_ADENTRO` | – |
| D | Tarjeta de ingreso en recepción | probada (tests + capturas) | `attendance.tarjeta_ingreso` | – |
| G | Copia de seguridad automática | probada; NO con Drive/OneDrive/pendrive reales ni en Windows | `services/backup_auto.py` | – (usa `configuracion`) |
| C | Empaquetado para Windows | **PENDIENTE de prueba en Windows real** (código y 27 tests hechos; .exe, instalador y workflow nunca se ejecutaron) | `windows/`, `.github/workflows/`, `app/escritorio.py`, `app/version.py` | – |
| H | Pagos por varios períodos (confirmación, saldo a favor, anual con descuento) | probada (tests + servidor real en la versión unida) | `services/payments.py`, `pagos/confirmar.html`, `static/js/pagos.js` | V6 (era V5 en su zip) |
| I | Lista de socios visible al elegir un socio | probada (tests + servidor real en la versión unida) | `services/selector.py`, `socios/_selector*.html`, `/membresias/nueva` | – |
| J | Rediseño visual | NO se hizo (en espera) | – | – |

Pendientes de prueba manual: ver la lista al final de `INFORME_UNION.md`.

---
## Historial detallado (tal como lo escribió cada IA)
Estados: **pendiente** → **hecha** (código escrito) → **probada** (con tests pytest pasando).
Para retomar: leer solo este archivo y seguir desde la primera tarea pendiente. No rehacer lo que figura como hecho/probada.

Comando de tests (pytest ya está en el disco vía uv; PyPI está bloqueado en este entorno):
`cd gimnasio && PYTHONPATH=$(ls -d /root/.local/share/uv/tools/pytest/lib/*/site-packages) python3 -m pytest -q -p no:cacheprovider`

## Ronda 1: correcciones
| # | Tarea | Estado | Dónde / tests |
|---|-------|--------|---------------|
| 1 | Anular pagos y membresías (motivo, quién, sin borrar, recalcula, no cuenta en panel/caja/CSV) | probada | services/payments.py, templates/*/anular.html, tests/test_anulaciones.py |
| 2 | Pagos parciales con confirmación y saldo pendiente | probada | services/payments.py, tests/test_pagos_parciales.py |
| 3 | GYM_ACCESO_SIN_PAGO (default no) | probada | services/attendance.py, tests/test_reglas_ingreso.py |
| 4 | GYM_PERMITIR_REINGRESO | probada | idem |
| 5 | Clases por semana al ingresar (GYM_LIMITAR_CLASES_SEMANA) | probada | idem |
| 6 | Planes: baja lógica | probada | routes/planes.py, tests/test_planes_y_acumulacion.py |
| 7 | Acumular días al reasignar plan | probada | routes/membresias.py, idem |
| 8 | Roles administrador / recepción + quién cargó | probada | permisos.py, routes/auth.py, tests/test_roles.py |
| 9 | Backup descargable + backup.py | probada | services/backup.py, backup.py, tests/test_backup.py |
| 10 | Importar socios CSV con vista previa | probada | services/importar.py, routes/importar.py, tests/test_importar.py |
| 11 | Seed: ingresos de hoy sin horas futuras (+ ejemplos de parcial y anulado) | probada | seed.py, tests/test_seed.py |
| 11b | Caja diaria de cuotas (base.html ya la enlaza; la tienda se suma en R3) | probada | routes/caja.py, services/caja.py, tests/test_caja.py |
| 11d | Test de migración: base vieja (V1) con datos -> V2/V3 sin perder nada | probada | tests/test_migraciones.py |
| 11c | Correr la suite completa al cerrar la Ronda 1 | probada | suite completa verde (342 tests al cerrar la tarea 12) |

## Ronda 2: modo kiosco
| 12 | Modo kiosco (foco permanente, pantalla verde/roja 5 s, sonido, teclado en pantalla opcional, pantalla completa, privacidad, clave aparte, límite de intentos) | probada | services/kiosco.py, routes/kiosco.py, templates/kiosco/, static/js/kiosco.js, tests/test_kiosco.py + prueba en Chromium real (16/16: foco, solo números, 5 s, verde/roja, teclado en pantalla). NO verificado: sonido (no se escucha en headless), pantalla completa real, foto en pantalla |

## Ronda 3: tienda
| 14a | Migración V3 (tablas de tienda) + servicios (productos, venta con control de stock, entradas, ajustes, anulación, faltantes, más vendidos, caja) + tests | probada | services/tienda.py, migraciones.py, tests/test_tienda_servicio.py, tests/test_migraciones.py (suite: 403 verdes) |
| 14b | Rutas y pantallas de la tienda (apagadas si GYM_MODULO_TIENDA no es 1; permisos admin/recepción) + tests | probada | routes/tienda.py, templates/tienda/ |
| 14c | Tienda aparte de las cuotas en el panel y en la caja diaria + tests | probada | routes/inicio.py, routes/caja.py |

## Tarea 13
| 13 | **No definida, revisar con el autor.** El pedido numeraba 12 (kiosco) y 14 (tienda); no hay nada en el código, los tests ni los pedidos que justifique una 13. No se inventó su contenido | pendiente (del autor) | |

## Cierre
| C1 | README (variables nuevas, roles, backup, import, kiosco, tienda, aclarar que no abre molinetes) y .env.example | probada | README.md, .env.example |
| C2 | Verificación final: suite completa, recorrido HTTP con servidor real, zip, lista honesta de lo no probado | probada | suite 444 verdes; recorrido HTTP real con servidor (tienda apagada y encendida, admin/recepción/kiosco): todo OK; zip regenerado |

## Notas / decisiones tomadas
- Un solo usuario de recepción (variables GYM_RECEPCION_USER / GYM_RECEPCION_PASSWORD_HASH): «quién» = nombre de ese usuario.
- Anular una membresía exige anular antes sus pagos.
- Pagos viejos (anteriores a la migración) menores al precio del plan se reinterpretan como parciales si se recalcula esa membresía.
- Tests viejos adaptados por cambios exigidos: test_asistencia (acceso sin pago), test_panel_y_alertas (parciales), test_exportar (columnas nuevas al final).

## Pedido de cierre (verificación, Windows, kiosco manual, instalación)
| P | Tarea | Estado |
|---|-------|--------|
| V1 | Suite completa | probada: ver resultado exacto abajo |
| V2 | Recorrido HTTP con servidor real (`scripts/recorrido_http.py`) | probada: ver tabla abajo |
| W | Compatibilidad con Windows (README, rutas) | hecha (revisión de código y README; NO probada en un Windows real) |
| K | Kiosco: sonido y pantalla completa como PENDIENTE + pasos manuales en README | hecha: PENDIENTE prueba manual en navegador real (sonido, pantalla completa) |
| I | INSTALACION.md para no técnicos | hecha (comandos verificados donde se pudo; NO probada en Windows) |

### V1: resultado exacto de la suite
Comando: `python -m pytest -q -o addopts=""` (el `-o addopts=""` es porque pytest.ini ya trae `-q` y dos `-q` ocultan el resumen; en este entorno pytest se carga con PYTHONPATH porque PyPI está bloqueado)
```
444 passed in 16.91s
```
(Sin FALLAS. 20 archivos de tests.)

### V2: recorrido HTTP (servidor real `python run.py`, base temporal con seed, dos corridas)
Se corrió `python scripts/recorrido_http.py`: 13 flujos con la tienda apagada y 13 con la tienda encendida = 26 OK, 0 FALLA.

| Flujo | Tienda apagada | Tienda encendida |
|---|---|---|
| login admin | OK | OK |
| alta de socio (y rechazo de DNI repetido) | OK | OK |
| alta de membresía | OK | OK |
| pago total | OK | OK |
| pago parcial (con confirmación) | OK | OK |
| anulación de un pago con motivo (sin motivo no deja) | OK | OK |
| acceso a asistencia | OK | OK |
| kiosco: clave mala rechazada, clave buena entra, pantalla roja | OK | OK |
| kiosco: pantalla verde sin datos privados | OK | OK |
| kiosco: sesión aislada (no ve /socios) | OK | OK |
| tienda: venta, control de stock, faltantes, caja separada, anulación | OK (404 con módulo apagado) | OK |
| caja diaria (suma lo vigente, no el parcial anulado) | OK | OK |
| backup descargable (zip con gimnasio.db y LEEME.txt) | OK | OK |

Nota honesta: las primeras corridas del script dieron FALLA por errores del propio script (nombre de plan equivocado, fecha tomada del reloj UTC en vez de Argentina, monto esperado de la caja); se corrigió el script, no la lógica de negocio.

### W: revisión de Windows
- Rutas: todo el código usa `pathlib`/`os.path`; no hay barras fijas en rutas de archivos (las `/` que quedan son URLs). No hay `open()` sin encoding, ni `fcntl`, `chmod` ni rutas `/tmp`.
- Dependencias: `tzdata` ya se instala solo en Windows (`sys_platform == "win32"`). Sin dependencias nuevas en este pedido.
- Diferencias documentadas en README: `Set-ExecutionPolicy` para `Activate.ps1`, `$env:HOST` en vez de `HOST=… python`, `setx` para variables persistentes, backup.py con rutas `D:\…` y Programador de tareas, `crear_hash.py` no muestra la clave al teclear.
- NO probado: ningún comando se corrió en PowerShell real (este entorno es Linux).

### K: pendiente de prueba manual
- Sonido del kiosco: PENDIENTE (prueba manual en navegador real).
- Pantalla completa real (F11): PENDIENTE (prueba manual en navegador real).
- Pasos para probarlos: README, sección «Lo que no se pudo probar».

### Dependencias nuevas
Ninguna. `scripts/recorrido_http.py` usa solo la biblioteca estándar y werkzeug (ya instalado con Flask).

## Cola nueva (detalle en TAREAS.md; orden obligatorio: E, A, F, B, D, G, C)
| Tarea | Descripción | Estado |
|---|---|---|
| E | Arreglo visual: montos del panel en celular (390 px) | probada (captura en Chromium; ver nota) |
| A | Cuentas de usuario en la base | probada (535 tests + servidor real); portada sobre el proyecto con F |
| F | Asistente de primera vez + pantalla Configuración | probada (tests + servidor real); sin captura visual (ver nota F) |
| B | Socios adentro ahora (aprox.) | probada (tests + captura en Chromium 390 y 1280 px) |
| D | Tarjeta de ingreso en recepción | probada (tests + capturas en Chromium PC y celular) |
| G | Copia de seguridad automática | probada (tests + servidor real); NO probada con Drive/OneDrive/pendrive reales ni en Windows |
| C | Empaquetado para Windows (C1–C5; C6 queda para después) | hecha; lógica probada con pytest; **PENDIENTE de prueba manual en Windows** (ver detalle abajo) |

Nota: el zip adjunto (gimnasio_2.zip) es idéntico al proyecto actual (diff sin diferencias).
- E.1 TAREAS.md y Cola nueva guardados (hecho)
- E.2 Bug reproducido en Chromium con Bootstrap 5.3.2 local (CDN bloqueado en el entorno): '$ 378.000' ocupa 3 líneas a 390 px y 2 líneas a 1280 px (hecho)
- E.3 Corrección en app/static/css/app.css: tamaño de letra fluido por ancho de tarjeta (container query, `clamp(0.8rem, 14cqw, 2.2rem)` con respaldo en vw) y `white-space: nowrap` (hecho)
- E.4 Medido en Chromium real tras el arreglo: '$ 378.000' y un monto de estrés '$ 123.456.789' quedan en 1 línea y sin desbordar a 390, 320 y 1280 px (antes: 3 líneas a 390 px y 2 a 1280 px). Captura: despues_celular_390.png (probada)
- E.5 Test de regresión de la regla CSS en tests/test_panel_y_alertas.py; suite completa verde: 445 passed
- Nota honesta E: el CDN de Bootstrap está bloqueado en este entorno; las capturas usaron Bootstrap 5.3.2 (tema Bootswatch «cerulean») tomado de un paquete local, por eso los colores no son los de producción, pero las reglas de layout son las de Bootstrap. NO probado en un celular real ni con el Bootstrap 5.3.3 del CDN.

## Tarea F (en curso)
Aviso: la tarea A la está haciendo otra sesión, así que acá NO se toca la tabla `usuarios` ni el login de recepción. F guarda al administrador del asistente en la tabla `configuracion` (claves `admin_usuario` y `admin_clave_hash`). Al juntar con A hay que revisar: (1) las dos migraciones usan el número 4 (renumerar una), (2) dónde vive el administrador.
- F.1 Migración V4: tabla `configuracion` (hecho)
- F.2 Servicio de configuración, clave secreta automática, arranque, rutas y plantillas del asistente y de Configuración (hecho, sin probar todavía)
- F.3 tests/test_asistente_configuracion.py escrito (hecho, falta correr)
- F.4 Mutaciones: sin clave mínima, asistente repetible, sin recarga por pedido y sobreescritura de config hacen fallar tests (hecho)
- F.5 Suite completa: 497 passed (445 anteriores + 52 nuevos en tests/test_asistente_configuracion.py)
- F.6 Servidor real (`python run.py`, base vacía, sin variables GYM_*): abre en /asistente/1, 4 pasos, queda logueado, `secret_key` creada con permisos 600, el asistente no se reabre, Configuración abre (probada)
- F.7 README (sección «Primera vez», variables como alternativa), .env.example e INSTALACION.md actualizados (hecho)
- Dependencias nuevas: ninguna.
- Cambios a lógica existente: `validar_config` ya no exige administrador ni SECRET_KEY (el administrador a medias sigue siendo error); `gym_nombre` pasó de variable global de Jinja a context processor (para que cambie sin reiniciar); texto del kiosco sin clave menciona Configuración (mantiene GYM_KIOSCO_CLAVE_HASH).
- Nota F: NO verificado visualmente en navegador (el CDN de Bootstrap está bloqueado acá); NO probado en Windows ni con varios procesos reales (se simula recargando desde la base en cada pedido). No hay cambio de clave del administrador (no estaba pedido; queda para la tarea A o aparte).

## Tarea A (portada sobre gimnasio_4, que ya traía la F)
- A.1 La migración de usuarios pasa a ser la **V5** (la V4 ya la usa F para `configuracion`): tablas `usuarios` e `importaciones` (hecha)
- A.2 services/usuarios.py, routes/usuarios.py, templates/usuarios/, menú «Usuarios» (solo admin), sesión de recepción que se invalida si desactivan la cuenta o cambian la clave, registro de importaciones (hecha)
- A.3 Convivencia con F: el administrador sigue saliendo de `app.config` (variables de entorno o el asistente), así que `auth.py` solo agrega la búsqueda de recepción en la base; `GYM_RECEPCION_*` se importa una vez después de `configuracion.aplicar` (hecha)
- A.4 Tests: tests/test_usuarios.py (37, incluido uno de instalación nueva con asistente → crear cuenta → entrar) + migración V4→V5 en test_migraciones.py. Suite completa: **535 passed** (497 de F + 38 nuevos) (probada)
- A.5 Recorrido HTTP real (scripts/recorrido_http.py, con flujo de usuarios): 28 OK, 0 FALLA (probada)
- A.6 README y .env.example actualizados (hecha)
- Decisiones A: el rol «admin» ya está permitido en la tabla usuarios pero hoy solo se crean y aceptan cuentas de recepción; el administrador sigue en configuración/variables (no se movió a la tabla); usuario = minúsculas, 3–30 caracteres [a-z0-9._-]; la importación guarda quién/cuándo/cuántas (no el nombre del archivo); sin dependencias nuevas.
- NO probado A: pantallas de usuarios en navegador real; si el nombre del administrador del asistente coincide con una cuenta de recepción importada del entorno, el login da prioridad al administrador (caso raro, no validado en el asistente); no hay «cambiar mi propia clave».

## Tarea B
- B.0 Hallazgo: el sistema no tiene «anular ingreso» (la tabla asistencias no tiene columna de anulación), así que «no contar ingresos anulados» hoy no tiene qué excluir; no se inventó esa función (no está en el pedido). La consulta cuenta cada socio una sola vez.
- B.1 Código: HORAS_ADENTRO (GYM_HORAS_ADENTRO, 1–12, defecto 2) en config y en Configuración; services/dashboard.adentro_ahora; bloque en el panel con «aprox.» (hecha, sin probar)
- B.2 tests/test_adentro_ahora.py (36): límites exactos de la ventana (justo N h incluido, N h + 1 s excluido, futuro excluido), N = 1/2/3/12, cruce de medianoche, sin duplicar al mismo socio (cuenta una vez con su último ingreso), orden, sin datos privados, panel con «aprox.» y «No se registra la salida», singular/plural, configuración (valida 1–12, rechaza 0/13/-1/abc/vacío/2.5, persiste en la base, toma cambios de otro proceso, recepción no puede), variable GYM_HORAS_ADENTRO. Mutaciones (>= → >, sin agrupar, sin tope futuro) hacen fallar tests (probada)
- B.3 Suite completa: **571 passed** (535 + 36). Servidor real en Chromium: el bloque se ve bien en 390 y 1280 px sin scroll horizontal; Configuración rechaza 13 y acepta 3, y el panel pasa a decir «últimas 3 horas» (probada). Captura: adentro_celular.png
- B.4 README, .env.example actualizados (hecha)
- Decisiones B: ventana inclusiva (exactamente N h cuenta); si el formulario de Configuración no trae el campo, no cambia el valor (para no romper formularios viejos); lista del panel limitada a 30 nombres + «y N más»; sin dependencias nuevas.
- NO probado B: en celular real; colores reales de producción (CDN de Bootstrap bloqueado, se usó Bootstrap 5.3.2 local con otro tema). «No contar ingresos anulados»: hoy no existe anular un ingreso en el sistema, así que no hay nada que excluir (ver B.0); si se agrega esa función, hay que filtrarla en `dashboard.adentro_ahora`.

## Tarea C: empaquetado para Windows (se pidió hacerla ahora, antes de D y G)
Plan: lógica testeable en app/escritorio.py + app/version.py; windows/ con lanzador (pywebview), .spec de PyInstaller, instalador Inno Setup, ícono; .github/workflows con windows-latest.
Aviso: en este entorno NO hay PyInstaller, pywebview ni Windows (PyPI bloqueado): lo que sea compilar/instalar/abrir la ventana queda PENDIENTE de prueba manual; lo que se puede ejecutar acá (carpeta de datos, servidor, apagado, versión, autocomprobación) se prueba con pytest.
- C.0 Dependencias nuevas (solo para construir el instalador, en windows/requirements-windows.txt; NO entran en requirements.txt ni en el uso normal): pyinstaller (empaquetar en .exe sin Python instalado), pywebview (ventana propia sin barra de navegador, pedido en C1). Pillow solo se usó una vez para dibujar el ícono (no queda como dependencia).
- C.1 app/version.py (1.0.0), create_app(instance_path=...), pie de página con la versión en todas las pantallas (hecha, sin probar)
- C.2 app/escritorio.py (carpeta de datos fuera del programa, servidor local en hilo con apagado, registro a archivo) y windows/lanzador.py (ventana pywebview + --autocomprobar) escritos (hecha, sin probar)
- C.3 windows/icono.ico (7 tamaños, generado con windows/crear_icono.py; dibujo original) (hecha)
- C.4 windows/gimnasio.spec (PyInstaller, modo carpeta, sin consola, con ícono, datos de templates/static/schema/tzdata), windows/instalador.iss (Inno Setup, español, accesos directos, datos en {commonappdata} con uninsneveruninstall, aviso de WebView2), windows/construir.ps1, .github/workflows/instalador-windows.yml (windows-latest, tests + autocomprobación del exe + artefacto) escritos (hecha, NO ejecutados: no hay Windows/PyInstaller/Inno acá)
- C.5 tests/test_escritorio.py (27): carpeta de datos (Windows/otros, nunca dentro del programa), la app guarda todo ahí, los datos sobreviven a «actualizar», servidor local que se apaga y libera el puerto, cerrar la ventana apaga el servidor (pywebview simulado), autocomprobación, versión visible, controles de texto de .iss/.spec/workflow/requirements. Mutaciones (no apagar el servidor, datos dentro del programa) fallan (probada)
- C.6 README (sección «Instalador de Windows»: qué es, dónde van los datos, actualizar, desinstalar, cómo armarlo con GitHub Actions o con construir.ps1, 12 pasos de prueba manual) e INSTALACION.md (opción del instalador) actualizados (hecha)
- C.7 Suite completa: **598 passed** (571 + 27). Recorrido HTTP real: 28 OK, 0 FALLA (probada)

### Estado por subtarea de C
| Sub | Qué | Estado |
|---|---|---|
| C1 | .exe con PyInstaller (modo carpeta), ventana propia con pywebview, ícono .ico, sin barra de navegador, cerrar la ventana apaga el servidor, sin Python instalado | hecha: windows/lanzador.py, gimnasio.spec, icono.ico. Probado acá: el lanzador con pywebview simulado (la ventana se pide con el título y tamaño correctos y al cerrarla se apaga el servidor) y el ícono (.ico válido, 7 tamaños, visto). **PENDIENTE: compilar el .exe y abrir la ventana real en Windows** |
| C2 | Instalador Inno Setup (Siguiente/Finalizar), accesos directos en escritorio y menú Inicio, desinstalador que no borra datos | hecha: windows/instalador.iss. Probado acá solo con controles de texto (AppId fijo, accesos directos, `uninsneveruninstall`, sin `[UninstallDelete]`). **PENDIENTE: compilarlo y correrlo en Windows** |
| C3 | Datos fuera de la carpeta del programa (%PROGRAMDATA%, con respaldo en %APPDATA%) | probada con pytest (lógica, la app guarda todo ahí, el programa instalado se niega a usar una carpeta propia). **PENDIENTE: ver que `C:\ProgramData\GestionGimnasio` se crea con permisos para otros usuarios de Windows** |
| C4 | Workflow de GitHub Actions (windows-latest) que arma el instalador y lo deja como artefacto, documentado | hecha: .github/workflows/instalador-windows.yml (YAML válido, revisado con tests de texto). **PENDIENTE: ejecutarlo en GitHub (nunca corrió)** |
| C5 | La app muestra su versión y se actualiza con un instalador nuevo sin perder datos | versión visible (probada) y datos que sobreviven a abrir una versión nueva sobre la misma carpeta (probada con pytest). **PENDIENTE: la actualización real con dos instaladores** |
| C6 | Android (APK) y PWA | NO implementado, como se pidió |

### Decisiones y avisos de C
- Dependencias nuevas, solo para armar el instalador (windows/requirements-windows.txt; no están en requirements.txt): `pyinstaller==6.11.1`, `pywebview==5.3.2`. Justificación: son lo que pide C1 (empaquetar sin Python y ventana propia). Las versiones están fijadas de memoria y NO se pudieron verificar con una instalación real (PyPI bloqueado acá): si el workflow falla en «Instalar dependencias», ajustar el número.
- Cambio mínimo en código existente: `create_app(test_config=None, instance_path=None)` (con el valor por defecto todo se comporta igual) y un pie de página con la versión en base.html.
- Datos en %PROGRAMDATA% (compartidos por todos los usuarios de la PC, útil si recepción usa otra cuenta de Windows); el instalador crea la carpeta con permiso de escritura para todos y el desinstalador nunca la borra.
- Riesgos: el .spec nunca se compiló (pueden faltar `hiddenimports` de pywebview/pythonnet); WebView2 es requisito de Windows (el instalador solo avisa, no lo instala); el programa no impide abrir dos ventanas a la vez (comparten la misma base; no se agregó bloqueo de instancia única porque no estaba en el pedido); sin firma digital, así que Windows SmartScreen va a mostrar «editor desconocido».
- Quedan sin hacer D y G (el orden pedido era E, A, F, B, D, G, C; se hizo C antes por pedido del usuario).

## Tarea D (en curso)
- D.1 Servicio attendance.tarjeta_ingreso, ruta (session, se muestra una vez), plantilla asistencia.html y CSS (hecho, falta probar)
- D.2 tests/test_tarjeta_ingreso.py (15 tests): datos de la tarjeta, una sola vez, foto o inicial, estados y días, deuda parcial, sin deuda, rechazos sin tarjeta, rol recepción, escape de HTML. Mutaciones (no borrar de la sesión, ocultar deuda, socio equivocado) hacen fallar tests (hecho)
- D.3 Suite completa: 512 passed (497 + 15)
- D.4 Capturas en Chromium real con Bootstrap 5.3.3 (bajado de npm) y servidor real: PC 1280 px y celular 390 px, con foto y sin foto + deuda. Sin desborde horizontal (scrollWidth = ancho de pantalla), foto cargada (naturalWidth > 0). Se corrigió el diseño del celular: la foto pasó a ir al costado del texto para que la tarjeta entre en pantalla (probada)
- Decisión: la tarjeta aparece solo cuando el ingreso se registró (no en rechazos: ahí sigue el mensaje rojo). Quien entra sin haber pagado nada (con GYM_ACCESO_SIN_PAGO) figura con el precio completo como saldo, igual que en la ficha del socio.
- Nota D: NO probado en un celular real ni con fotos subidas desde un teléfono (orientación EXIF); las fotos de las capturas son imágenes de prueba. Dependencias nuevas: ninguna (Bootstrap solo se usó para la captura).

## Tarea G (en curso)
- G.1 services/backup_auto.py (estado, ejecutar con retención 14, validar_carpeta, hilo de fondo), claves backup_* en configuracion, GYM_BACKUP_DIR (hecho, falta pantalla, panel y tests)
- G.2 Pantalla Configuración (carpeta, estado de la última copia, primera copia al guardar), panel del administrador con fecha y aviso (>3 días, nunca, sin configurar, falla), README y .env.example (hecho)
- G.3 tests/test_backup_automatico.py (29 tests): una por día, cambio de carpeta, retención 14 sin tocar archivos ajenos, fallas (carpeta inválida, verificación rota, sin archivo a medias), reintento, bloqueo entre procesos, avisos en el límite de 3 días, validación de carpeta, pantalla y panel (admin sí, recepción no), hilo. Mutaciones (30 en vez de 14, >= en vez de >, temporal sin renombrar, ignorar cambio de carpeta, mostrar a recepción) hacen fallar tests
- G.4 Bug encontrado por los tests y corregido: si la carpeta no era un directorio, el `unlink` del manejo de errores levantaba otra excepción y dejaba la copia «en curso»
- G.5 Suite completa: 541 passed (512 + 29)
- G.6 Servidor real (`python run.py` con GYM_BACKUP_DIR): el hilo hizo la copia a los ~20 s (zip con gimnasio.db y fotos, sin temporales), el panel mostró la fecha; captura del aviso en celular (390 px): sin desborde (probada)
- Decisiones: la copia es un hilo dentro del proceso de la app (no usa el Programador de tareas): si la app está cerrada todo el día, no hay copia ese día. El aviso se ve solo para el administrador. Dependencias nuevas: ninguna.
- Nota G: NO probado con Google Drive/OneDrive reales (se usa la carpeta sincronizada como una carpeta común), ni con un pendrive real que se desenchufa, ni en Windows, ni con varios procesos reales a la vez (el bloqueo se probó simulado).

## Tareas H e I (resumen del historial de la otra línea; detalle en docs/historial/PROGRESO_IA3.md y CAMBIOS_IA3.md)
- H: migración (planes.descuento_anual_tipo/valor, pagos.descuento_centavos; **renumerada V5 → V6** al unir), servicio de períodos y vista previa, confirmación de sobrante, descuento anual, saldo a favor; 60 tests en tests/test_pagos_periodos.py.
- I: servicio `selector`, fragmento HTML + JS, integrado en nuevo pago, asignar/renovar plan (pantalla nueva `/membresias/nueva`), asistencia y tienda (nunca en el kiosco); 36 tests en tests/test_selector_socios.py.
- J quedó en espera por pedido del autor.
