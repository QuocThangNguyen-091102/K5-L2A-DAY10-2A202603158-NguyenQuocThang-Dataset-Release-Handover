#!/usr/bin/env python3
"""Công cụ xem ảnh cho Pha 2 và đề ẩn (được dùng Pillow; validator thì không).

  python tools/review_tool.py --delivery runs/r3158/delivery --candidates runs/r3158/candidates.json --out runs/r3158/review
  python tools/review_tool.py --delivery runs/r3158/delivery --image 000000000285 --out runs/r3158/review

Mỗi ứng viên ra một ảnh <tên>.png gồm 2 hàng:
  hàng 1 (toàn ảnh):   ảnh gốc | box detection (mọi box, box nghi vấn màu đỏ) | segment panoptic (viền + tên lớp, segment nghi vấn tô màu)
  hàng 2 (phóng to vùng nghi vấn): cùng ba ô như trên.
Kèm review_todo.csv (image,type,verdict,note) để điền sau khi xem; note phải nói THẤY GÌ trong ảnh.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pngutil  # noqa: E402

PALETTE = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (148, 103, 189), (140, 86, 75), (227, 119, 194),
           (127, 127, 127), (188, 189, 34), (23, 190, 207), (255, 187, 120), (152, 223, 138), (197, 176, 213)]
RED = (230, 20, 20)
YELLOW = (255, 230, 0)


def font(size: int):
    # font có dấu tiếng Việt (Windows: arial; Linux/macOS: DejaVu/Arial nếu có)
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def color_of(name: str) -> tuple[int, int, int]:
    return PALETTE[sum(map(ord, name)) % len(PALETTE)]


def label(draw, xy, text, fill, f):
    x, y = xy
    l, t, r, b = draw.textbbox((x, y), text, font=f)
    draw.rectangle((l - 1, t - 1, r + 1, b + 1), fill=(0, 0, 0))
    draw.text((x, y), text, fill=fill, font=f)


class Delivery:
    def __init__(self, d: Path):
        self.d = d
        self.classes = {}
        for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                k, n = ln.split(" ", 1)
                self.classes[int(k)] = n.strip()
        pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
        self.cats = {c["id"]: c for c in pan["categories"]}
        imgs = {im["id"]: im for im in pan["images"]}
        self.anns = {Path(imgs[a["image_id"]]["file_name"]).stem: a for a in pan["annotations"]}
        self.man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]

    def boxes(self, name, w, h):
        out = []
        for i, ln in enumerate((self.d / self.man[name]["label"]).read_text(encoding="utf-8").splitlines()):
            p = ln.split()
            if len(p) < 5:
                continue
            c = int(float(p[0]))
            x, y, bw, bh = map(float, p[1:5])
            out.append((i, self.classes.get(c, f"id{c}"), ((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)))
        return out

    def segments(self, name):
        w, h, px = pngutil.read_rgb(self.d / self.man[name]["mask"])
        ids = [r + g * 256 + b * 65536 for r, g, b in zip(px[0::3], px[1::3], px[2::3])]
        segs = []
        for s in self.anns[name]["segments_info"]:
            c = self.cats.get(s["category_id"], {"name": f"cat{s['category_id']}", "isthing": 1})
            segs.append({"id": s["id"], "name": c["name"], "thing": c.get("isthing"), "crowd": s.get("iscrowd", 0)})
        return w, h, ids, segs


def seg_mask(ids, sid, w, h) -> Image.Image:
    return Image.frombytes("L", (w, h), bytes(255 if v == sid else 0 for v in ids))


def render(dl: Delivery, name: str, cand: dict | None, out: Path, f_small, f_big) -> None:
    img_path = dl.d / dl.man[name]["image"]
    w, h, ids, segs = dl.segments(name)
    base = Image.open(img_path).convert("RGB") if img_path.is_file() else Image.new("RGB", (w, h), (60, 60, 60))
    boxes = dl.boxes(name, w, h)
    sus_boxes = set()
    sus_segs = set()
    if cand:
        for k in ("box", "box2"):
            if k in cand:
                sus_boxes.add(cand[k])
        sus_boxes.update(cand.get("boxes", []))
        if "seg" in cand:
            sus_segs.add(cand["seg"])

    # ô detection (det_plain: chỉ viền, cho hàng phóng to; det: thêm tên lớp)
    det = base.copy()
    dd = ImageDraw.Draw(det)
    for i, n, (x0, y0, x1, y1) in boxes:
        col = RED if i in sus_boxes else color_of(n)
        dd.rectangle((x0, y0, x1, y1), outline=col, width=2 if i in sus_boxes else 1)
    det_plain = det.copy()
    for i, n, (x0, y0, x1, y1) in boxes:
        label(dd, (x0 + 2, y0 + 1), f"{i}:{n}", RED if i in sus_boxes else (255, 255, 255), f_small)

    # ô panoptic
    pan = base.copy()
    overlay = Image.new("RGB", (w, h), (0, 0, 0))
    od = ImageDraw.Draw(pan)
    tags = []
    for s in segs:
        if not s["thing"]:
            continue
        m = seg_mask(ids, s["id"], w, h)
        bb = m.getbbox()
        if not bb:
            continue
        col = RED if s["id"] in sus_segs else color_of(s["name"])
        if s["id"] in sus_segs:
            pan = Image.composite(Image.blend(pan, Image.new("RGB", (w, h), YELLOW), 0.45), pan, m)
            od = ImageDraw.Draw(pan)
        edge = m.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v else 0)
        overlay.paste(col, mask=edge)
        tags.append((bb, s, col))
    edges_mask = overlay.convert("L").point(lambda v: 255 if v else 0)
    pan.paste(overlay, mask=edges_mask)
    pan_plain = pan.copy()
    od = ImageDraw.Draw(pan)
    for bb, s, col in tags:
        label(od, (bb[0] + 2, bb[1] + 1), s["name"] + (" (crowd)" if s["crowd"] else ""), RED if s["id"] in sus_segs else (255, 255, 255), f_small)

    # vùng phóng to: hộp bao quanh box/segment nghi vấn
    region = None
    for i, n, b in boxes:
        if i in sus_boxes:
            region = b if region is None else (min(region[0], b[0]), min(region[1], b[1]), max(region[2], b[2]), max(region[3], b[3]))
    for s in segs:
        if s["id"] in sus_segs:
            bb = seg_mask(ids, s["id"], w, h).getbbox()
            if bb:
                region = bb if region is None else (min(region[0], bb[0]), min(region[1], bb[1]), max(region[2], bb[2]), max(region[3], bb[3]))
    if region is None:
        region = (0, 0, w, h)
    rw, rh = region[2] - region[0], region[3] - region[1]
    pad = max(20, 0.35 * max(rw, rh))
    crop = (max(0, int(region[0] - pad)), max(0, int(region[1] - pad)), min(w, int(region[2] + pad)), min(h, int(region[3] + pad)))

    tile_w = 520
    def fit(im, box=None):
        if box:
            im = im.crop(box)
        s = tile_w / im.width
        return im.resize((tile_w, max(1, int(im.height * s))), Image.LANCZOS)

    row1 = [fit(base), fit(det), fit(pan)]
    row2 = [fit(base, crop), fit(det_plain, crop), fit(pan_plain, crop)]
    head = 60
    H = head + row1[0].height + row2[0].height + 10
    sheet = Image.new("RGB", (tile_w * 3 + 20, H), (25, 25, 25))
    sd = ImageDraw.Draw(sheet)
    title = f"{name}   [{cand['type'] if cand else 'xem tay'}]   " + (cand.get("why", "") if cand else "")
    sd.text((8, 6), title[:150], fill=(255, 255, 255), font=f_big)
    sus_txt = ", ".join(f"box {i}:{n}" for i, n, _ in boxes if i in sus_boxes) + "".join(f" | seg:{s['name']}" for s in segs if s["id"] in sus_segs)
    sd.text((8, 32), f"ảnh gốc | detection (đỏ = nghi vấn) | panoptic (vàng = nghi vấn) — hàng dưới: phóng to, không chữ.  Nghi vấn: {sus_txt}"[:170], fill=(200, 200, 200), font=f_small)
    y = head
    for row in (row1, row2):
        x = 0
        for t in row:
            sheet.paste(t, (x, y))
            x += tile_w + 10
        y += row[0].height + 10
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Vẽ box + viền segment để xem ứng viên")
    ap.add_argument("--delivery", required=True)
    ap.add_argument("--candidates")
    ap.add_argument("--image", action="append", help="xem thêm ảnh bất kỳ (lặp được)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dl = Delivery(Path(args.delivery))
    out = Path(args.out)
    f_small, f_big = font(15), font(19)
    todo = []
    if args.candidates:
        for c in json.loads(Path(args.candidates).read_text(encoding="utf-8"))["candidates"]:
            render(dl, c["image"], c, out / f"{c['image']}.png", f_small, f_big)
            todo.append({"image": c["image"], "type": c["type"], "verdict": "", "note": c["why"]})
            print(f"{c['image']}  {c['type']:<26} {c['why']}")
    for name in args.image or []:
        render(dl, name, None, out / f"{name}.png", f_small, f_big)
        print(f"{name}  (xem tay)")
    if todo:
        with (out / "review_todo.csv").open("w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=["image", "type", "verdict", "note"])
            wr.writeheader()
            wr.writerows(todo)
        print(f"{len(todo)} ứng viên -> {out}/<ảnh>.png ; điền {out / 'review_todo.csv'} rồi lưu thành review_log.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
