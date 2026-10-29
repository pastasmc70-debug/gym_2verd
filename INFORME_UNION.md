# INFORME DE UNIÓN

## Qué se unió
Siete zips del mismo proyecto, cada uno en su carpeta y sin tocar los originales. Se armó un repositorio git nuevo.

| Zip | Archivo | Contenido (tareas) | Tests del zip |
|---|---|---|---|
| z6 | gimnasio_3 (ff8e18da) | E (**base**) | 445 |
| z5 | gimnasio_4 (ad9b9368) | E + F (ancestro común) | 497 |
| z3 | gimnasio_4 (31edca8f) | E, F, A, B | 571 |
| z1 | gimnasio_5 (f8e4d5a6) | + C (parcial) | 598 |
| z4 | gimnasio_5 (c67d6b8a) | E, F, D | 512 |
| z2 | gimnasio_6 (df056e79) | E, F, G | 541 |
| z7 | gimnasio_6_HI (17e0e622) | z2 + H + I | 637 |

Nota: el pedido hablaba de 2 zips nuevos (H e I); llegó **uno solo** (z7), que trae H e I juntas.

## Tarea × zip
| Tarea | z6 | z5 | z4 | z3 | z2 | z1 | z7 | Resultado en la unión |
|---|---|---|---|---|---|---|---|---|
| E | sí | sí | sí | sí | sí | sí | sí | TIENE |
| F | – | sí | sí | sí | sí | sí | sí | TIENE |
| A | – | – | – | sí | – | sí | – | TIENE |
| B | – | – | – | sí | – | sí | – | TIENE |
| C | – | – | – | – | – | PARCIAL | – | PARCIAL (código y 27 tests; sin compilar ni probar en Windows) |
| D | – | – | sí | – | – | – | – | TIENE |
| G | – | – | – | – | sí | – | sí | TIENE |
| H | – | – | – | – | – | – | sí | TIENE |
| I | – | – | – | – | – | – | sí | TIENE |
| J | – | – | – | – | – | – | – | NO existe en ningún zip (no se hizo) |

(El estado se decidió mirando el código y los tests de cada zip, no los archivos de progreso.)

## Linaje y orden de unión
Base z6 → z5 (F) como ancestro común. z3, z1, z4 y z2 parten de z5 o de sus descendientes; **z7 (H+I) parte de z2**, es decir, de la misma línea (no de una línea distinta), por lo que el orden pedido se mantuvo sin cambios. A y B vienen juntas en z3, y H e I juntas en z7, así que se unieron de a pares.

Orden y suite completa después de cada unión (todas verdes):
1. A+B (z3): 571
2. C (z1): 598
3. D (z4): 613
4. G (z2): 642
5. H+I (z7): 739 (= 598 + 15 + 29 + 96 + 1 test de migración nuevo)
6. Consolidación de PROGRESO.md y archivos históricos a `docs/historial/`: 739.

`datos/` (que traía z1 con una base vacía y `secret_key`) se excluyó y está en `.gitignore`, igual que `instance/`, `*.db`, `secret_key`, `respaldos/`, `__pycache__` y `.pytest_cache`.

## Conflictos y cómo se resolvieron
- **PROGRESO.md** (D y varias ramas): se conservaron todas las secciones. Ahora hay un solo PROGRESO.md con la tabla consolidada arriba y el historial detallado abajo; los de la otra línea están en `docs/historial/` (PROGRESO_IA3.md, CAMBIOS_IA3.md, TAREAS_IA3.md).
- **G con B** (configuración, panel, README, `.env.example`, `services/configuracion.py`): conflictos aditivos. Se combinaron ambos cambios: conviven `horas_adentro` y `backup_carpeta`, la tarjeta «Adentro ahora» y el bloque de copia de seguridad.
- **Migraciones**: choque real en el número 5 (A usa V5 para `usuarios`/`importaciones`; H también usaba V5 para el descuento anual). Se renumeró la de H a **V6**. Migraciones finales: V2 (base), V3, V4 (`configuracion`, F), V5 (usuarios, A), V6 (descuento anual, H). `user_version` = 6.
- Tests que dependían del número: 2 ajustados (`test_pagos_periodos.py`: ahora `numero < 6` y versión 5 antes de aplicar la última; `test_migraciones.py`: la prueba 4→5 de A usa solo hasta V5) y 1 nuevo (de la versión 4 a la última conviven usuarios y pagos por períodos). Se mantuvieron todos los tests duplicados con el mismo nombre.
- Verificado con una base real de la versión base (user_version 3, 30 socios, 58 pagos): al abrirla con la app unida pasa a 6, conserva los 30 socios y 58 pagos y crea `configuracion`, `usuarios`, `importaciones` y `pagos.descuento_centavos`.
- No hubo ninguna implementación distinta de lo mismo que exigiera tu decisión.

## Verificación final
- Suite completa: **739 passed**.
- Servidor real (`scripts/recorrido_http.py`, tienda apagada y encendida): **28 OK, 0 FALLA** (login, alta de socio y DNI repetido, membresía, pago total, pago parcial con confirmación, anulación con motivo, asistencia, kiosco clave/rojo/verde/aislado, tienda apagada 404 / venta-stock-anulación, usuarios y recepción, caja, backup).
- Recorrido de H e I en servidor real de la versión unida (tienda apagada: 18 OK; encendida: 19 OK; 0 FALLA): pago de 1 período, de 2 períodos exacto, monto no múltiplo con pantalla de confirmación y confirmación, «Volver y corregir», saldo a favor visible en el siguiente pago, pago anual con descuento (10 % de 120.000 → 108.000), lista de socios en Registrar pago, Asignar membresía (`/membresias/nueva`), Asistencia y Tienda, filtro de la lista, clic que lleva al socio, sin sesión pide login, recepción la usa, venta a un socio, y **el kiosco no la muestra ni puede pedir el fragmento**.
- Capturas en Chromium a 1366 px y 390 px (sin desborde horizontal en ninguna): ver los PNG entregados. Se usó Bootstrap 5.3.3 local porque el CDN está bloqueado acá, así que los colores pueden diferir del tema de producción.

## Pendientes (no probados acá)
- **C**: compilar el .exe con PyInstaller, el instalador Inno Setup, el workflow de GitHub Actions, WebView2 y la carpeta `C:\ProgramData\GestionGimnasio` en Windows real. `windows/requirements-windows.txt` fija `pyinstaller==6.11.1` y `pywebview==5.3.2` sin verificar que instalen.
- **J**: no se hizo.
- Celular real (aspecto de H e I, foto de socios con EXIF), Drive/OneDrive/pendrive reales para G, varios procesos reales a la vez, Windows real en general.
- Pasos manuales sugeridos para C: ver la sección «Instalador de Windows» del README (12 pasos).

## Riesgos
- La copia automática (G) es un hilo dentro de la app: si la app está cerrada todo el día no hay copia ese día.
- Si alguien tiene una base de la línea H/I con `user_version` 5 (la V5 de H), esa base **no** migra sola a la V6 unida (el número 5 ya figura como aplicado): hay que partir de una base de otra versión o aplicar a mano el contenido de V6. No se probó con una base real de esa línea.
- Dependencias de C sin verificar (ver arriba).
