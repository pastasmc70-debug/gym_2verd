"""Carga datos de ejemplo: 3 planes, 30 socios con membresías en distintos estados y pagos.

Uso:
    python seed.py            # carga los datos (se niega si la base ya tiene socios)
    python seed.py --reset    # BORRA la base de datos y la vuelve a crear con los datos de ejemplo

Usa la base indicada en GYM_DB_PATH, o instance/gimnasio.db por defecto.
Los datos son siempre los mismos (semilla fija) pero se acomodan respecto de la fecha de hoy.
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from app import db as dbm
from app import models, timeutils
from app.services import memberships, payments

RAIZ = Path(__file__).resolve().parent

PLANES = [
    dict(nombre="Libre", precio_centavos=2800000, duracion_dias=30, clases_por_semana=None),
    dict(nombre="3 veces por semana", precio_centavos=2200000, duracion_dias=30, clases_por_semana=3),
    dict(nombre="2 veces por semana", precio_centavos=1800000, duracion_dias=30, clases_por_semana=2),
]

NOMBRES = ["Lucía", "Martín", "Camila", "Joaquín", "Valentina", "Santiago", "Sofía", "Mateo", "Julieta", "Nicolás",
           "Florencia", "Tomás", "Agustina", "Facundo", "Micaela", "Lautaro", "Rocío", "Franco", "Candela", "Bruno",
           "Paula", "Diego", "Carolina", "Federico", "Mariana", "Gonzalo", "Natalia", "Ezequiel", "Romina", "Ignacio"]
APELLIDOS = ["Gómez", "Rodríguez", "Fernández", "López", "Martínez", "Pérez", "González", "Sánchez", "Romero", "Díaz",
             "Sosa", "Álvarez", "Torres", "Ruiz", "Ramírez", "Flores", "Benítez", "Acosta", "Medina", "Herrera"]

# (cantidad, cómo se arma el vencimiento respecto de hoy, estado del socio)
#  vigente: vence entre 8 y 30 días; por vencer: entre 0 y 7; vencida: venció hace 1 a 45 días
GRUPOS = [
    (13, (8, 30), "activo"),
    (6, (0, 7), "activo"),
    (6, (-45, -1), "activo"),
    (2, (5, 25), "pausado"),
    (1, (-90, -60), "baja"),
    (2, None, "activo"),  # socios sin plan todavía
]
METODOS = ["efectivo", "efectivo", "transferencia", "transferencia", "tarjeta"]
USUARIO = "ejemplo"  # figura como «cargó» en pagos e ingresos de los datos de ejemplo


def hora_de_hoy_ya_pasada(rng, ahora: datetime) -> str:
    """Una hora de hoy que ya pasó: entre las 6:00 y ahora (o entre las 0:00 y ahora si todavía es de madrugada)."""
    tope = ahora.hour * 60 + ahora.minute
    piso = min(6 * 60, tope)
    minutos = rng.randint(piso, tope)
    return f"{minutos // 60:02d}:{minutos % 60:02d}:00"


def ruta_db() -> Path:
    return Path(os.environ.get("GYM_DB_PATH") or RAIZ / "instance" / "gimnasio.db")


def borrar_db(ruta: Path) -> None:
    for sufijo in ("", "-wal", "-shm"):
        Path(str(ruta) + sufijo).unlink(missing_ok=True)


def cargar(conn) -> dict:
    rng = random.Random(42)
    hoy = timeutils.hoy()

    planes = []
    with conn:
        for p in PLANES:
            planes.append(dict(p, id=models.crear_plan(conn, p)))

    nombres_usados, dnis_usados = set(), set()

    def socio_nuevo(estado, alta):
        while True:
            nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
            if nombre not in nombres_usados:
                nombres_usados.add(nombre)
                break
        while True:
            dni = str(rng.randint(20_000_000, 45_999_999))
            if dni not in dnis_usados:
                dnis_usados.add(dni)
                break
        mail = nombre.lower().replace(" ", ".").translate(str.maketrans("áéíóúñ", "aeioun"))
        datos = dict(nombre=nombre, dni=dni, telefono=f"11 {rng.randint(2000, 6999)}-{rng.randint(1000, 9999)}",
                     email=f"{mail}@ejemplo.com" if rng.random() < 0.7 else None,
                     fecha_alta=alta.isoformat(), estado=estado, foto=None, notas=None)
        with conn:
            return models.crear_socio(conn, datos)

    socios_con_ingreso_posible = []
    ejemplos = []  # socios al día, para mostrar un pago parcial y un pago anulado
    for cantidad, rango, estado in GRUPOS:
        for _ in range(cantidad):
            if rango is None:
                socio_nuevo(estado, hoy - timedelta(days=rng.randint(0, 3)))
                continue
            plan = rng.choice(planes)
            duracion = plan["duracion_dias"]
            vencimiento = hoy + timedelta(days=rng.randint(*rango))
            extras = rng.choice([0, 1, 2])  # renovaciones posteriores al primer pago
            inicio = vencimiento - timedelta(days=duracion * (extras + 1))
            socio_id = socio_nuevo("activo" if estado == "baja" else estado, inicio - timedelta(days=rng.randint(0, 20)))

            memberships.asignar_plan(conn, socio_id, plan["id"], inicio, cargada_por=USUARIO)

            # primer pago al inscribirse y una renovación por cada período extra
            fechas_pago = [inicio] + [inicio + timedelta(days=duracion * k) for k in range(1, extras + 1)]
            for fecha in fechas_pago:
                payments.registrar_pago(conn, socio_id, plan["precio_centavos"], fecha, rng.choice(METODOS),
                                        cargado_por=USUARIO)
            if estado == "baja":  # un socio de baja ya no se puede operar: se lo da de baja al final
                with conn:
                    conn.execute("UPDATE socios SET estado = 'baja' WHERE id = ?", (socio_id,))
            if estado == "activo" and vencimiento >= hoy:
                socios_con_ingreso_posible.append(socio_id)
                ejemplos.append((socio_id, plan))

    # Un pago parcial (queda con saldo pendiente) y un pago cargado dos veces por error y anulado.
    if len(ejemplos) >= 2:
        parcial_id, plan_parcial = ejemplos[0]
        payments.registrar_pago(conn, parcial_id, plan_parcial["precio_centavos"] // 3, hoy, "efectivo",
                                "Dejó una seña", cargado_por=USUARIO, confirmar_parcial=True)
        repetido_id, plan_repetido = ejemplos[1]
        duplicado = payments.registrar_pago(conn, repetido_id, plan_repetido["precio_centavos"], hoy,
                                            "transferencia", cargado_por=USUARIO)
        payments.anular_pago(conn, duplicado["pago_id"], "Pago cargado dos veces por error", USUARIO)

    # asistencias: hoy para algunos socios al día (a horas que ya pasaron) y algo de historia de la última semana
    ahora = timeutils.ahora()
    with conn:
        for i, socio_id in enumerate(socios_con_ingreso_posible):
            if i < 6:
                conn.execute("INSERT INTO asistencias (socio_id, fecha, hora, registrado_por) VALUES (?, ?, ?, ?)",
                             (socio_id, hoy.isoformat(), hora_de_hoy_ya_pasada(rng, ahora), USUARIO))
            for atras in rng.sample(range(1, 8), k=rng.randint(0, 4)):
                conn.execute("INSERT INTO asistencias (socio_id, fecha, hora, registrado_por) VALUES (?, ?, ?, ?)",
                             (socio_id, (hoy - timedelta(days=atras)).isoformat(), "18:30:00", USUARIO))

    return {
        "planes": conn.execute("SELECT COUNT(*) FROM planes").fetchone()[0],
        "socios": conn.execute("SELECT COUNT(*) FROM socios").fetchone()[0],
        "pagos": conn.execute("SELECT COUNT(*) FROM pagos").fetchone()[0],
        "asistencias": conn.execute("SELECT COUNT(*) FROM asistencias").fetchone()[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga datos de ejemplo en la base del gimnasio.")
    parser.add_argument("--reset", action="store_true", help="borra la base de datos actual antes de cargar")
    args = parser.parse_args()

    ruta = ruta_db()
    if args.reset:
        borrar_db(ruta)
    conn = dbm.connect(str(ruta))
    try:
        dbm.init_schema(conn)
        if conn.execute("SELECT COUNT(*) FROM socios").fetchone()[0] or conn.execute("SELECT COUNT(*) FROM planes").fetchone()[0]:
            print(f"La base {ruta} ya tiene datos. Si querés reemplazarlos por los de ejemplo, corré: python seed.py --reset",
                  file=sys.stderr)
            return 1
        totales = cargar(conn)
    finally:
        conn.close()
    print(f"Listo ({ruta}): {totales['planes']} planes, {totales['socios']} socios, "
          f"{totales['pagos']} pagos, {totales['asistencias']} asistencias.")
    return 0
    

if __name__ == "__main__":
    sys.exit(main())
