#!/usr/bin/env python3
"""Erzeugt das App-Symbol (Web + Android) ohne Zusatzbibliotheken.

Violettes Feld mit drei Figuren (zwei Erwachsene, ein Kind).
Aufruf aus app/: python3 tool/make_icons.py
"""
import struct
import zlib
from pathlib import Path

TOP, BOTTOM = (0x7C, 0x3A, 0xED), (0x4C, 0x1D, 0x95)
WHITE = (255, 255, 255)
SS = 3  # Supersampling für weiche Kanten

# Figuren im Einheitsquadrat: (kopf_x, kopf_y, kopf_r, körper_x0, körper_y0, körper_x1, körper_y1)
FIGURES = [
    (0.33, 0.33, 0.085, 0.24, 0.45, 0.42, 0.74),
    (0.67, 0.33, 0.085, 0.58, 0.45, 0.76, 0.74),
    (0.50, 0.50, 0.065, 0.435, 0.59, 0.565, 0.74),
]


def inside_figure(x, y):
    for hx, hy, hr, x0, y0, x1, y1 in FIGURES:
        if (x - hx) ** 2 + (y - hy) ** 2 <= hr * hr:
            return True
        r = (x1 - x0) / 2  # Körper oben abgerundet
        if x0 <= x <= x1 and y0 + r <= y <= y1:
            return True
        if (x - (x0 + r)) ** 2 + (y - (y0 + r)) ** 2 <= r * r:
            return True
    return False


def inside_rounded(x, y, radius):
    if radius == 0:
        return True
    cx = min(max(x, radius), 1 - radius)
    cy = min(max(y, radius), 1 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius


def render(size, full_bleed=False):
    """full_bleed: ganze Fläche gefüllt, Motiv kleiner (maskable/Apple)."""
    radius = 0.0 if full_bleed else 0.22
    scale = 0.8 if full_bleed else 1.0
    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            r = g = b = a = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    x = (px + (sx + 0.5) / SS) / size
                    y = (py + (sy + 0.5) / SS) / size
                    if not inside_rounded(x, y, radius):
                        continue
                    if inside_figure((x - 0.5) / scale + 0.5, (y - 0.5) / scale + 0.5):
                        c = WHITE
                    else:
                        c = tuple(TOP[i] + (BOTTOM[i] - TOP[i]) * y for i in range(3))
                    r += c[0]; g += c[1]; b += c[2]; a += 1
            if a:
                row += bytes([round(r / a), round(g / a), round(b / a), round(255 * a / (SS * SS))])
            else:
                row += bytes(4)
        rows.append(bytes(row))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def main():
    out = {
        "web/favicon.png": (64, False),
        "web/icons/Icon-192.png": (192, False),
        "web/icons/Icon-512.png": (512, False),
        "web/icons/Icon-maskable-192.png": (192, True),
        "web/icons/Icon-maskable-512.png": (512, True),
        "web/icons/apple-touch-icon.png": (180, True),
    }
    for density, size in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        out[f"android/app/src/main/res/mipmap-{density}/ic_launcher.png"] = (size, False)
    for path, (size, full) in out.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(render(size, full))
        print(path, size)


if __name__ == "__main__":
    main()
