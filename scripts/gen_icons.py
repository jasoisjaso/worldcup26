"""Generate WC26 PWA icons: soccer ball with green WC26 wordmark on dark background.
PIL-based, no external assets. Runs once at build time."""
from PIL import Image, ImageDraw, ImageFont
import math
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")

def draw_icon(size: int, path: str):
    img = Image.new("RGBA", (size, size), (4, 10, 10, 255))
    d = ImageDraw.Draw(img)

    cx, cy = size / 2, size / 2
    # Outer ring
    pad = size * 0.06
    d.ellipse([pad, pad, size - pad, size - pad], outline=(16, 185, 129, 255), width=max(2, size // 80))

    # Soccer ball pattern
    r = size * 0.38
    # Central pentagon
    pent_r = r * 0.32
    pts = []
    for i in range(5):
        ang = -math.pi / 2 + i * 2 * math.pi / 5
        pts.append((cx + pent_r * math.cos(ang), cy + pent_r * math.sin(ang)))
    d.polygon(pts, fill=(16, 185, 129, 255))

    # Hex patches around (simplified pentagon edges)
    hex_r = r * 0.78
    for i in range(5):
        ang = -math.pi / 2 + (i + 0.5) * 2 * math.pi / 5
        hx = cx + hex_r * math.cos(ang)
        hy = cy + hex_r * math.sin(ang)
        patch_r = r * 0.32
        ppts = []
        for j in range(6):
            pa = ang + j * math.pi / 3
            ppts.append((hx + patch_r * math.cos(pa), hy + patch_r * math.sin(pa)))
        d.polygon(ppts, fill=(7, 26, 18, 255), outline=(13, 51, 38, 255))

    # WC26 text below if size allows
    if size >= 192:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(size * 0.13))
            text = "WC26"
            bbox = d.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            d.text(((size - tw) / 2, size * 0.78), text, font=font, fill=(255, 255, 255, 255))
        except Exception:
            pass

    img.save(path, "PNG", optimize=True)
    print(f"Generated {path} ({size}x{size})")


def draw_maskable(size: int, path: str):
    """Maskable icon: same as regular but with 20% safe-zone padding."""
    img = Image.new("RGBA", (size, size), (4, 10, 10, 255))
    d = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    r = size * 0.3  # smaller for safe zone

    # Outer ring
    d.ellipse([cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3], outline=(16, 185, 129, 255), width=max(2, size // 80))
    # Central pentagon
    pent_r = r * 0.32
    pts = []
    for i in range(5):
        ang = -math.pi / 2 + i * 2 * math.pi / 5
        pts.append((cx + pent_r * math.cos(ang), cy + pent_r * math.sin(ang)))
    d.polygon(pts, fill=(16, 185, 129, 255))
    # Hex patches
    hex_r = r * 0.78
    for i in range(5):
        ang = -math.pi / 2 + (i + 0.5) * 2 * math.pi / 5
        hx = cx + hex_r * math.cos(ang)
        hy = cy + hex_r * math.sin(ang)
        patch_r = r * 0.32
        ppts = []
        for j in range(6):
            pa = ang + j * math.pi / 3
            ppts.append((hx + patch_r * math.cos(pa), hy + patch_r * math.sin(pa)))
        d.polygon(ppts, fill=(7, 26, 18, 255), outline=(13, 51, 38, 255))
    img.save(path, "PNG", optimize=True)
    print(f"Generated {path} ({size}x{size}) maskable")


if __name__ == "__main__":
    draw_icon(192, os.path.join(OUT, "icon-192.png"))
    draw_icon(512, os.path.join(OUT, "icon-512.png"))
    draw_maskable(192, os.path.join(OUT, "icon-maskable-192.png"))
    draw_maskable(512, os.path.join(OUT, "icon-maskable-512.png"))
    # Apple touch icon
    draw_icon(180, os.path.join(OUT, "apple-touch-icon.png"))
