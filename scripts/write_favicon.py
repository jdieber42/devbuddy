#!/usr/bin/env python3
import base64
import os

png_b64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII="
)
png = base64.b64decode(png_b64)

# ICO header for single image
header = b"\x00\x00\x01\x00\x01\x00"
# ICONDIRENTRY: width, height, colorCount, reserved, planes (2 bytes), bitCount (2 bytes), bytesInRes (4), imageOffset (4)
entry = (
    bytes([1, 1, 0, 0])
    + (0).to_bytes(2, "little")
    + (0).to_bytes(2, "little")
    + len(png).to_bytes(4, "little")
    + (6 + 16).to_bytes(4, "little")
)

ico = header + entry + png
out_path = os.path.join("app", "static", "favicon.ico")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "wb") as f:
    f.write(ico)
print("Wrote", out_path)
