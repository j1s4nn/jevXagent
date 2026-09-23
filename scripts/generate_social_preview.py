import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow is not installed. Run:  pip install pillow")
    sys.exit(1)

WIDTH, HEIGHT = 1280, 640
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"
OUT = OUT_DIR / "social_preview.png"

BG_TOP = (13, 17, 23)
BG_BOTTOM = (28, 35, 51)
INK = (236, 239, 246)
MUTED = (150, 158, 172)
ACCENT_A = (245, 124, 42)
ACCENT_B = (255, 198, 71)
BOX_FILL = (33, 40, 56)
BOX_EDGE = (90, 100, 120)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def vertical_gradient(width, height, top, bottom):
    image = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / (height - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def center_text(draw, text, font, cx, cy, fill):
    w = draw.textlength(text, font=font)
    draw.text((cx - w / 2, cy), text, font=font, fill=fill)


def main():
    image = vertical_gradient(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM)

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [WIDTH * 0.52, -140, WIDTH * 1.18, HEIGHT * 0.78],
        fill=(255, 132, 50, 34),
    )
    glow_draw.ellipse(
        [WIDTH * 0.66, 60, WIDTH * 1.05, HEIGHT * 0.62],
        fill=(255, 190, 80, 26),
    )
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")

    draw = ImageDraw.Draw(image)

    font_badge = load_font(30)
    font_title = load_font(128)
    font_tagline = load_font(58)
    font_sub = load_font(27)
    font_box = load_font(26)
    font_footer = load_font(22)

    draw.text((78, 84), "LOCAL LLM PROXY  ·  AI AGENT MIDDLEWARE", font=font_badge, fill=ACCENT_B)

    draw.text((74, 138), "jevXagent", font=font_title, fill=INK)

    draw.text((76, 306), "When Jev meets LLM", font=font_tagline, fill=ACCENT_A)

    draw.text(
        (78, 388),
        "Claude Code  ·  Decision Routing  ·  Telemetry  ·  Statistics  ·  Benchmarking",
        font=font_sub,
        fill=MUTED,
    )

    labels = ["LLM AGENT", "JEVXAGENT", "JEV / CLAUDE"]
    box_w, box_h, gap = 200, 64, 110
    total_w = len(labels) * box_w + (len(labels) - 1) * gap
    start_x = (WIDTH - total_w) / 2
    y = 500

    for i, label in enumerate(labels):
        x = start_x + i * (box_w + gap)
        fill = BOX_FILL if i != 1 else (70, 52, 30)
        edge = BOX_EDGE if i != 1 else ACCENT_A
        draw.rounded_rectangle(
            [x, y, x + box_w, y + box_h], radius=12, fill=fill, outline=edge, width=2
        )
        center_text(
            draw, label, font_box, x + box_w / 2, y + box_h / 2 - 15,
            INK if i != 1 else ACCENT_B,
        )
        if i < len(labels) - 1:
            arrow_x = x + box_w + 10
            draw.line(
                [(arrow_x, y + box_h / 2), (arrow_x + gap - 20, y + box_h / 2)],
                fill=MUTED,
                width=3,
            )
            draw.polygon(
                [
                    (arrow_x + gap - 20, y + box_h / 2 - 7),
                    (arrow_x + gap - 20, y + box_h / 2 + 7),
                    (arrow_x + gap - 8, y + box_h / 2),
                ],
                fill=MUTED,
            )

    draw.text((78, 598), "github.com/j1s4nn/jevXagent", font=font_footer, fill=MUTED)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    image.save(OUT, format="PNG")
    print(f"Saved {WIDTH}x{HEIGHT} PNG to: {OUT}")


if __name__ == "__main__":
    main()
