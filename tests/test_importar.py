"""Importar socios desde CSV: vista previa, errores por línea y confirmación."""
import io
from pathlib import Path

import pytest

from app import models
from app.services import importar
from conftest import HOY

ENCABEZADO = "nombre;dni;telefono;email;fecha_alta;estado;notas"


def _csv(*filas, encabezado=ENCABEZADO, sep=";"):
    texto = "\r\n".join([encabezado, *filas]) + "\r\n"
    return texto.replace(";", sep).encode("utf-8")


def _analizar(db, contenido):
    return importar.analizar(db, contenido, hoy=HOY)


# ------------------------------------------------------------------------ análisis
def test_filas_validas_quedan_listas_para_importar(db):
    a = _analizar(db, _csv("Ana Paz;30.111.222;11 5555-1234;ANA@ejemplo.com;15/03/2025;pausado;Lesión de rodilla",
                           "Beto Gil;30111223;11 5555-9999;;;;"))

    assert a.puede_confirmar and a.total_filas == 2 and not a.errores
    ana, beto = a.validas
    assert ana["dni"] == "30111222"                      # sin puntos
    assert ana["email"] == "ana@ejemplo.com"
    assert ana["fecha_alta"] == "2025-03-15"             # dd/mm/aaaa -> ISO
    assert ana["estado"] == "pausado" and ana["notas"] == "Lesión de rodilla"
    assert beto["estado"] == "activo" and beto["fecha_alta"] == HOY.isoformat()   # valores por defecto
    assert a.lineas_validas == [2, 3]


@pytest.mark.parametrize("sep", [";", ",", "\t"])
def test_detecta_el_separador(db, sep):
    a = _analizar(db, _csv("Ana Paz;30111222;11 5555-1234;;;;", sep=sep))
    assert len(a.validas) == 1 and a.validas[0]["nombre"] == "Ana Paz"


def test_acepta_excel_con_bom_y_con_tildes(db):
    contenido = "﻿".encode("utf-8") + _csv("Zoé Ñandú;30111222;11 5555-1234;;;;")
    assert _analizar(db, contenido).validas[0]["nombre"] == "Zoé Ñandú"


def test_acepta_archivos_guardados_como_windows_1252(db):
    contenido = _csv("Zoé Ñandú;30111222;11 5555-1234;;;;").decode("utf-8").encode("cp1252")
    assert _analizar(db, contenido).validas[0]["nombre"] == "Zoé Ñandú"


def test_entiende_encabezados_con_otros_nombres(db):
    a = _analizar(db, _csv("Ana Paz;30111222;11 5555-1234;ana@x.com", encabezado="Nombre y Apellido;Documento;Teléfono;Correo"))
    assert a.puede_confirmar and a.validas[0]["email"] == "ana@x.com"


def test_ignora_lineas_en_blanco_y_cuenta_bien_los_numeros_de_linea(db):
    a = _analizar(db, _csv("Ana Paz;30111222;11 5555-1234;;;;", ";;;;;;", "", "Mal;123;11 5555-1234;;;;"))
    assert a.total_filas == 2
    assert a.errores[0].linea == 5                        # la línea real del archivo


def test_reporta_cada_error_con_su_linea_y_mensajes_claros(db, crear_socio):
    crear_socio(nombre="Ya Existe", dni="30000099")
    a = _analizar(db, _csv(
        "Ana Paz;30111222;11 5555-1234;;;;",              # 2 ok
        ";30111223;11 5555-1234;;;;",                     # 3 sin nombre
        "Beto;123;11 5555-1234;;;;",                      # 4 DNI inválido
        "Carla;30111224;;;;;",                            # 5 sin teléfono
        "Dani;30111225;11 5555-1234;no-es-mail;;;",       # 6 email inválido
        "Eli;30111226;11 5555-1234;;31/02/2025;;",        # 7 fecha inexistente
        "Fede;30111227;11 5555-1234;;;congelado;",        # 8 estado inválido
        "Gus;30000099;11 5555-1234;;;;",                  # 9 DNI ya registrado
        "Hugo;30111222;11 5555-1234;;;;",                 # 10 DNI repetido en el archivo
    ))

    assert [v["nombre"] for v in a.validas] == ["Ana Paz"]
    por_linea = {e.linea: " ".join(e.mensajes) for e in a.errores}
    assert sorted(por_linea) == [3, 4, 5, 6, 7, 8, 9, 10]
    assert "nombre" in por_linea[3].lower()
    assert "7 u 8 números" in por_linea[4]
    assert "teléfono" in por_linea[5].lower()
    assert "email" in por_linea[6].lower()
    assert "fecha de alta" in por_linea[7].lower()
    assert "estado" in por_linea[8].lower()
    assert "Ya existe un socio con ese DNI (Ya Existe)" in por_linea[9]
    assert "repetido en el archivo" in por_linea[10] and "línea 2" in por_linea[10]


def test_faltan_columnas_obligatorias(db):
    a = _analizar(db, b"nombre;email\r\nAna;ana@x.com\r\n")
    assert not a.puede_confirmar
    assert "faltan columnas obligatorias: dni, telefono" in a.problema_general


@pytest.mark.parametrize("contenido,mensaje", [
    (b"", "vacío"),
    (b"   \r\n  ", "vacío"),
    (ENCABEZADO.encode(), "ninguna fila con datos"),
    (b"x" * (importar.MAX_BYTES + 1), "demasiado grande"),
], ids=["vacio", "solo-espacios", "solo-encabezado", "demasiado-grande"])
def test_archivos_que_no_sirven(db, contenido, mensaje):
    a = _analizar(db, contenido)
    assert mensaje in a.problema_general and not a.puede_confirmar


def test_limite_de_filas(db, monkeypatch):
    monkeypatch.setattr(importar, "MAX_FILAS", 3)
    filas = [f"Socio {i};3011122{i};11 5555-1234;;;;" for i in range(4)]
    a = _analizar(db, _csv(*filas))
    assert "más de 3 filas" in a.problema_general and not a.validas


def test_un_archivo_con_solo_errores_no_se_puede_confirmar(db):
    a = _analizar(db, _csv("Mal;1;1;;;;"))
    assert not a.puede_confirmar and len(a.errores) == 1


def test_el_analisis_no_escribe_nada(db):
    _analizar(db, _csv("Ana Paz;30111222;11 5555-1234;;;;"))
    assert db.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 0


def test_importar_crea_los_socios_sin_plan(db):
    a = _analizar(db, _csv("Ana Paz;30111222;11 5555-1234;;;;", "Mal;1;1;;;;", "Beto Gil;30111223;11 5555-1234;;;;"))
    assert importar.importar(db, a) == 2
    ana = models.obtener_socio_por_dni(db, "30111222")
    assert ana["nombre"] == "Ana Paz" and ana["plan_nombre"] is None and ana["foto"] is None
    assert db.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 2


def test_importar_sin_filas_validas_falla(db):
    with pytest.raises(Exception, match="No hay filas válidas"):
        importar.importar(db, _analizar(db, _csv("Mal;1;1;;;;")))


# ------------------------------------------------------------------------- pantallas
def _subir(nav, contenido, nombre="socios.csv"):
    return nav.post("/datos/importar/", {"archivo": (io.BytesIO(contenido), nombre)})


def _token(html):
    import re
    return re.search(r'name="token" value="([0-9a-f]{32})"', html).group(1)


def test_la_pantalla_de_importar_explica_el_formato(nav):
    html = nav.get("/datos/importar/").get_data(as_text=True)
    assert "Importar socios desde un CSV" in html and "obligatorias" in html and "vista previa" in html


def test_la_vista_previa_muestra_validos_y_errores_y_no_guarda_nada(nav, db):
    r = _subir(nav, _csv("Ana Paz;30111222;11 5555-1234;;;;", "Mal;1;1;;;;"))
    html = r.get_data(as_text=True)

    assert "Vista previa de la importación" in html and "Todavía no se guardó nada" in html
    assert "Ana Paz" in html and "7 u 8 números" in html
    assert "Importar 1 socio" in html
    assert db.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 0


def test_confirmar_importa_las_filas_validas_y_avisa_las_omitidas(nav, db):
    html = _subir(nav, _csv("Ana Paz;30111222;11 5555-1234;;;;", "Beto Gil;30111223;11 5555-1234;;;;", "Mal;1;1;;;;")).get_data(as_text=True)

    r = nav.post("/datos/importar/confirmar", {"token": _token(html)}, follow_redirects=True)

    texto = r.get_data(as_text=True)
    assert "Se importaron 2 socios. Se omitieron 1 fila con errores." in texto
    assert db.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 2


def test_el_archivo_temporal_se_borra_al_confirmar_y_no_se_puede_confirmar_dos_veces(nav, db, app):
    html = _subir(nav, _csv("Ana Paz;30111222;11 5555-1234;;;;")).get_data(as_text=True)
    token = _token(html)
    carpeta = Path(app.config["IMPORT_DIR"])
    assert (carpeta / f"{token}.csv").is_file()

    nav.post("/datos/importar/confirmar", {"token": token})
    assert not (carpeta / f"{token}.csv").exists()

    otra = nav.post("/datos/importar/confirmar", {"token": token}, follow_redirects=True).get_data(as_text=True)
    assert "venció" in otra
    assert db.execute("SELECT COUNT(*) FROM socios").fetchone()[0] == 1


def test_se_revalida_al_confirmar_si_mientras_tanto_cargaron_el_mismo_dni(nav, db, crear_socio):
    html = _subir(nav, _csv("Ana Paz;30111222;11 5555-1234;;;;", "Beto Gil;30111223;11 5555-1234;;;;")).get_data(as_text=True)
    crear_socio(nombre="Llegó Antes", dni="30111222")          # alguien lo cargó entre la vista previa y la confirmación

    texto = nav.post("/datos/importar/confirmar", {"token": _token(html)}, follow_redirects=True).get_data(as_text=True)

    assert "Se importaron 1 socio. Se omitieron 1 fila" in texto
    assert models.obtener_socio_por_dni(db, "30111222")["nombre"] == "Llegó Antes"


@pytest.mark.parametrize("token", ["", "../../etc/passwd", "g" * 32, "a" * 31, "A" * 32])
def test_un_token_raro_se_rechaza(nav, token):
    html = nav.post("/datos/importar/confirmar", {"token": token}, follow_redirects=True).get_data(as_text=True)
    assert "ya no es válida" in html


def test_sin_archivo(nav):
    html = nav.post("/datos/importar/", {}, follow_redirects=True).get_data(as_text=True)
    assert "Elegí el archivo CSV" in html


def test_un_archivo_invalido_muestra_el_problema_y_no_ofrece_confirmar(nav):
    html = _subir(nav, b"nombre;email\r\nAna;a@x.com\r\n").get_data(as_text=True)
    assert "faltan columnas obligatorias" in html and "Importar " not in html.split("Probar con otro archivo")[0].split("Vista previa")[-1]
    assert 'name="token"' not in html


def test_recepcion_no_puede_importar(nav_recepcion):
    assert nav_recepcion.get("/datos/importar/").status_code == 403
    assert _subir(nav_recepcion, _csv("Ana Paz;30111222;11 5555-1234;;;;")).status_code == 403
