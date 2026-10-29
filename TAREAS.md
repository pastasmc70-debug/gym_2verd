COLA DE TAREAS (orden obligatorio: E, A, F, B, D, G, C)

TAREA E. Arreglo visual
- En el panel de inicio, en celular, los montos grandes se parten en varias líneas (ej. "$ 378.00 / 0"). Corregir con tamaño de letra fluido o sin corte. Verificar con captura en 390 px de ancho.

TAREA A. Cuentas de usuario
- Hoy hay un administrador y una sola cuenta de recepción fija en variables de entorno. Pasar a usuarios en la base de datos, con migración que no pierda datos.
- El administrador crea, desactiva (no borra) y cambia la clave de cada recepcionista desde una pantalla. Claves siempre con hash.
- Cada pago, anulación, venta, ingreso e importación queda con el nombre de quien lo hizo, visible donde hoy se muestra "quién".
- Compatibilidad: si existen GYM_RECEPCION_USER y GYM_RECEPCION_PASSWORD_HASH, importarlos como primer usuario de recepción.
- Tests: permisos, desactivación, migración, y que recepción no pueda crear usuarios.

TAREA F. Asistente de primera vez (reemplaza las variables de entorno)
- Si no hay administrador, la primera vez que se abre aparece un asistente de 4 pasos: (1) nombre del gimnasio, (2) usuario y clave del administrador (mínimo 10 caracteres, con confirmación), (3) planes con precio y duración, (4) activar o no la tienda de suplementos.
- La SECRET_KEY se genera sola (secrets.token_hex(32)) y se guarda en la carpeta de datos. Nadie la ve ni la escribe.
- La configuración (nombre, tienda, kiosco, reglas de ingreso) pasa de variables de entorno a una pantalla "Configuración" del administrador, guardada en la base. Las variables de entorno siguen funcionando como alternativa.
- NO agregar nada de molinetes ni hardware.
- Tests: el asistente no se puede repetir si ya hay administrador, claves cortas rechazadas, la configuración persiste.

TAREA B. Socios adentro ahora (estimado)
- No pedir marcar la salida. En el panel mostrar "Adentro ahora (aprox.)": socios con ingreso en las últimas N horas, N configurable (por defecto 2) desde Configuración. Debe decir "aprox." en pantalla y en el README. No contar ingresos anulados ni duplicar al mismo socio. Tests con horarios límite.

TAREA D. Tarjeta de ingreso en recepción
- En asistencia (recepción), al registrar un ingreso mostrar una tarjeta con foto, nombre, plan, estado y días restantes, y si debe una cuota parcial. Verificarla con captura en navegador real, en PC y en celular.

TAREA G. Copia de seguridad automática
- Backup diario automático a una carpeta que el dueño elige en Configuración (puede ser una carpeta sincronizada de Google Drive, OneDrive o un pendrive). Conservar las últimas 14 copias. Mostrar en el panel la fecha de la última copia y avisar si hace más de 3 días que no se hace.

TAREA C. Empaquetado para Windows
- C1. PyInstaller (modo carpeta) en un ejecutable con ventana propia (pywebview o equivalente), con ícono .ico, sin barra de navegador. Al cerrar la ventana se apaga el servidor. No requiere Python instalado.
- C2. Instalador con Inno Setup ("Siguiente, Siguiente, Finalizar"), con acceso directo en escritorio y menú inicio, y desinstalador que NO borra los datos.
- C3. Los datos (base, fotos, copias) viven en una carpeta aparte (%PROGRAMDATA% o %APPDATA%), nunca dentro de la carpeta del programa.
- C4. Workflow de GitHub Actions (runner windows-latest) que arme el instalador y lo deje como artefacto descargable. Documentar cómo ejecutarlo.
- C5. La app muestra su versión y se actualiza ejecutando un instalador nuevo sin perder datos.
- C6. Android (APK) y PWA quedan para DESPUÉS: no implementarlos ahora.
- Todo lo que no se pueda probar acá (Windows real) queda PENDIENTE con pasos manuales.
