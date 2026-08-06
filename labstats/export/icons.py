"""Minimal flat pictogram icons for the official PDF report, drawn locally
with Pillow (no external icon library / network fetch required). Each icon
is a colored circular badge with a simple white glyph, supersampled and
downscaled for smooth edges at print resolution.
"""
import io

from PIL import Image, ImageDraw

SUPERSAMPLE = 512
BADGE_BLUE = (30, 150, 210)
BADGE_NAVY = (20, 70, 110)
BADGE_AMBER = (200, 140, 20)
WHITE = (255, 255, 255, 255)


def _canvas():
    img = Image.new("RGBA", (SUPERSAMPLE, SUPERSAMPLE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _badge(draw, color):
    pad = 8
    draw.ellipse([pad, pad, SUPERSAMPLE - pad, SUPERSAMPLE - pad], fill=(*color, 255))


def _draw_person(draw):
    cx = SUPERSAMPLE / 2
    draw.ellipse([cx - 70, 130, cx + 70, 270], fill=WHITE)
    draw.pieslice([cx - 130, 240, cx + 130, 470], 180, 360, fill=WHITE)


def _draw_calendar(draw):
    left, top, right, bottom = 110, 140, 402, 400
    draw.rounded_rectangle([left, top, right, bottom], radius=24, outline=WHITE, width=22)
    draw.line([left, 210, right, 210], fill=WHITE, width=22)
    draw.line([170, 100, 170, 175], fill=WHITE, width=22)
    draw.line([342, 100, 342, 175], fill=WHITE, width=22)
    for gy in (260, 330):
        for gx in (170, 256, 342):
            draw.ellipse([gx - 14, gy - 14, gx + 14, gy + 14], fill=WHITE)


def _draw_test_tube(draw):
    cx = SUPERSAMPLE / 2
    draw.line([cx - 55, 110, cx + 55, 110], fill=WHITE, width=22)
    draw.rounded_rectangle([cx - 45, 110, cx + 45, 360], radius=45, outline=WHITE, width=22)
    draw.pieslice([cx - 45, 320, cx + 45, 410], 0, 180, fill=WHITE)
    draw.rectangle([cx - 33, 240, cx + 33, 320], fill=WHITE)


def _draw_clipboard(draw):
    left, top, right, bottom = 130, 110, 382, 410
    draw.rounded_rectangle([left, top, right, bottom], radius=20, outline=WHITE, width=22)
    cx = SUPERSAMPLE / 2
    draw.rounded_rectangle([cx - 55, 90, cx + 55, 150], radius=16, fill=WHITE)
    for ly in (200, 260, 320):
        draw.line([left + 40, ly, right - 40, ly], fill=WHITE, width=18)


def _draw_flask(draw):
    cx = SUPERSAMPLE / 2
    draw.line([cx - 40, 100, cx + 40, 100], fill=WHITE, width=22)
    draw.line([cx - 25, 100, cx - 25, 230], fill=WHITE, width=22)
    draw.line([cx + 25, 100, cx + 25, 230], fill=WHITE, width=22)
    draw.polygon(
        [(cx - 25, 230), (cx + 25, 230), (cx + 110, 400), (cx - 110, 400)],
        outline=WHITE,
        width=22,
    )
    draw.polygon([(cx - 80, 330), (cx + 80, 330), (cx + 110, 400), (cx - 110, 400)], fill=WHITE)


def _draw_box(draw):
    cx, cy = SUPERSAMPLE / 2, SUPERSAMPLE / 2
    top_pts = [(cx, cy - 150), (cx + 140, cy - 70), (cx, cy + 10), (cx - 140, cy - 70)]
    draw.polygon(top_pts, outline=WHITE, width=20)
    draw.line([cx - 140, cy - 70, cx - 140, cy + 90], fill=WHITE, width=20)
    draw.line([cx + 140, cy - 70, cx + 140, cy + 90], fill=WHITE, width=20)
    draw.line([cx, cy + 10, cx, cy + 170], fill=WHITE, width=20)
    draw.polygon([(cx - 140, cy + 90), (cx, cy + 170), (cx + 140, cy + 90), (cx, cy + 10)], outline=WHITE, width=20)


def _draw_grid(draw):
    cx, cy = SUPERSAMPLE / 2, SUPERSAMPLE / 2
    size, gap = 110, 20
    for dx in (-1, 1):
        for dy in (-1, 1):
            x0 = cx + dx * gap / 2 + (0 if dx > 0 else -size)
            y0 = cy + dy * gap / 2 + (0 if dy > 0 else -size)
            draw.rounded_rectangle([x0, y0, x0 + size, y0 + size], radius=14, fill=WHITE)


def _draw_warning(draw):
    cx = SUPERSAMPLE / 2
    draw.polygon([(cx, 100), (cx + 160, 400), (cx - 160, 400)], outline=WHITE, width=24)
    draw.line([cx, 190, cx, 300], fill=WHITE, width=26)
    draw.ellipse([cx - 15, 330, cx + 15, 360], fill=WHITE)


def _draw_clock(draw):
    cx, cy = SUPERSAMPLE / 2, SUPERSAMPLE / 2
    draw.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], outline=WHITE, width=24)
    draw.line([cx, cy, cx, cy - 100], fill=WHITE, width=20)
    draw.line([cx, cy, cx + 70, cy + 20], fill=WHITE, width=20)


_DRAWERS = {
    "patients": _draw_person,
    "visits": _draw_calendar,
    "samples": _draw_test_tube,
    "requests": _draw_clipboard,
    "tests": _draw_flask,
    "packages": _draw_box,
    "division": _draw_grid,
    "alert": _draw_warning,
    "average": _draw_clock,
}


def icon_png_bytes(name: str, badge_color=BADGE_BLUE, target_size=96) -> bytes:
    drawer = _DRAWERS.get(name, _draw_grid)
    img, draw = _canvas()
    _badge(draw, badge_color)
    drawer(draw)
    img = img.resize((target_size, target_size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
