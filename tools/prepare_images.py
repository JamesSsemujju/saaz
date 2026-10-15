#!/usr/bin/env python3
"""Make the site's fixed images from the original photos in Pictures/.

Usage:  python3 tools/prepare_images.py   (needs Pillow: pip3 install pillow)
Reads:  src/data/image-crops.json and Pictures/<source>
Writes: src/assets/img/<slot>-640.webp and <slot>-1280.webp, cropped to 4:3, number plates blurred.
The originals are never changed. Run this only when a photo or crop changes; build.py does not need Pillow.
"""
import json, sys
from pathlib import Path
try:
    from PIL import Image, ImageFilter, ImageOps
except ImportError:
    sys.exit("Pillow is needed: pip3 install pillow")

ROOT = Path(__file__).resolve().parent.parent
plan = json.loads((ROOT / "src/data/image-crops.json").read_text(encoding="utf-8"))
out = ROOT / "src/assets/img"
out.mkdir(parents=True, exist_ok=True)
for slot, p in plan.items():
    if slot.startswith("_"): continue
    im = ImageOps.exif_transpose(Image.open(ROOT / "Pictures" / p["source"])).convert("RGB")
    w, h = im.size
    for (l, t, r, b) in p["blur"]:  # blur plates on the original before cropping
        box = (int(l * w), int(t * h), int(r * w), int(b * h))
        im.paste(im.crop(box).filter(ImageFilter.GaussianBlur(max(12, (box[2] - box[0]) // 8))), box)
    ch = int(w * 3 / 4)
    top = min(int(p["crop_top"] * h), h - ch)
    im = im.crop((0, top, w, top + ch))
    for width in (640, 1280):
        im.resize((width, width * 3 // 4), Image.LANCZOS).save(out / f"{slot}-{width}.webp", "WEBP", quality=72, method=6)
    print("made", slot)
