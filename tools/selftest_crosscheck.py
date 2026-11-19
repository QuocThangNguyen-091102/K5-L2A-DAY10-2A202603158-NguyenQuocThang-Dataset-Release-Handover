#!/usr/bin/env python3
"""Tự kiểm phần đối chiếu của validator mà KHÔNG đọc _private.

Lấy một lô sạch (runs/clean/delivery, sinh bằng inject_release.py --no-faults), chép ra thư mục
tạm, TỰ gài lỗi gán nhãn (code riêng của nhóm, biết đáp án), chạy validator rồi đo recall/precision
theo từng loại. Mức lỗi được để rộng hơn (và khó hơn) mặc định của lab, vì đề ẩn có thể khác.

  python tools/selftest_crosscheck.py --clean runs/clean/delivery --rounds 6
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pngutil  # noqa: E402

KINDS = ["class_swap", "bbox_drift", "missing_box", "category_swap", "instance_merge"]
CONFUSABLE = [["car", "truck", "bus"], ["bicycle", "motorcycle"], ["cat", "dog"], ["horse", "cow", "sheep"],
              ["cup", "wine glass", "bowl"], ["chair", "couch", "bench"], ["laptop", "tv"],
              ["handbag", "backpack", "suitcase"], ["orange", "apple"], ["donut", "cake"], ["bird", "kite"]]


def partner(name, names):
    for g in CONFUSABLE:
        if name in g:
            return [n for n in g if n != name and n in names]
    return []


def counts(mask):
    w, h, px = mask
    out = {}
    for i in range(0, len(px), 3):
        sid = pngutil.segment_id(px, i)
        if sid:
            out[sid] = out.get(sid, 0) + 1
    return out


def inject(d: Path, rng: random.Random, drift=(0.06, 0.3)) -> list[tuple[str, str]]:
    classes = [ln.split(" ", 1)[1] for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in pan["categories"]}
    by_name = {c["name"]: c["id"] for c in pan["categories"]}
    things = {c["id"] for c in pan["categories"] if c["isthing"]}
    imgs = {im["id"]: im for im in pan["images"]}
    anns = {Path(imgs[a["image_id"]]["file_name"]).stem: a for a in pan["annotations"]}
    names = sorted(anns)
    rng.shuffle(names)
    truth = []
    plan = [KINDS[i % len(KINDS)] for i in range(len(names) // 2)]  # một nửa số ảnh bị gài, mỗi ảnh một lỗi
    for name, kind in zip(names, plan):
        lp = d / "labels" / f"{name}.txt"
        rows = [ln.split() for ln in lp.read_text(encoding="utf-8").splitlines() if ln.strip()]
        a = anns[name]
        segs = [s for s in a["segments_info"] if s["category_id"] in things and not s.get("iscrowd")]
        ok = False
        if kind == "class_swap":
            el = [r for r in rows if float(r[3]) * float(r[4]) >= 0.005]
            if el:
                r = rng.choice(el)
                before = classes[int(r[0])]
                pool = partner(before, classes) if rng.random() < 0.7 else []
                pool = pool or [c for c in classes if c != before]
                r[0] = str(classes.index(rng.choice(pool)))
                ok = True
        elif kind == "bbox_drift":
            el = [r for r in rows if float(r[3]) > 0.05 and float(r[4]) > 0.05 and float(r[3]) * float(r[4]) >= 0.004]
            if el:
                r = rng.choice(el)
                x, y, w, h = map(float, r[1:5])
                ang, mag = rng.uniform(0, 2 * math.pi), rng.uniform(*drift)
                if rng.random() < 0.5:
                    s = 1 + rng.uniform(-0.2, 0.2)
                    w, h = min(1.0, w * s), min(1.0, h * s)
                x = min(1 - w / 2, max(w / 2, x + math.cos(ang) * mag * w))
                y = min(1 - h / 2, max(h / 2, y + math.sin(ang) * mag * h))
                r[1:5] = [f"{x:.6f}", f"{y:.6f}", f"{w:.6f}", f"{h:.6f}"]
                ok = True
        elif kind == "missing_box":
            el = [r for r in rows if float(r[3]) * float(r[4]) > 0.008]
            if len(rows) >= 2 and el:
                rows.remove(rng.choice(el))
                ok = True
        elif kind == "category_swap":
            el = [s for s in segs if s.get("area", 0) >= 1024]
            if el:
                s = rng.choice(el)
                before = cats[s["category_id"]]["name"]
                pool = partner(before, by_name) if rng.random() < 0.7 else []
                pool = pool or sorted(cats[c]["name"] for c in things if cats[c]["name"] != before)
                s["category_id"] = by_name[rng.choice(pool)]
                ok = True
        elif kind == "instance_merge":
            groups = {}
            for s in segs:
                groups.setdefault(s["category_id"], []).append(s)
            el = [v for v in groups.values() if len(v) >= 2 and sorted(x.get("area", 0) for x in v)[0] >= 512]
            if el:
                pair = sorted(rng.choice(el), key=lambda s: s.get("area", 0))
                removed, kept = pair[0], pair[-1]
                mp = d / "masks" / f"{name}.png"
                w, h, px = pngutil.read_rgb(mp)
                px = bytearray(px)
                rgb = bytes(pngutil.segment_rgb(kept["id"]))
                for i in range(0, len(px), 3):
                    if pngutil.segment_id(px, i) == removed["id"]:
                        px[i:i + 3] = rgb
                pngutil.write_rgb(mp, w, h, bytes(px))
                kept["area"] = counts((w, h, px))[kept["id"]]
                a["segments_info"] = [s for s in a["segments_info"] if s["id"] != removed["id"]]
                ok = True
        if ok:
            lp.write_text("".join(" ".join(r) + "\n" for r in rows), encoding="utf-8")
            truth.append((kind, name))
    (d / "panoptic.json").write_text(json.dumps(pan), encoding="utf-8")
    return truth


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", default="runs/clean/delivery")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--drift", default="0.06,0.3", help="khoảng độ lệch tâm của bbox_drift (theo cỡ box)")
    args = ap.parse_args()
    drift = tuple(float(v) for v in args.drift.split(","))
    stat = {k: [0, 0] for k in KINDS}  # [gài, bắt được ảnh]
    fp = 0
    wrong_type = 0
    for r in range(args.rounds):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "delivery"
            shutil.copytree(args.clean, d)
            truth = inject(d, random.Random(1000 + r), drift)
            # validator kiểm hash: cập nhật manifest để chỉ còn lỗi gán nhãn
            import hashlib
            man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            for name, it in man["items"].items():
                for key in ("label", "mask"):
                    it[f"{key}_sha256"] = hashlib.sha256((d / it[key]).read_bytes()).hexdigest()
            (d / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
            subprocess.run([sys.executable, str(ROOT / "validator" / "validate.py"), str(d), "--out", str(Path(tmp) / "e.json"),
                            "--candidates", str(Path(tmp) / "c.json")], check=True, capture_output=True)
            doc = json.loads((Path(tmp) / "c.json").read_text(encoding="utf-8"))
            assert not doc["rule_errors"], doc["rule_errors"]
            flagged = {c["image"]: c["type"] for c in doc["candidates"]}
            tmap = {n: k for k, n in truth}
            for k, n in truth:
                stat[k][0] += 1
                if n in flagged:
                    stat[k][1] += 1
                    if k not in flagged[n].split("|"):
                        wrong_type += 1
                        print(f"  round {r}: {n} gài {k}, validator gợi ý {flagged[n]}")
                else:
                    print(f"  round {r}: BỎ SÓT {k} ở {n}")
            fp += sum(1 for n in flagged if n not in tmap)
    tot = sum(v[0] for v in stat.values())
    hit = sum(v[1] for v in stat.values())
    for k, (n, h) in stat.items():
        print(f"{k:<15} gài {n:>3}  bắt {h:>3}  recall {h / max(1, n):.2f}")
    print(f"TỔNG gài {tot}, bắt {hit} (recall {hit / max(1, tot):.2f}); ảnh sạch bị báo: {fp}; gợi ý sai loại: {wrong_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
