"""Exportación a CSV."""
from datetime import timedelta

from app.services import memberships, payments
from conftest import HOY, hoy_real, leer_csv


def _armar_datos(db, plan, crear_socio):
    ana = crear_socio(nombre="Ana Paz", dni="30000001", telefono="+54 9 11 5555-1234", email="ana@ejemplo.com")
    memberships.asignar_plan(db, ana, plan, hoy_real() - timedelta(days=10))
    payments.registrar_pago(db, ana, 2500050, hoy_real(), "transferencia", "primer mes", confirmar=True)
    crear_socio(nombre="Beto Sin Plan", dni="30000002")
    return ana


def test_exporta_socios_en_csv(nav, db, plan, crear_socio):
    _armar_datos(db, plan, crear_socio)

    r = nav.get("/exportar/socios.csv")

    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/csv")
    assert "attachment" in r.headers["Content-Disposition"]
    assert f"socios_{hoy_real().isoformat()}.csv" in r.headers["Content-Disposition"]
    assert r.get_data().startswith(b"\xef\xbb\xbf")                      # BOM: Excel respeta tildes
    filas = leer_csv(r)
    assert filas[0][:3] == ["ID", "Nombre", "DNI"]
    assert len(filas) == 3                                              # encabezado + 2 socios
    ana = next(f for f in filas if f[1] == "Ana Paz")
    assert ana[2] == "30000001" and ana[6] == "activo" and ana[7] == "Mensual" and ana[9] == "vigente"
    assert ana[3] == "+54 9 11 5555-1234"                                # el + de un teléfono no se altera
    beto = next(f for f in filas if f[1] == "Beto Sin Plan")
    assert beto[7] == "" and beto[9] == "sin_membresia"


def test_exporta_pagos_en_csv(nav, db, plan, crear_socio):
    _armar_datos(db, plan, crear_socio)

    r = nav.get("/exportar/pagos.csv")

    assert r.status_code == 200 and r.headers["Content-Type"].startswith("text/csv")
    filas = leer_csv(r)
    assert filas[0][:9] == ["ID", "Fecha", "Socio", "DNI", "Monto (ARS)", "Método", "Plan", "Cubre hasta", "Nota"]
    assert len(filas) == 2
    pago = filas[1]
    assert pago[2] == "Ana Paz" and pago[3] == "30000001"
    assert pago[4] == "25000,50"                                         # coma decimal, como en Excel argentino
    assert pago[5] == "transferencia" and pago[6] == "Mensual" and pago[8] == "primer mes"


def test_csv_vacio_tiene_solo_encabezados(nav):
    assert len(leer_csv(nav.get("/exportar/socios.csv"))) == 1
    assert len(leer_csv(nav.get("/exportar/pagos.csv"))) == 1


def test_csv_neutraliza_formulas_de_excel(nav, db, crear_socio):
    crear_socio(nombre='=HYPERLINK("http://malo.example","clic")', dni="30000003")
    filas = leer_csv(nav.get("/exportar/socios.csv"))
    assert filas[1][1].startswith("'=")


def test_csv_requiere_sesion(anonimo):
    assert anonimo.get("/exportar/socios.csv").status_code == 302
    assert anonimo.get("/exportar/pagos.csv").status_code == 302


def test_servicio_de_exportacion_usa_la_fecha_pedida(db, plan, crear_socio):
    from app.services import exports
    socio_id = crear_socio()
    memberships.asignar_plan(db, socio_id, plan, HOY - timedelta(days=60))   # venció el 25/9
    filas = list(__import__("csv").reader(exports.socios_csv(db, HOY).lstrip("﻿").splitlines(), delimiter=";"))
    assert filas[1][9] == "vencida"
