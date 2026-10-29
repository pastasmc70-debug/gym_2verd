"""Lógica de pagos, pagos parciales y anulaciones.

El vencimiento de una membresía NO se va sumando "a mano" cada vez: se calcula reproduciendo,
en orden, los pagos que no están anulados. Así, anular un pago (o cargar uno con fecha anterior)
deja siempre el vencimiento correcto.

Reglas:
  - Al asignar el plan, la membresía arranca con su primer período (inicio + duración + días
    acumulados de una membresía anterior).
  - Un período se "completa" cuando lo pagado alcanza el precio del plan (el que tenía al
    asignarlo). Un pago menor es PARCIAL: queda registrado, pero no extiende nada hasta que lo
    pagado completa el precio. Si se paga de más, el sobrante cuenta para el período siguiente.
  - El PRIMER período que se completa confirma el que se dio al asignar el plan: el vencimiento no
    cambia (si no, quien se inscribe y paga recibiría dos períodos por uno).
  - Los períodos siguientes suman la duración del plan a continuación del vencimiento actual
    (no se pierden días), o desde la fecha del pago si la membresía ya estaba vencida.
  - Pagos por varios períodos: se paga el monto (precio x períodos, editable). Si el monto NO es un múltiplo
    exacto de lo que falta, hay que confirmarlo (cubre X períodos y sobra $Y a favor, o falta $Z).
  - Pago anual: si el plan tiene descuento anual, el descuento cuenta como crédito del pago (no como plata
    que entró): monto_centavos es lo que se cobró y descuento_centavos lo que se perdonó. Se aplica solo si
    el monto alcanza el precio anual con descuento.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from .. import models, timeutils
from ..formatting import pesos
from .errors import ErrorDeNegocio, RequiereConfirmacion

MOTIVO_MAX = 300
PERIODOS_OPCIONES = (1, 2, 3, 6, 12)   # además de "anual"


def periodos_anuales(duracion_dias: int) -> int:
    """Cuántos períodos del plan hacen un año: 12 para un plan de 30 días, 52 para uno semanal, 1 para uno de 365."""
    return max(1, int(365 / max(1, duracion_dias) + 0.5))


def descuento_anual(precio_centavos: int, periodos: int, tipo, valor) -> int:
    """Descuento (en centavos) de pagar `periodos` períodos juntos. 0 si el plan no tiene descuento configurado."""
    bruto = precio_centavos * periodos
    if tipo == "porcentaje" and valor:
        d = bruto * int(valor) // 100
    elif tipo == "monto" and valor:
        d = int(valor)
    else:
        d = 0
    return d if 0 < d < bruto else 0   # un descuento que deja el pago en cero (o negativo) no es válido


def calcular_nuevo_vencimiento(vencimiento_actual: date, fecha_pago: date, duracion_dias: int,
                               es_primer_pago: bool) -> date:
    if es_primer_pago and vencimiento_actual >= fecha_pago:
        return vencimiento_actual
    base = vencimiento_actual if vencimiento_actual >= fecha_pago else fecha_pago
    return base + timedelta(days=duracion_dias)


@dataclass
class ResultadoPago:
    pago_id: int
    vencimiento_anterior: date
    vencimiento_nuevo: date
    periodos_completados: int      # períodos que completó este pago (0 = parcial)
    es_parcial: bool
    cubrio_periodo_inicial: bool
    saldo_pendiente_centavos: int = 0   # cómo quedó el socio justo después de este pago
    saldo_a_favor_centavos: int = 0


@dataclass
class EstadoMembresia:
    """Resultado de reproducir los pagos vigentes de una membresía."""
    vencimiento: date
    precio_centavos: int
    pagado_centavos: int = 0       # plata que entró de verdad (sin los descuentos)
    acumulado_centavos: int = 0    # lo pagado que todavía no completa el próximo período
    periodos_completados: int = 0
    ultimo_pago_parcial: bool = False
    pagos: list[ResultadoPago] = field(default_factory=list)

    @property
    def faltante_centavos(self) -> int:
        """Lo que falta pagar para completar el próximo período."""
        return self.precio_centavos - self.acumulado_centavos

    @property
    def saldo_pendiente_centavos(self) -> int:
        """Deuda visible: el período inicial sin completar, o un pago parcial a medio completar."""
        if self.periodos_completados == 0:
            return self.faltante_centavos
        if self.acumulado_centavos > 0 and self.ultimo_pago_parcial:
            return self.faltante_centavos
        return 0

    @property
    def saldo_a_favor_centavos(self) -> int:
        """Plata (o descuento) ya pagada que sobró después de completar períodos y todavía no completa el siguiente."""
        if self.periodos_completados > 0 and self.acumulado_centavos > 0 and not self.ultimo_pago_parcial:
            return self.acumulado_centavos
        return 0


@dataclass
class VistaPrevia:
    """Qué pasaría si se registrara un pago. No escribe nada."""
    periodos_cubiertos: int
    sobrante_centavos: int            # queda a favor del socio (solo si cubre al menos un período)
    faltante_proximo_centavos: int    # lo que falta para completar el período siguiente (0 si el pago es exacto)
    es_parcial: bool                  # no completa ningún período
    exacto: bool                      # cubre períodos enteros, sin sobrante ni faltante
    vencimiento_anterior: date
    vencimiento_nuevo: date
    descuento_centavos: int
    saldo_pendiente_centavos: int
    saldo_a_favor_centavos: int


def vencimiento_inicial(membresia) -> date:
    inicio = date.fromisoformat(membresia["fecha_inicio"])
    return inicio + timedelta(days=membresia["duracion_dias"] + (membresia["dias_extra"] or 0))


def reproducir(db, membresia_id: int, extra: list[dict] | None = None) -> EstadoMembresia:
    """Calcula el estado de la membresía a partir de sus pagos vigentes. No escribe nada.

    `extra` permite simular pagos que todavía no se guardaron (dicts con fecha, monto_centavos y
    descuento_centavos; sin "id"): se ubican donde les toca por fecha y quedan con pago_id None.
    """
    m = models.obtener_membresia(db, membresia_id)
    estado = EstadoMembresia(vencimiento=vencimiento_inicial(m), precio_centavos=m["precio_centavos"])
    pagos = [dict(id=p["id"], fecha=p["fecha"], monto_centavos=p["monto_centavos"],
                  descuento_centavos=p["descuento_centavos"] or 0)
             for p in models.pagos_activos_de_membresia(db, membresia_id)]
    for e in extra or []:
        pagos.append(dict(id=None, fecha=e["fecha"], monto_centavos=e["monto_centavos"],
                          descuento_centavos=e.get("descuento_centavos", 0)))
    pagos.sort(key=lambda p: (p["fecha"], float("inf") if p["id"] is None else p["id"]))
    for pago in pagos:
        anterior = estado.vencimiento
        fecha = date.fromisoformat(pago["fecha"])
        estado.pagado_centavos += pago["monto_centavos"]
        estado.acumulado_centavos += pago["monto_centavos"] + pago["descuento_centavos"]
        completados, inicial = 0, False
        while estado.acumulado_centavos >= estado.precio_centavos:
            estado.acumulado_centavos -= estado.precio_centavos
            primero = estado.periodos_completados == 0
            estado.vencimiento = calcular_nuevo_vencimiento(estado.vencimiento, fecha, m["duracion_dias"], primero)
            estado.periodos_completados += 1
            completados += 1
            inicial = inicial or (primero and estado.vencimiento == anterior)
        estado.ultimo_pago_parcial = completados == 0
        estado.pagos.append(ResultadoPago(pago["id"], anterior, estado.vencimiento, completados,
                                          completados == 0, inicial,
                                          estado.saldo_pendiente_centavos, estado.saldo_a_favor_centavos))
    return estado


def previsualizar_pago(db, membresia_id: int, monto_centavos: int, fecha: date,
                       descuento_centavos: int = 0) -> VistaPrevia:
    """Resultado de registrar un pago con estos datos, sin guardarlo."""
    estado = reproducir(db, membresia_id, [dict(fecha=fecha.isoformat(), monto_centavos=monto_centavos,
                                                descuento_centavos=descuento_centavos)])
    mio = next(r for r in estado.pagos if r.pago_id is None)
    cubiertos = mio.periodos_completados
    resto = estado.acumulado_centavos
    return VistaPrevia(
        periodos_cubiertos=cubiertos,
        sobrante_centavos=resto if cubiertos else 0,
        faltante_proximo_centavos=estado.precio_centavos - resto if resto else 0,
        es_parcial=cubiertos == 0,
        exacto=cubiertos > 0 and resto == 0,
        vencimiento_anterior=mio.vencimiento_anterior,
        vencimiento_nuevo=mio.vencimiento_nuevo,
        descuento_centavos=descuento_centavos,
        saldo_pendiente_centavos=mio.saldo_pendiente_centavos,
        saldo_a_favor_centavos=mio.saldo_a_favor_centavos,
    )


def opciones_de_periodos(membresia, estado: EstadoMembresia) -> list[dict]:
    """Opciones del selector "Cuántos períodos paga", con el monto sugerido de cada una.

    Monto = precio x períodos, menos lo que ya hay acumulado (un parcial a medio completar o un saldo a favor),
    así que sin saldos es exactamente precio x períodos. La opción anual descuenta además el descuento del plan.
    """
    precio, acumulado = estado.precio_centavos, estado.acumulado_centavos
    opciones = [dict(valor=str(n), periodos=n, etiqueta="1 período" if n == 1 else f"{n} períodos",
                     monto_centavos=n * precio - acumulado, descuento_centavos=0)
                for n in PERIODOS_OPCIONES]
    n = periodos_anuales(membresia["duracion_dias"])
    d = descuento_anual(precio, n, membresia["descuento_anual_tipo"], membresia["descuento_anual_valor"])
    opciones.append(dict(valor="anual", periodos=n, etiqueta=f"Anual ({n} períodos)",
                         monto_centavos=n * precio - d - acumulado, descuento_centavos=d))
    return opciones


def descuento_que_corresponde(membresia, estado: EstadoMembresia, monto_centavos: int) -> int:
    """Descuento de un pago anual: el del plan, pero solo si el monto alcanza el precio anual con descuento."""
    n = periodos_anuales(membresia["duracion_dias"])
    d = descuento_anual(estado.precio_centavos, n, membresia["descuento_anual_tipo"], membresia["descuento_anual_valor"])
    if d and monto_centavos >= n * estado.precio_centavos - d - estado.acumulado_centavos:
        return d
    return 0


def resumen_de_pago(db, pago_id: int):
    """El pago y cómo dejó al socio (vencimientos, períodos, saldos). None si no existe o está anulado."""
    pago = models.obtener_pago(db, pago_id)
    if pago is None or pago["anulado"]:
        return None
    estado = reproducir(db, pago["membresia_id"])
    resultado = next((r for r in estado.pagos if r.pago_id == pago_id), None)
    return {"pago": pago, "resultado": resultado, "precio_centavos": estado.precio_centavos} if resultado else None


def recalcular_membresia(db, membresia_id: int) -> EstadoMembresia:
    """Reproduce los pagos y guarda el resultado (vencimiento de la membresía y de cada pago).

    No hace commit: quien llama decide la transacción.
    """
    estado = reproducir(db, membresia_id)
    for r in estado.pagos:
        db.execute("UPDATE pagos SET vencimiento_anterior = ?, vencimiento_nuevo = ?, es_parcial = ? WHERE id = ?",
                   (r.vencimiento_anterior.isoformat(), r.vencimiento_nuevo.isoformat(), int(r.es_parcial), r.pago_id))
    db.execute("UPDATE membresias SET fecha_vencimiento = ? WHERE id = ?",
               (estado.vencimiento.isoformat(), membresia_id))
    return estado


def es_primer_pago(db, membresia_id: int) -> bool:
    return db.execute("SELECT COUNT(*) FROM pagos WHERE membresia_id = ? AND anulado = 0",
                      (membresia_id,)).fetchone()[0] == 0


def tiene_pago_vigente(db, membresia_id: int) -> bool:
    return not es_primer_pago(db, membresia_id)


def saldo_del_socio(db, socio_id: int) -> int:
    """Saldo pendiente (en centavos) de la membresía actual del socio; 0 si no debe nada."""
    actual = models.membresia_actual(db, socio_id)
    return reproducir(db, actual["id"]).saldo_pendiente_centavos if actual else 0


def registrar_pago(db, socio_id: int, monto_centavos: int, fecha: date, metodo: str,
                   nota: str | None = None, cargado_por: str | None = None,
                   confirmar_parcial: bool = False, *, anual: bool = False, confirmar: bool = False) -> dict:
    """Registra un pago. Si el monto no es un múltiplo exacto de lo que falta, exige confirmarlo.

    Pago parcial (no completa ningún período): código "pago_parcial". Pago que cubre períodos pero deja
    sobrante: código "pago_sobrante". `confirmar` (o su nombre anterior `confirmar_parcial`) los acepta.
    `anual=True` aplica el descuento anual del plan, si lo tiene y el monto alcanza.
    """
    if monto_centavos <= 0:
        raise ErrorDeNegocio("El monto tiene que ser mayor a cero.", "monto")
    if metodo not in models.METODOS_PAGO:
        raise ErrorDeNegocio("El método de pago no es válido.", "metodo")

    socio = models.obtener_socio(db, socio_id)
    if socio is None:
        raise ErrorDeNegocio("No encontramos al socio.", "socio")
    if socio["estado"] == "baja":
        raise ErrorDeNegocio("El socio está dado de baja. Reactivalo antes de registrarle un pago.", "baja")

    membresia = models.membresia_actual(db, socio_id)
    if membresia is None:
        raise ErrorDeNegocio("El socio todavía no tiene un plan. Asignale uno antes de registrar el pago.", "sin_plan")

    antes = reproducir(db, membresia["id"])
    descuento = descuento_que_corresponde(membresia, antes, monto_centavos) if anual else 0
    vista = previsualizar_pago(db, membresia["id"], monto_centavos, fecha, descuento)
    if not vista.exacto and not (confirmar or confirmar_parcial):
        datos = dict(faltante_centavos=antes.faltante_centavos, monto_centavos=monto_centavos, vista=vista,
                     periodos_cubiertos=vista.periodos_cubiertos, sobrante_centavos=vista.sobrante_centavos,
                     faltante_proximo_centavos=vista.faltante_proximo_centavos, descuento_centavos=descuento)
        if vista.es_parcial:
            raise RequiereConfirmacion(
                "El monto es menor a lo que falta para completar el período. "
                "Se registraría como pago parcial y no extendería la membresía.", "pago_parcial", **datos)
        raise RequiereConfirmacion(
            f"Esto cubre {vista.periodos_cubiertos} período(s) y sobran {pesos(vista.sobrante_centavos)} a favor.",
            "pago_sobrante", **datos)

    with db:  # una sola transacción: o se guardan las dos cosas o ninguna
        cur = db.execute(
            """INSERT INTO pagos (socio_id, membresia_id, monto_centavos, fecha, metodo, nota,
                                  vencimiento_anterior, vencimiento_nuevo, creado_en, cargado_por,
                                  descuento_centavos)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (socio_id, membresia["id"], monto_centavos, fecha.isoformat(), metodo, nota,
             antes.vencimiento.isoformat(), antes.vencimiento.isoformat(),
             timeutils.ahora().isoformat(timespec="seconds"), cargado_por, descuento),
        )
        despues = recalcular_membresia(db, membresia["id"])

    mio = next(r for r in despues.pagos if r.pago_id == cur.lastrowid)
    return {
        "pago_id": mio.pago_id,
        "vencimiento_anterior": mio.vencimiento_anterior,
        "vencimiento_nuevo": mio.vencimiento_nuevo,
        "plan_nombre": membresia["plan_nombre"],
        "cubrio_periodo_inicial": mio.cubrio_periodo_inicial,
        "es_parcial": mio.es_parcial,
        "periodos_cubiertos": mio.periodos_completados,
        "descuento_centavos": descuento,
        "saldo_pendiente_centavos": despues.saldo_pendiente_centavos,
        "saldo_a_favor_centavos": despues.saldo_a_favor_centavos,
        "faltante_centavos": despues.faltante_centavos,
    }


def _validar_motivo(motivo) -> str:
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorDeNegocio("Escribí el motivo de la anulación.", "motivo")
    if len(motivo) > MOTIVO_MAX:
        raise ErrorDeNegocio(f"El motivo es demasiado largo (máximo {MOTIVO_MAX} caracteres).", "motivo")
    return motivo


def anular_pago(db, pago_id: int, motivo: str, usuario: str) -> dict:
    """Marca el pago como anulado (no se borra) y recalcula el vencimiento de su membresía."""
    motivo = _validar_motivo(motivo)
    pago = models.obtener_pago(db, pago_id)
    if pago is None:
        raise ErrorDeNegocio("No encontramos el pago.", "pago")
    if pago["anulado"]:
        raise ErrorDeNegocio("Ese pago ya estaba anulado.", "ya_anulado")

    with db:
        db.execute(
            "UPDATE pagos SET anulado = 1, anulado_en = ?, anulado_por = ?, anulado_motivo = ? WHERE id = ?",
            (timeutils.ahora().isoformat(timespec="seconds"), usuario, motivo, pago_id),
        )
        estado = recalcular_membresia(db, pago["membresia_id"])
    return {"vencimiento": estado.vencimiento, "socio_id": pago["socio_id"], "pago": pago}


def anular_membresia(db, membresia_id: int, motivo: str, usuario: str) -> dict:
    """Anula una membresía asignada por error. Si tiene pagos vigentes, primero hay que anularlos."""
    motivo = _validar_motivo(motivo)
    m = models.obtener_membresia(db, membresia_id)
    if m is None:
        raise ErrorDeNegocio("No encontramos la membresía.", "membresia")
    if m["anulada"]:
        raise ErrorDeNegocio("Esa membresía ya estaba anulada.", "ya_anulada")
    if not es_primer_pago(db, membresia_id):
        raise ErrorDeNegocio(
            "Esta membresía tiene pagos registrados. Primero anulá esos pagos y después la membresía.",
            "con_pagos",
        )
    with db:
        db.execute(
            "UPDATE membresias SET anulada = 1, anulada_en = ?, anulada_por = ?, anulada_motivo = ? WHERE id = ?",
            (timeutils.ahora().isoformat(timespec="seconds"), usuario, motivo, membresia_id),
        )
    return {"socio_id": m["socio_id"], "membresia": m}
