# TAREAS (IA 3)

TAREA H. Pagos por varios períodos (meses / anual)
- En el formulario de pago agregar "Cuántos períodos paga" (1, 2, 3, 6, 12 y anual). El monto se calcula solo (precio del plan × períodos) y se puede editar. Si el administrador lo configura, el pago anual puede tener un descuento (porcentaje o monto fijo por plan).
- Hoy, si se carga un monto mayor al precio del plan (por ejemplo 50.000 en un plan de 23.000), el sistema lo acepta sin avisar: cubre dos períodos y deja el sobrante a favor, pero no lo muestra. Si el monto cargado NO coincide con un múltiplo exacto del precio, mostrar una pantalla de confirmación clara: "Esto cubre X períodos y sobra $Y a favor" o "Falta $Z para el próximo período", y pedir confirmar.
- Después de guardar, mostrar siempre el resultado: vencimiento anterior, vencimiento nuevo, períodos cubiertos y saldo a favor o pendiente.
- El saldo a favor tiene que verse en la ficha del socio.
- Tests: 1, 2 y 12 períodos, anual con descuento, monto de más con sobrante, monto de menos (parcial, que ya existe), y anulación de un pago de varios períodos (el vencimiento se recalcula bien).

TAREA I. Lista de socios visible al elegir un socio
- En las pantallas donde hoy hay que buscar o escribir un socio (nuevo pago, renovar o asignar membresía, registrar ingreso en asistencia, venta en tienda con socio), mostrar debajo del buscador una lista de socios para elegir con un clic, sin tener que recordar el nombre.
- Cada fila muestra: foto chica (si tiene), nombre, DNI, plan y estado (vigente, por vencer, vencido) con color.
- Orden por defecto: vencidos y por vencer arriba, después alfabético. Que se pueda cambiar a solo alfabético.
- El buscador filtra la misma lista mientras se escribe (por nombre o DNI), sin recargar toda la página.
- Límite razonable por vez (50) con paginación o scroll, para que no se ponga lenta con cientos de socios.
- En celular, la lista se ve como tarjetas, una debajo de la otra, sin salirse de la pantalla (verificar a 390 px de ancho).
- Privacidad: la lista solo se muestra con sesión de administrador o recepción. En el kiosco NO aparece nunca.
- Tests: la lista aparece en cada una de esas pantallas, el filtro funciona por nombre y por DNI, respeta el orden, y el kiosco no la muestra.

TAREA J. Rediseño visual (EN ESPERA: no empezar hasta que yo lo pida)
- Cambiar el aspecto del sistema para que se vea más vivo, con más color, manteniendo la claridad. Referencia: el tema Bootswatch "<nombre del tema>" o la captura que te voy a pasar.
- Definir una paleta (color principal, color de acento y los de estado: verde = vigente, amarillo = por vencer, rojo = vencido) como variables CSS en un solo archivo.
- No cambiar la lógica ni los textos. Todas las pantallas (panel, socios, planes, pagos, asistencia, alertas, caja, tienda, kiosco, login) deben verse bien en PC y en celular de 390 px. Verificar con capturas.
- Bootstrap y las fuentes deben quedar dentro del proyecto (no por CDN) para que el sistema funcione sin internet.
- Mantener buen contraste y que el kiosco se lea a un metro.
- Tests: la suite sigue verde.