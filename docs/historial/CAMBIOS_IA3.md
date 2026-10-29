# CAMBIOS_IA3

Cambios hechos por la IA 3 sobre la BASE (gimnasio_6). Se actualiza al cerrar cada tarea.

## Migraciones agregadas
| Número usado | Dónde | Qué hace | Nota para juntar el trabajo |
|---|---|---|---|
| **5** (tarea H) | `app/migraciones.py` (`V5`) | `planes.descuento_anual_tipo` y `planes.descuento_anual_valor` (descuento anual por plan); `pagos.descuento_centavos` (default 0) | Si otra IA también usó el 5, **renumerar esta**. Además de cambiar el número en `MIGRACIONES` y en `PRAGMA user_version`, hay que ajustar `tests/test_pagos_periodos.py::test_la_migracion_agrega_las_columnas_sin_tocar_los_datos` (usa `numero < 5` para armar la base "anterior" y espera versión 4). |

## Tarea H: archivos nuevos
- `TAREAS_IA3.md`, `PROGRESO_IA3.md`, `CAMBIOS_IA3.md`: protocolo de la IA 3.
- `app/templates/pagos/confirmar.html`: pantalla de confirmación (pago parcial o monto que no es múltiplo exacto).
- `app/static/js/pagos.js`: al elegir los períodos completa el monto (el cálculo lo hace el servidor; el JS solo copia `data-monto`).
- `tests/test_pagos_periodos.py`: 60 tests de la tarea H.

## Tarea H: archivos modificados
- `app/migraciones.py`: migración 5 (ver arriba).
- `app/models.py`: `crear_plan` / `actualizar_plan` guardan el descuento anual (`d.get`, así los llamadores viejos siguen andando); `membresia_actual` trae `descuento_anual_tipo/valor`.
- `app/services/payments.py`: `reproducir` acepta pagos simulados y suma `descuento_centavos` como crédito; nuevos `periodos_anuales`, `descuento_anual`, `previsualizar_pago`, `opciones_de_periodos`, `descuento_que_corresponde`, `resumen_de_pago`, `VistaPrevia`, `EstadoMembresia.saldo_a_favor_centavos`; `registrar_pago` pide confirmación también cuando sobra plata (código `pago_sobrante`), acepta `confirmar=` (y sigue aceptando `confirmar_parcial=`) y `anual=`, y devuelve períodos cubiertos y saldo a favor.
- `app/services/validation.py`: `validar_plan` valida el descuento anual (porcentaje 1–99 o monto fijo menor al precio anual).
- `app/routes/pagos.py`: `nuevo` con selector de períodos, monto vacío = monto calculado, pantalla de confirmación, "volver y corregir", redirección a la ficha con `?pago=ID`.
- `app/routes/socios.py`: `detalle` calcula saldo a favor y la tarjeta de resultado del pago.
- `app/routes/planes.py`: precarga el descuento al editar un plan.
- `app/templates/pagos/form.html`: selector «Cuántos períodos paga», saldo a favor en el aviso; el aviso de parcial pasó a `confirmar.html`.
- `app/templates/socios/detalle.html`: tarjeta «Pago registrado» (vencimiento anterior/nuevo, períodos, saldo), «Saldo a favor» en la membresía, descuento en el historial de pagos.
- `app/templates/planes/form.html` y `planes/lista.html`: campos y texto del descuento anual.
- `README.md`: reglas de pagos por varios períodos y pago anual.
- Tests viejos ajustados (solo se les agregó `confirmar=True`, porque cargaban un monto de más sin confirmar, algo que ahora exige confirmación por pedido de la tarea): `tests/test_exportar.py` (1), `tests/test_pagos.py` (1), `tests/test_pagos_parciales.py` (1), `tests/test_panel_y_alertas.py` (1).

---

## Tarea I: archivos nuevos
- `app/services/selector.py`: consulta de la lista (orden "prioridad" o alfabético, filtro por nombre o DNI, 50 por vez).
- `app/templates/socios/_selector.html`, `_selector_macros.html`, `_selector_lista.html`, `_selector_mas.html`: el componente (fila con foto chica, nombre, DNI, plan y estado con color) y los fragmentos que pide el JavaScript.
- `app/templates/socios/elegir_para_plan.html`: pantalla nueva «Asignar o renovar plan» (antes solo se entraba desde la ficha del socio).
- `app/static/js/selector.js`: filtra mientras se escribe, cambia el orden, «Mostrar más» y, en la tienda, completa el DNI.
- `tests/test_selector_socios.py`: 36 tests de la tarea I.

## Tarea I: archivos modificados
- `app/routes/socios.py`: `contexto_selector()` (lo usan las otras pantallas) y la ruta `GET /socios/selector` (fragmento HTML).
- `app/routes/pagos.py`: el primer paso de «nuevo pago» muestra la lista (se sacó la búsqueda de 15 resultados).
- `app/routes/membresias.py`: ruta nueva `GET /membresias/nueva` (`membresias.elegir`).
- `app/routes/asistencia.py`, `app/routes/tienda.py`: pasan la lista a su pantalla.
- `app/permisos.py`: se habilitan para recepción `socios.selector_lista` y `membresias.elegir` (las rutas nuevas nacen bloqueadas para quien no sea administrador; el kiosco no puede entrar a ninguna). **Si otra IA toca `ENDPOINTS_RECEPCION` (cuentas de usuario), conservar estas dos.**
- `app/templates/pagos/buscar.html`, `asistencia.html`, `tienda/nueva_venta.html`, `socios/lista.html`: incluyen la lista (ids `q` / `buscar_socio` para el buscador; botón «Asignar o renovar plan» en Socios).
- `app/static/css/app.css`: bloque «Lista de socios para elegir» al final (variables de color aparte: la tarea J las puede mover a la paleta).
- `README.md`: regla «Elegir un socio».
- Sin migraciones nuevas en la tarea I.
