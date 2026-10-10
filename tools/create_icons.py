"""Render the two CT2Trainer Windows icons from the same vector-like shapes.

Requires Pillow at build time. The committed PNG and ICO files do not need it.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1] / "src" / "ct2trainer" / "assets"
SIZE = 1024
SCALE = SIZE / 256


def box(*values: int) -> tuple[int, ...]:
    return tuple(round(value * SCALE) for value in values)


def points(values: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [box(x, y) for x, y in values]


def base() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box(9, 9, 247, 247), radius=box(52)[0], fill="#111B2C")
    # Broad, quiet bands keep the icon legible at 16 px.
    draw.rounded_rectangle(box(11, 11, 245, 245), radius=box(50)[0],
                           outline="#35516B", width=box(4)[0])
    draw.arc(box(25, 25, 231, 231), 196, 312, fill="#48627A", width=box(3)[0])
    return image


def converter() -> Image.Image:
    image = base()
    shadow = Image.new("RGBA", image.size)
    s = ImageDraw.Draw(shadow)
    s.rounded_rectangle(box(53, 48, 166, 211), radius=box(14)[0], fill="#000000")
    shadow = shadow.filter(ImageFilter.GaussianBlur(box(7)[0]))
    image = Image.alpha_composite(image, Image.blend(Image.new("RGBA", image.size), shadow, 0.30))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box(53, 48, 166, 211), radius=box(14)[0],
                           fill="#23384C", outline="#6DE2DC", width=box(7)[0])
    draw.line(points([(73, 81), (134, 81)]), fill="#DDF9F4", width=box(7)[0])
    draw.line(points([(73, 110), (116, 110)]), fill="#B3C5D5", width=box(7)[0])
    draw.line(points([(73, 139), (108, 139)]), fill="#B3C5D5", width=box(7)[0])
    # The bright arrow denotes conversion from a table to a runnable trainer.
    draw.rounded_rectangle(box(113, 159, 194, 178), radius=box(9)[0], fill="#F5A34B")
    draw.polygon(points([(173, 137), (219, 169), (173, 201)]), fill="#FFC075")
    draw.line(points([(115, 169), (185, 169)]), fill="#FFDDB3", width=box(4)[0])
    return image


def trainer() -> Image.Image:
    image = base()
    draw = ImageDraw.Draw(image)
    shield = points([(128, 39), (207, 73), (197, 157), (176, 191),
                     (128, 220), (80, 191), (59, 157), (49, 73)])
    draw.polygon(shield, fill="#23384C")
    draw.line(shield + [shield[0]], fill="#6DE2DC", width=box(8)[0], joint="curve")
    inner = points([(128, 61), (184, 84), (178, 151), (161, 176),
                    (128, 198), (95, 176), (78, 151), (72, 84)])
    draw.line(inner + [inner[0]], fill="#45667C", width=box(3)[0], joint="curve")
    bolt = points([(136, 72), (99, 132), (126, 132), (112, 182),
                   (167, 112), (139, 112), (154, 72)])
    draw.polygon(bolt, fill="#FFC075")
    draw.line(points([(100, 132), (126, 132), (112, 182)]),
              fill="#F5A34B", width=box(2)[0], joint="curve")
    return image


def save(name: str, image: Image.Image) -> None:
    ROOT.mkdir(exist_ok=True)
    png = image.resize((512, 512), Image.Resampling.LANCZOS)
    png.save(ROOT / f"{name}.png")
    png.save(ROOT / f"{name}.ico", format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                    (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    save("ct2trainer-converter", converter())
    save("ct2trainer-trainer", trainer())
