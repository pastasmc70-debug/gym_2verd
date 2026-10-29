# Progreso del rediseño

> La IA actualiza este archivo al final de CADA paso y lo entrega completo. El usuario lo guarda en el repo
> (docs/PROGRESO_REDISENO.md). Al retomar, se lee primero este archivo.

**Última actualización:** 28/10/2026 — fin de la Etapa 3
**Estado general:** ETAPAS 1, 2 Y 3 HECHAS (falta que el usuario las pruebe en Windows y dé el OK para la Etapa 4)

## Decisiones ya tomadas (no volver a discutirlas)
- Estilo: "Athletic Minimal Esmeralda", claro, con color principal verde (variables CSS para poder cambiarlo).
- Tipografía: Plus Jakarta Sans, guardada localmente (sin CDN). Íconos: SVG propios (macro `icono()` en `_macros.html`).
- Se mantiene Bootstrap + Jinja2 con un CSS propio. No se usa Tailwind. No se toca la lógica.
- Menú único para todas las pantallas, preparado para 11 ítems (con "Tienda").
- Sin elementos inventados: nada de capacidad, aforo, saludos con nombre, "Turno Mañana", etc.
- Colores: se usa lo que dice el prompt (primario #006948, contenedor #00855d, hover #005137). DESIGN.md tiene dos paletas
  (la del encabezado y la del texto, #059669); se tomó la del encabezado.
- Estrategia: el CSS (`tema.css`) redefine las clases de Bootstrap que ya usan las plantillas. `btn-dark` = botón principal
  verde, `btn-outline-dark` y `btn-outline-secondary` = botón secundario, `btn-outline-danger` = peligro, `badge text-bg-*`
  = píldoras de estado. Por eso casi no hubo que tocar plantillas.
- Menú: escritorio (desde 1100 px) = barra con logo y usuario arriba, y las secciones en una segunda fila.
  Menos de 1100 px = barra inferior fija (Inicio, Socios, Caja, Asistencia, Más) y "Más" abre una hoja con el resto
  y "Cerrar sesión".
- El texto "usuario · Rol" del menú se deja en una sola línea porque un test lo busca así (test_usuarios.py).

## Cómo está armado el proyecto (verificado en el paso 0)
- Bootstrap 5.3.3, ahora LOCAL en app/static/vendor/bootstrap/ (css/bootstrap.min.css y js/bootstrap.bundle.min.js).
- CSS: app/static/css/tokens.css (variables y fuente, lo cargan todas las pantallas incluido el kiosco),
  tema.css (estilo global sobre Bootstrap), app.css (cosas propias de cada pantalla, ahora con variables),
  kiosco.css (kiosco, hereda colores y fuente de tokens.css).
- Plantillas: app/templates/base.html (menú único, 39 plantillas lo heredan); kiosco/base.html aparte.
- Empaquetado: windows/gimnasio.spec ya incluye app/static completo (no se tocó).

## Etapas
| Etapa | Estado | Notas |
|---|---|---|
| 0. Leer el código y proponer el plan | HECHA | |
| 1. Sistema de estilos global + menú único | HECHA | Falta probar en Windows (pywebview) |
| 2. Panel de inicio | HECHA | Falta probar en Windows |
| 3. Celular (barra inferior, tablas) | HECHA | Auditado con navegador en 390 y 320 px: 28 pantallas sin desborde y sin botones de menos de 44 px |
| 4. Ajustes finos | PENDIENTE | |

## Pantallas (estado por pantalla)
El estilo global ya se aplica a todas por herencia (botones, campos, tablas, píldoras, avisos, interruptores, menú).
- Inicio: HECHA (Etapa 2; revisada con captura en 1440, 820, 390 y 320 px)
- Socios (listado, nuevo, ficha, editar): HECHA a nivel global (listado y formulario revisados con captura); ficha: REVISAR
- Planes (listado, editar): HECHA a nivel global (listado revisado con captura)
- Configuración, Datos, Pagos, Alertas, Caja: HECHA a nivel global (revisadas con captura)
- Registrar pago, Asistencia, Usuarios, Importar (vista previa), Tienda: HECHA a nivel global; REVISAR en pantalla real
- Login: HECHA (con barra verde arriba)
- Kiosco: HECHA (solo colores y fuente); REVISAR en pantalla real
- Asistente de primera vez, vista de recepción: REVISAR (heredan el estilo global)

## Etapa 2: decisiones del panel de inicio
- Orden: título + fecha en píldora; aviso de copia de seguridad arriba si NO está ok (ámbar/rojo, con ícono y "Ir a Configuración →");
  si está ok, la línea "Última copia de seguridad" queda abajo; 4 botones grandes con ícono (Registrar ingreso es el principal);
  tarjetas de métricas con ícono de color (verde, ámbar, rojo, azul); tarjeta "Adentro ahora (aprox.)" con la aclaración de estimado.
- Se conservaron todos los textos, ids (adentro-ahora, copia-seguridad) y el h2 `Adentro ahora (aprox.): <span class="fw-bold">N</span>`.
- Los montos usan la regla anti-corte de app.css (clamp con cqw + nowrap, la busca un test); los conteos usan `.numero-cuenta` (más grandes).
- Celular: botones de acción en 2x2; Ingresos y Tienda a todo el ancho; después Socios/Asistencias y Por vencer/Vencidos de a dos.
- Sin elementos inventados (no hay aforo, saludo ni porcentajes).

## Etapa 3: decisiones del celular
- Auditoría automática en 28 pantallas (390 y 320 px): se corrigieron 3 desbordes (renglones de botones en Socios, Caja y Productos)
  y la paginación (botones de 44 px).
- Los renglones de botones/filtros bajan de línea en celular (`main .d-flex { flex-wrap: wrap }`) y los textos de botones pueden partirse en 2 líneas.
- Tablas: siguen siendo tablas con deslizamiento horizontal dentro de la tarjeta (no se pasaron a formato tarjeta para no tocar la
  estructura que miran los tests), con sombra en el borde donde hay más para ver. En Socios, Planes, Alertas, Productos, Faltantes y
  Usuarios la primera columna (nombre) queda fija al deslizar (clase `tabla-fija`).
- Áreas seguras de iOS/Android: `viewport-fit=cover` + márgenes con `env(safe-area-inset-*)` en barra superior, barra inferior y contenedor.
- Botones táctiles: mínimo 44 px también los `btn-sm` en pantallas angostas.

## Archivos creados o modificados (ruta exacta y estado)
Etapa 3:
- app/static/css/tema.css  (bloque "CELULAR Y PANTALLAS ANGOSTAS")
- app/templates/socios/lista.html, planes/lista.html, alertas.html, tienda/productos.html, tienda/faltantes.html, usuarios/lista.html
  (solo se agregó la clase `tabla-fija` a la tabla)
Etapa 2 (además de lo de la Etapa 1):
- app/templates/inicio.html  (rediseñada)
- app/templates/_macros.html  (más íconos: dinero, reloj, alerta, usuario_mas, calendario, info, flecha, pesa, escudo)
- app/static/css/app.css  (estilos del panel; ajuste del tamaño de los montos)
Etapa 1:
Nuevos:
- app/static/css/tokens.css
- app/static/css/tema.css
- app/static/vendor/bootstrap/css/bootstrap.min.css  (Bootstrap 5.3.3, sin la referencia al mapa)
- app/static/vendor/bootstrap/js/bootstrap.bundle.min.js  (Bootstrap 5.3.3)
- app/static/vendor/fonts/PlusJakartaSans-variable.woff2  (fuente variable, licencia OFL)
- app/static/vendor/fonts/OFL.txt
Modificados:
- app/templates/base.html  (sin CDN, menú único, barra inferior, hoja "Más")
- app/templates/_macros.html  (se agregó la macro icono())
- app/templates/login.html, socios/form.html, planes/form.html, usuarios/form.html, usuarios/clave.html, pagos/form.html,
  socios/membresia_form.html, importar/subir.html  (solo se agregó la clase `tarjeta-form` a la tarjeta)
- app/templates/kiosco/base.html  (carga tokens.css)
- app/static/css/app.css  (colores fijos pasados a variables)
- app/static/css/kiosco.css  (colores y fuente desde variables; el botón azul pasa a verde)
No se tocó: lógica, rutas, servicios, base de datos, tests, windows/gimnasio.spec.

## Tests
Último resultado de pytest: pasan todos, sin cambiar ningún test.
Nota: no corras pytest con variables GYM_* puestas en el entorno (por ejemplo GYM_MODULO_TIENDA): hacen fallar 2 tests.

## Cosas que el usuario debe probar en Windows
00. Celular real (o la ventana angosta): deslizar las tablas de Socios y Pagos, usar la barra de abajo y "Más", y revisar que ningún botón quede cortado.
0. Panel de inicio: que los números no se partan en dos líneas y que los botones y tarjetas se vean bien al achicar la ventana.
1. Que el programa abra SIN internet (desconectá el wifi) y se vea con la letra Plus Jakarta Sans y todo en verde.
2. El menú: que se vean las 11 secciones sin cortarse (con Tienda activada) y que "Cerrar sesión" ande.
3. Achicá la ventana: tiene que aparecer la barra de abajo y "Más" tiene que abrir la hoja con el resto.
4. Configuración: los interruptores apagados se ven grises con borde, los prendidos verdes.
5. El modo kiosco: que se vea bien y los botones sean verdes.
6. Si construís el instalador: que la carpeta app/static/vendor quede incluida (el spec ya incluye app/static).

## PRÓXIMO PASO
Esperar el OK del usuario y hacer la Etapa 4: ajustes finos según lo que el usuario vea en el programa real (traer capturas o lista de cosas a corregir).
