#!/usr/bin/env python3
"""Validator cho một lô bàn giao (detection YOLO + panoptic COCO).

  python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

- Chỉ đọc thư mục delivery được truyền vào. Không đọc _private/, data_source/, annotation COCO.
- Chỉ thư viện chuẩn (+ scripts/pngutil.py để đọc PNG). Không dùng mạng.
- --out: lỗi LUẬT (máy chứng minh được bằng file). Lỗi gán nhãn KHÔNG ghi vào đây:
  chúng chỉ là ứng viên, phải xem ảnh rồi mới đưa vào errors.json (scripts/merge_review.py).
- --candidates: ứng viên lỗi gán nhãn sinh ra bằng cách đối chiếu detection <-> panoptic.

Các ngưỡng nằm ở khối THAM SỐ bên dưới; cách chọn ghi trong submission/REPORT.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from itertools import groupby
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402  (chỉ đọc PNG, thư viện chuẩn)

# ----------------------------------------------------------------------------- THAM SỐ
# Luật
OOB_TOL = 1e-3            # box tràn khỏi [0,1] quá mức làm tròn (1e-6) mới là lỗi
DUP_SIZE_PX = 1.0         # box lặp: cùng lớp, w/h lệch <= 1 px ...
DUP_SHIFT_PX = 3.0        # ... và tâm lệch <= 3 px mỗi trục
AREA_TOL = 0              # area khai > số pixel đếm được + AREA_TOL => thing_overlap

# Đối chiếu (chọn trên lô sạch + lô tự gài lỗi, xem REPORT.md)
MATCH_IOU = 0.3           # ghép box <-> segment theo IoU của bbox (box vs bbox pixel của segment)
MIN_SEG_FRAC = 0.003      # bỏ segment nhỏ hơn 0.3% ảnh khi tìm missing_box / merge
MIN_SEG_PX = 400
# Lô sạch (50 ảnh, 435 cặp): segment thò ra ngoài box tối đa 0.5 px, 100% pixel nằm trong box,
# IoU(box, bbox segment) >= 0.91 với segment >= 400 px. Ngưỡng dưới đây để cách xa mức tự nhiên đó.
DRIFT_PROTRUDE = 0.01     # segment thò ra ngoài box > 1% cạnh box (và > 2 px) ...
DRIFT_PROTRUDE_PX = 2.0
DRIFT_COVER = 0.97        # ... hoặc < 97% pixel segment nằm trong box
DRIFT_IOU = 0.80          # ... hoặc IoU(box, bbox segment) < 0.80 (box rộng/lệch hẳn khỏi vật)
DRIFT_IOU_MIN_PX = 400    # chỉ dùng tín hiệu IoU khi segment đủ lớn
EDGE_TOL_PX = 2.0         # cạnh box và cạnh bbox segment coi là khớp nếu lệch <= 2 px
MERGE_SHARE = 0.05        # segment có >= 5% pixel nằm trong mỗi box của >= 2 box cùng lớp
MERGE_FILL = 0.25         # và mỗi box đó được segment lấp >= 25% diện tích
NATURAL_DUP_IOU = 0.7     # segment chưa ghép trùng khung box cùng lớp >= 0.7 => gợi ý lệch tự nhiên
# Lô sạch: không có segment thing nào >= 0.3% ảnh mà không ghép được box. Nên segment lớn chưa ghép
# (không phải merge, không phải drift) là ứng viên missing_box, kể cả khi nó nằm trong box của vật khác.

SEMANTIC = ("class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge")


# ----------------------------------------------------------------------------- đọc lô
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(d: Path) -> dict:
    classes = {}
    for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            k, name = ln.strip().split(" ", 1)
            classes[int(k)] = name.strip()
    pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in pan["categories"]}
    images = {im["id"]: im for im in pan["images"]}
    anns = {}
    for a in pan["annotations"]:
        im = images.get(a["image_id"])
        stem = Path(im["file_name"] if im else a["file_name"]).stem
        anns[stem] = (a, im)
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}
    return {"classes": classes, "cats": cats, "anns": anns, "man": man, "meta": meta, "jobs": jobs}


def parse_labels(path: Path) -> tuple[list[dict], bool]:
    """Trả (boxes, invalid_class). Box: cls, x, y, w, h chuẩn hoá."""
    boxes, invalid = [], False
    if not path.is_file():
        return boxes, invalid
    for ln in path.read_text(encoding="utf-8").splitlines():
        parts = ln.split()
        if not parts:
            continue
        try:
            c = float(parts[0])
            x, y, w, h = map(float, parts[1:5])
        except (ValueError, IndexError):
            invalid = True
            continue
        if c != int(c) or not 0 <= int(c) < 80:
            invalid = True
        boxes.append({"cls": int(c) if c == int(c) else -1, "x": x, "y": y, "w": w, "h": h})
    return boxes, invalid


# ----------------------------------------------------------------------------- mask
def read_segments(mask_path: Path) -> tuple[int, int, dict]:
    """Đọc mask panoptic -> {segment_id: {area, bbox[x0,y0,x1,y1] (bao gồm), rows{y: [(x0,x1)]}}}."""
    width, height, px = pngutil.read_rgb(mask_path)
    r, g, b = px[0::3], px[1::3], px[2::3]
    ids = [ri + gi * 256 + bi * 65536 for ri, gi, bi in zip(r, g, b)]
    segs: dict[int, dict] = {}
    for y in range(height):
        x = 0
        for sid, grp in groupby(ids[y * width:(y + 1) * width]):
            n = sum(1 for _ in grp)
            if sid:
                s = segs.get(sid)
                if s is None:
                    s = segs[sid] = {"area": 0, "bbox": [x, y, x + n - 1, y], "rows": {}}
                s["area"] += n
                bb = s["bbox"]
                bb[0], bb[1], bb[2], bb[3] = min(bb[0], x), min(bb[1], y), max(bb[2], x + n - 1), max(bb[3], y)
                s["rows"].setdefault(y, []).append((x, x + n - 1))
            x += n
    return width, height, segs


def inside(seg: dict, box: tuple[float, float, float, float], margin: float = 1.0) -> int:
    """Số pixel của segment có tâm nằm trong box (pixel, nới margin)."""
    x0, y0, x1, y1 = box
    xa, xb = int(-(-(x0 - margin - 0.5) // 1)), int((x1 + margin - 0.5) // 1)
    ya, yb = int(-(-(y0 - margin - 0.5) // 1)), int((y1 + margin - 0.5) // 1)
    total = 0
    for y, runs in seg["rows"].items():
        if ya <= y <= yb:
            for a, b in runs:
                lo, hi = max(a, xa), min(b, xb)
                if hi >= lo:
                    total += hi - lo + 1
    return total


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


# ----------------------------------------------------------------------------- luật
def rule_checks(d: Path, data: dict) -> tuple[list[dict], dict]:
    man, meta, jobs, cats = data["man"], data["meta"], data["jobs"], data["cats"]
    found: list[dict] = []
    cache: dict = {}

    def add(kind, target, **why):
        found.append({"type": kind, "target": target, **why})

    scenes: dict[str, dict[str, list[str]]] = {}
    for name in sorted(man):
        it = man[name]
        m = meta.get(name, {})
        scenes.setdefault(m.get("scene_id"), {}).setdefault(m.get("split"), []).append(name)

        img = d / it["image"]
        if not img.is_file():
            add("missing_image", name, why="manifest có ảnh nhưng thiếu file")
        else:
            if sha256(img) != it.get("image_sha256"):
                add("wrong_hash", name, why="sha256 của file ảnh khác manifest")
        for key in ("label", "mask"):
            p = d / it[key]
            if p.is_file() and sha256(p) != it.get(f"{key}_sha256"):
                add("wrong_hash", name, why=f"sha256 của file {key} khác manifest")

        job = jobs.get(m.get("job_id"))
        if job and m.get("guideline_version") != job["guideline"]:
            add("guideline_mismatch", name, why=f"ảnh ghi {m.get('guideline_version')}, job {m.get('job_id')} ghi {job['guideline']}")

        boxes, invalid = parse_labels(d / it["label"])
        if invalid:
            add("invalid_class", name, why="class_id ngoài 0-79")
        a, im = data["anns"].get(name, (None, None))
        W = im["width"] if im else None
        H = im["height"] if im else None
        for bx in boxes:
            if (bx["x"] - bx["w"] / 2 < -OOB_TOL or bx["y"] - bx["h"] / 2 < -OOB_TOL
                    or bx["x"] + bx["w"] / 2 > 1 + OOB_TOL or bx["y"] + bx["h"] / 2 > 1 + OOB_TOL):
                add("bbox_out_of_bounds", name, why=f"box {bx} vượt khỏi ảnh")
                break
        if W and H:
            dup = False
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    p, q = boxes[i], boxes[j]
                    if (p["cls"] == q["cls"] and abs(p["w"] - q["w"]) * W <= DUP_SIZE_PX and abs(p["h"] - q["h"]) * H <= DUP_SIZE_PX
                            and abs(p["x"] - q["x"]) * W <= DUP_SHIFT_PX and abs(p["y"] - q["y"]) * H <= DUP_SHIFT_PX):
                        dup = True
                        break
                if dup:
                    break
            if dup:
                add("duplicate_box", name, why="hai box cùng lớp, cùng kích thước, lệch <= 3 px")

        # panoptic
        if a is not None:
            bad_cat = [s["id"] for s in a["segments_info"] if s["category_id"] not in cats]
            if bad_cat:
                add("invalid_category_id", name, why=f"segment {bad_cat} có category_id không có trong categories")
            mask = d / it["mask"]
            if mask.is_file():
                w, h, segs = read_segments(mask)
                cache[name] = (w, h, segs, boxes)
                over = [s["id"] for s in a["segments_info"] if s.get("area", 0) > segs.get(s["id"], {"area": 0})["area"] + AREA_TOL]
                if over:
                    add("thing_overlap", name, why=f"segment {over}: area khai > số pixel thật trong mask")
    for scene, by_split in scenes.items():
        if len(by_split) > 1:
            sizes = {k: len(v) for k, v in by_split.items()}
            minority = min(by_split, key=lambda k: len(by_split[k]))
            add("scene_leak", scene, why=f"cảnh nằm ở {sizes}", leaked_images=by_split[minority])
    return found, cache


# ----------------------------------------------------------------------------- đối chiếu
def cross_check(name: str, data: dict, w: int, h: int, segs: dict, boxes: list[dict]) -> list[dict]:
    cats, classes = data["cats"], data["classes"]
    a, _ = data["anns"][name]
    min_px = max(MIN_SEG_PX, MIN_SEG_FRAC * w * h)
    things = []
    for s in a["segments_info"]:
        c = cats.get(s["category_id"])
        if not c or not c.get("isthing") or s.get("iscrowd") or s["id"] not in segs:
            continue
        g = segs[s["id"]]
        bb = g["bbox"]
        things.append({"id": s["id"], "name": c["name"], "area": g["area"], "g": g,
                       "box": (bb[0], bb[1], bb[2] + 1, bb[3] + 1)})
    dets = []
    for i, bx in enumerate(boxes):
        if not 0 <= bx["cls"] < 80:
            continue
        x0, y0 = (bx["x"] - bx["w"] / 2) * w, (bx["y"] - bx["h"] / 2) * h
        dets.append({"i": i, "name": classes[bx["cls"]], "box": (x0, y0, x0 + bx["w"] * w, y0 + bx["h"] * h)})

    # ghép một-một: lượt 1 cùng lớp, lượt 2 khác lớp (IoU cao hơn)
    pairs = []
    for di, dt in enumerate(dets):
        for si, sg in enumerate(things):
            v = iou(dt["box"], sg["box"])
            if v >= MATCH_IOU:
                pairs.append((dt["name"] == sg["name"], v, di, si))
    pairs.sort(key=lambda p: (not p[0], -p[1]))
    d2s, s2d = {}, {}
    for same, v, di, si in pairs:
        if di in d2s or si in s2d or (not same and v < 0.5):
            continue
        d2s[di], s2d[si] = si, di

    out = []

    def cand(kind, score, why, **extra):
        out.append({"image": name, "type": kind, "score": round(score, 3), "why": why, **extra})

    def same_class_boxes(sg):
        return [(di, dt) for di, dt in enumerate(dets) if dt["name"] == sg["name"]]

    # 1) cặp đã ghép nhưng khác lớp
    for di, si in d2s.items():
        dt, sg = dets[di], things[si]
        if dt["name"] != sg["name"]:
            v = iou(dt["box"], sg["box"])
            cand("class_swap|category_swap", 1.0 + v, f"box '{dt['name']}' trùng segment '{sg['name']}' (IoU {v:.2f})",
                 box=dt["i"], seg=sg["id"], det_class=dt["name"], pan_class=sg["name"])

    # 2) cặp cùng lớp nhưng segment thò ra ngoài box: drift hoặc merge
    for di, si in d2s.items():
        dt, sg = dets[di], things[si]
        if dt["name"] != sg["name"]:
            continue
        x0, y0, x1, y1 = dt["box"]
        bw, bh = max(1.0, x1 - x0), max(1.0, y1 - y0)
        sx0, sy0, sx1, sy1 = sg["box"]
        prot = max((x0 - sx0) / bw, (sx1 - x1) / bw, (y0 - sy0) / bh, (sy1 - y1) / bh, 0.0)
        prot_px = max(x0 - sx0, sx1 - x1, y0 - sy0, sy1 - y1, 0.0)
        cover = inside(sg["g"], dt["box"]) / max(1, sg["area"])
        v = iou(dt["box"], sg["box"])
        loose = sg["area"] >= DRIFT_IOU_MIN_PX and v < DRIFT_IOU
        if (prot > DRIFT_PROTRUDE and prot_px > DRIFT_PROTRUDE_PX) or cover < DRIFT_COVER or loose:
            # phần thò ra có nằm gọn trong một box cùng lớp khác không có segment riêng? => merge
            outside = sg["area"] - inside(sg["g"], dt["box"])
            merge = None
            for dj, other in same_class_boxes(sg):
                if dj == di:
                    continue
                share = inside(sg["g"], other["box"]) - 0  # pixel của segment trong box kia
                ob = other["box"]
                fill = share / max(1.0, (ob[2] - ob[0]) * (ob[3] - ob[1]))
                if dj not in d2s and share >= 0.5 * outside and fill >= MERGE_FILL:
                    merge = (dj, fill)
                    break
            if merge:
                cand("instance_merge", 1.0 + merge[1], f"segment '{sg['name']}' phủ box {dt['i']} và box {dets[merge[0]]['i']} (box sau không có segment riêng)",
                     box=dt["i"], box2=dets[merge[0]]["i"], seg=sg["id"], det_class=dt["name"], pan_class=sg["name"])
            else:
                # Box lệch thật bị tịnh tiến nên hầu như không cạnh nào còn khớp segment. Segment nằm trọn trong box
                # và >= 3 cạnh khớp (<= 2 px) => box đúng, segment bị vật phía trước che một phía (lệch tự nhiên).
                same_edges = sum(1 for a_, b_ in zip(dt["box"], sg["box"]) if abs(a_ - b_) <= EDGE_TOL_PX)
                natural = prot_px <= DRIFT_PROTRUDE_PX and cover >= 0.99 and same_edges >= 3
                cand("bbox_drift", (0.05 if natural else 0.0) + max(prot, 1 - cover, 1 - v) * (0.2 if natural else 1.0),
                     f"segment '{sg['name']}' thò ra ngoài box {prot:.0%} cạnh ({prot_px:.0f}px), {cover:.0%} pixel trong box, IoU {v:.2f}, {same_edges}/4 cạnh khớp"
                     + ("; segment nằm trọn trong box và 3 cạnh khớp -> có thể bị che (lệch tự nhiên)" if natural else ""),
                     box=dt["i"], seg=sg["id"], det_class=dt["name"], pan_class=sg["name"], protrude=round(prot, 3), cover=round(cover, 3),
                     iou=round(v, 3), same_edges=same_edges, natural_hint=natural)

    # 3) segment lớn không ghép được box nào
    for si, sg in enumerate(things):
        if si in s2d or sg["area"] < min_px:
            continue
        boxes_same = same_class_boxes(sg)
        shares = []
        for di, dt in boxes_same:
            sh = inside(sg["g"], dt["box"])
            b = dt["box"]
            fill = sh / max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
            shares.append((sh / sg["area"], fill, di))
        big = [s for s in shares if s[0] >= MERGE_SHARE and s[1] >= MERGE_FILL]
        best = max((s[0] for s in shares), default=0.0)
        loose = [s for s in shares if s[2] not in d2s and s[0] > 0.2]
        if len(big) >= 2:
            cand("instance_merge", 1.0 + min(s[1] for s in big), f"segment '{sg['name']}' ({sg['area']}px) trải trên {len(big)} box cùng lớp",
                 seg=sg["id"], boxes=[dets[s[2]]["i"] for s in big], pan_class=sg["name"])
        elif loose:
            # có box cùng lớp chưa ghép chồng lên => box lệch xa tới mức không ghép được
            cand("bbox_drift", 1.0 - best, f"segment '{sg['name']}' không ghép được; box cùng lớp chưa ghép chỉ chứa {loose[0][0]:.0%} pixel",
                 seg=sg["id"], box=dets[loose[0][2]]["i"], pan_class=sg["name"])
        else:
            # Lô gốc đã bỏ box trùng khung (cùng lớp, IoU > 0.7) trước khi giao: hai vật chồng khít chỉ còn
            # một box. Segment trùng khung (IoU >= NATURAL_DUP_IOU) với box cùng lớp có sẵn => nhiều khả năng
            # là lệch tự nhiên đó, không phải box bị xoá. Vẫn đưa vào hàng đợi, xếp cuối, để người xem quyết.
            dup = max((iou(sg["box"], dt["box"]) for _, dt in boxes_same), default=0.0)
            natural = dup >= NATURAL_DUP_IOU
            cand("missing_box", (0.2 if natural else 1.0) + sg["area"] / (w * h),
                 f"segment '{sg['name']}' {sg['area']}px ({sg['area'] / (w * h):.1%} ảnh) không có box riêng (tối đa {best:.0%} pixel trong box cùng lớp khác)"
                 + (f"; TRÙNG KHUNG box cùng lớp IoU {dup:.2f} -> có thể lệch tự nhiên (box trùng đã bị bỏ ở nguồn)" if natural else ""),
                 seg=sg["id"], pan_class=sg["name"], area=sg["area"], natural_hint=natural, dup_iou=round(dup, 3))

    # 4) box không ghép được segment nhưng nằm trong segment cùng lớp đã ghép với box khác => merge
    for di, dt in enumerate(dets):
        if di in d2s:
            continue
        b = dt["box"]
        barea = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
        if barea < min_px:
            continue
        for si, sg in enumerate(things):
            if sg["name"] != dt["name"] or si not in s2d:
                continue  # segment chưa ghép đã được xét ở bước 3
            fill = inside(sg["g"], b, margin=0) / barea
            if fill >= 0.5 and not any(c.get("seg") == sg["id"] for c in out):
                cand("instance_merge", 0.5 + fill, f"box {dt['i']} '{dt['name']}' không có segment riêng, bị segment của box {dets[s2d[si]]['i']} lấp {fill:.0%}",
                     box=dt["i"], box2=dets[s2d[si]]["i"], seg=sg["id"], det_class=dt["name"], pan_class=sg["name"])
    return out


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Validator lô bàn giao detection + panoptic")
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True, help="errors.json: chỉ lỗi luật")
    ap.add_argument("--candidates", help="candidates.json: ứng viên lỗi gán nhãn để xem ảnh")
    args = ap.parse_args()
    d = Path(args.delivery)
    data = load(d)
    rules, cache = rule_checks(d, data)

    rule_targets = {e["target"] for e in rules}
    for e in rules:
        rule_targets.update(e.get("leaked_images", []))
    errors = sorted({(e["type"], e["target"]) for e in rules})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"errors": [{"type": t, "target": g} for t, g in errors]}, indent=1) + "\n", encoding="utf-8")
    counts = {}
    for t, _ in errors:
        counts[t] = counts.get(t, 0) + 1
    print(f"lỗi luật: {len(errors)} {counts} -> {out}")

    if args.candidates:
        cands = []
        for name in sorted(cache):
            if name in rule_targets:
                continue  # mỗi ảnh mang nhiều nhất một lỗi: ảnh đã có lỗi luật thì không xét
            w, h, segs, boxes = cache[name]
            found = cross_check(name, data, w, h, segs, boxes)
            if found:
                found.sort(key=lambda c: -c["score"])
                top = found[0]
                cands.append({**top, "others": [{"type": c["type"], "why": c["why"]} for c in found[1:]]})
        cands.sort(key=lambda c: (-c["score"], c["image"]))
        doc = {"note": "Ứng viên lỗi gán nhãn: chưa phải lỗi. Mở ảnh, ghi review_log.csv.",
               "rule_errors": [{"type": e["type"], "target": e["target"], "why": e.get("why", "")} for e in rules],
               "candidates": cands}
        cp = Path(args.candidates)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        byk = {}
        for c in cands:
            byk[c["type"]] = byk.get(c["type"], 0) + 1
        print(f"ứng viên: {len(cands)} ảnh {byk} -> {cp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
