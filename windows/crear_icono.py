"""Dibuja windows/icono.ico (una pesa sobre fondo azul). Solo hace falta correrlo si se quiere cambiar el ícono:
  pip install pillow && python windows/crear_icono.py
Pillow no es una dependencia del programa."""
from pathlib import Path

from PIL import Image, ImageDraw

TAMANOS = [16, 24, 32, 48, 64, 128, 256]


def dibujar(n: int) -> Image.Image:
    g = 1024  # se dibuja grande y se reduce para que los bordes salgan suaves
    img = Image.new("RGBA", (g, g), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, g - 1, g - 1), radius=g // 5, fill=(24, 90, 157, 255))
    blanco = (255, 255, 255, 255)
    d.rounded_rectangle((300, 470, 724, 554), radius=40, fill=blanco)             # barra
    for x0, x1, alto in ((200, 290, 330), (120, 190, 220)):                       # discos de la izquierda
        d.rounded_rectangle((x0, 512 - alto // 2, x1, 512 + alto // 2), radius=36, fill=blanco)
    for x0, x1, alto in ((734, 824, 330), (834, 904, 220)):                       # discos de la derecha
        d.rounded_rectangle((x0, 512 - alto // 2, x1, 512 + alto // 2), radius=36, fill=blanco)
    return img.resize((n, n), Image.LANCZOS)


if __name__ == "__main__":
    destino = Path(__file__).with_name("icono.ico")
    dibujar(256).save(destino, format="ICO", sizes=[(n, n) for n in TAMANOS], append_images=[dibujar(n) for n in TAMANOS if n != 256])
    print("Ícono creado:", destino)
