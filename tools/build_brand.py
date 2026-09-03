"""Remove the chosen icon's black exterior and export genuine RGBA PNGs.

Scanline envelopes keep the opaque tile and all dark interior details, rather
than color-keying the bus windows or clock shadows. Only the tile's outer edge
is antialiased.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "design/source/icon-original.png"
    image = Image.open(source).convert("RGB")
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    pixels = image.load()
    for y in range(image.height):
        # Exterior is black; the tile is a convex rounded square. Filling each
        # row's full span protects dark enclosed parts of the bus and background.
        xs = [x for x in range(image.width) if max(pixels[x, y]) > 8]
        if xs and xs[-1] - xs[0] > image.width // 4:
            draw.line((xs[0], y, xs[-1], y), fill=255)
    # Move the antialias transition slightly inside the existing black matte,
    # avoiding an opaque black fringe when composited on light backgrounds.
    alpha = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.5))
    image.putalpha(alpha)
    master = root / "design/brand/YaBusTracker.png"
    image.save(master, optimize=True)
    output = root / "custom_components/yandex_transit/brand/icon.png"
    output.parent.mkdir(exist_ok=True)
    image.resize((256, 256), Image.Resampling.LANCZOS).save(output, optimize=True)
    previews = Image.new("RGB", (768, 256), "white")
    icon = image.resize((256, 256), Image.Resampling.LANCZOS)
    for index, color in enumerate(("#ffffff", "#1c1c1c", "#b9e3f7")):
        background = Image.new("RGBA", icon.size, color)
        background.alpha_composite(icon)
        previews.paste(background.convert("RGB"), (index * 256, 0))
    previews.save(root / "design/brand/background-preview.png")
    print(master)
    print(output)


if __name__ == "__main__":
    main()
