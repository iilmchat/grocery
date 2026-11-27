"""Восстановление fpgen/data/values.dat из values.dat.zst.

Camoufox падает с ValueError: Unable to create a ZSTDSeekContext,
если у .zst-файла нет встроенного индекса. fpgen умеет читать обычный
распакованный values.dat — создаём его рядом с архивом.
"""
from pathlib import Path

import zstandard

from fpgen.pkgman import VALUES_DATA

zst = VALUES_DATA.with_suffix(".dat.zst")
print("source:", zst, zst.stat().st_size)
data = zstandard.ZstdDecompressor().decompress(zst.read_bytes())
print("unpacked:", len(data))
VALUES_DATA.write_bytes(data)
print("written:", VALUES_DATA)
