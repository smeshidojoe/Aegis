"""
Генератор картинок проекта:

    assets/app.ico           — иконка exe и трея (9 размеров)
    assets/icon.png          — иконка 1024x1024 для страницы на GitHub
    extension/icons/*.png    — иконки расширения браузера

Иконку рисует тот же код, что и в рантайме (aegis/ui/appicon.py), поэтому
файл и программа не разъезжаются. Каждый размер ico рендерится отдельно, а не
ужимается из 1024: ужатая версия на 16x16 превращается в кашу.

    python tools/make_assets.py
    (нужен Pillow: pip install pillow — только для записи .ico)
"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ICO_SIZES = [256, 128, 64, 48, 40, 32, 24, 20, 16]
EXTENSION_SIZES = [16, 32, 48, 128]


def _png_bytes(pixmap):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


def main():
    from PIL import Image

    QApplication.instance() or QApplication([])
    from aegis.ui import appicon

    assets = os.path.join(ROOT, "assets")
    os.makedirs(assets, exist_ok=True)
    frames = [Image.open(io.BytesIO(_png_bytes(appicon.pixmap(s)))).convert("RGBA")
              for s in ICO_SIZES]
    frames[0].save(os.path.join(assets, "app.ico"), format="ICO",
                   sizes=[(f.width, f.height) for f in frames], append_images=frames[1:])
    appicon.pixmap(1024).save(os.path.join(assets, "icon.png"))

    icons = os.path.join(ROOT, "extension", "icons")
    os.makedirs(icons, exist_ok=True)
    for size in EXTENSION_SIZES:
        appicon.pixmap(size).save(os.path.join(icons, "icon%d.png" % size))
    print("app.ico, icon.png, extension/icons")


if __name__ == "__main__":
    main()
