# PROGRESO_IA3

Estados: **pendiente** → **hecha** (código escrito) → **probada** (tests pasando) / **PENDIENTE de prueba manual**.
Archivo propio de la IA 3. No se edita PROGRESO.md (es de otra IA). Detalle de archivos tocados: CAMBIOS_IA3.md.

Comando de tests: `cd gimnasio && PYTHONPATH=$(ls -d /root/.local/share/uv/tools/pytest/lib/*/site-packages) python3 -m pytest -q -o addopts="" -p no:cacheprovider`
Base de partida: suite de la BASE = 541 tests verdes.

| Tarea | Estado |
|-------|--------|
| H. Pagos por varios períodos (meses / anual) | **probada** (601 tests verdes + prueba en Chromium real); PENDIENTE de prueba manual: aspecto con Bootstrap a 390 px |
| I. Lista de socios visible al elegir un socio | **probada** (637 tests verdes + prueba en Chromium real a 390 px); PENDIENTE de prueba manual: aspecto con Bootstrap en un celular real |
| J. Rediseño visual | EN ESPERA (no empezar hasta que lo pida el autor) |

## Tarea H: subpasos
| Subpaso | Estado |
|---------|--------|
| H0. Archivos de protocolo (TAREAS_IA3, PROGRESO_IA3, CAMBIOS_IA3) | hecha |
| H1. Migración 5 (planes.descuento_anual_tipo/valor, pagos.descuento_centavos) | hecha |
| H3. Plan: campos de descuento anual (validación, formulario, lista), modelo | hecha |
| H4. Formulario de pago (selector de períodos + JS), pantalla de confirmación (pagos/confirmar.html), tarjeta de resultado y saldo a favor en la ficha | probada |
| H5. Tests nuevos (tests/test_pagos_periodos.py, 60) + suite completa | probada: 601 passed |
| H6. Prueba con servidor real + Chromium (selector, confirmación, corregir, resultado, anual) | probada 22/23; la 23 (ficha a 390 px sin scroll horizontal) no se pudo evaluar: Bootstrap viene por CDN y está bloqueado acá. La tabla de historial ya existente es la que desborda sin Bootstrap; con y sin la tarjeta nueva da lo mismo |
| H7. scripts/recorrido_http.py (regresión con servidor real) | probada: 26 OK, 0 FALLA |
| H8. README y CAMBIOS_IA3.md | hecha |
| H2. Servicio (services/payments.py): períodos, vista previa, confirmación de sobrante, descuento anual, saldo a favor | probada (suite verde; 4 llamadas de tests viejos ajustadas, ver Decisiones) |

## Tarea I: subpasos
| Subpaso | Estado |
|---------|--------|
| I0. Relevamiento: pantallas que piden un socio = nuevo pago (pagos/buscar.html), asistencia (campo q), tienda (campo DNI) y renovar/asignar plan (hoy solo se entra desde la ficha: no tiene pantalla de búsqueda) | hecha |

| I1. Servicio, fragmento HTML, componente, JS y CSS | probada |
| I2. Integración en nuevo pago, asignar plan (pantalla nueva), asistencia y tienda | probada |
| I3. Tests (tests/test_selector_socios.py, 36) + suite completa | probada: 637 passed |
| I4. Chromium real a 390 px con 120 socios: filtro por nombre y DNI sin recargar, orden, «Mostrar más», clic en cada pantalla, sin JS, sin errores de JS | probada 20/20 (con Bootstrap bloqueado por CDN, pero 0 tarjetas fuera de pantalla y sin scroll horizontal) |
| I5. scripts/recorrido_http.py | probada: 26 OK, 0 FALLA |

## Dependencias pendientes de otras IAs
(ninguna por ahora)

## Decisiones
- **«Anual» = períodos que hacen un año** (365 ÷ duración del plan, redondeado: 12 para 30 días). Con un plan de 30 días son 12 períodos = 360 días de cobertura, no 365.
- **El descuento anual vive en cada plan** (pantalla de planes, solo administrador), no en Configuración, para no pisarme con la IA que toca esa pantalla.
- **El descuento es crédito, no plata cobrada:** `pagos.monto_centavos` sigue siendo lo que entró (caja, panel y CSV no cambian); `pagos.descuento_centavos` suma al calcular períodos.
- **El descuento solo se aplica si se elige «Anual» y el monto alcanza** el precio anual con descuento (menos lo que ya haya acumulado el socio). Si se edita el monto a uno menor, se cobra sin descuento y se pide confirmar.
- **Monto sugerido = precio × períodos − acumulado del socio** (parcial a medio completar o saldo a favor). Sin saldos es exactamente precio × períodos.
- **El primer pago de una membresía** sigue confirmando el período inicial: pagar 2 períodos de entrada suma 1 período de días (el inicial ya estaba dado). Es la regla que ya existía.
- **La confirmación vive en el servicio** (no solo en la pantalla): `registrar_pago` sin `confirmar=True` lanza `RequiereConfirmacion` si el monto no es múltiplo exacto. Por eso 4 llamadas a `registrar_pago` en tests viejos (5 tests fallaban por eso: cargaban $ 25.000,50 o un parcial más un pago completo, sin confirmar) necesitaron `confirmar=True`. No se tocó ninguna otra aserción.
- Resultado del pago: tarjeta en la ficha del socio (`/socios/ID?pago=ID`), no una pantalla aparte, para mantener el redirect de siempre.
- **Tarea I:** «renovar o asignar membresía» no tenía pantalla con búsqueda (solo se entraba desde la ficha): se creó `/membresias/nueva` y un botón en Socios.
- **Tarea I:** el DNI solo se busca si lo escrito son números (con puntos o espacios); «Socio 003» busca por nombre. Se cambió después de ver en el navegador que traía socios de más.
- **Tarea I:** el orden «prioridad» es vencidos, por vencer y resto (sin plan incluido), cada grupo alfabético. Los socios pausados o de baja aparecen igual, con una etiqueta.
- **Tarea I (error encontrado en el navegador):** el contenedor tenía `data-orden` igual que los botones de orden y cada clic en una fila se tomaba como clic de orden. Quedó con `data-orden-inicial` y un test que lo cuida.
- Exportar CSV no cambió (no agregué columna de descuento: no se pidió y el test de columnas es estricto).
