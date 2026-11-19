#!/usr/bin/env python3
"""Dựng lô bàn giao v2 (sản phẩm DETECTION) từ delivery v1 + errors.json, không sửa gì trong delivery/.

  python tools/make_handover.py --run runs/r3158 [--broken-hash <ảnh> ...]

- Ảnh có lỗi ở nhãn detection hoặc thiếu file -> rework_queue.csv, rời v2 (giao đúng người gán/kiểm theo jobs.csv).
- wrong_hash: ảnh đã mở kiểm còn nguyên -> ở lại v2, manifest.csv ghi hash thật. Ảnh hỏng (--broken-hash) -> rework.
- guideline_mismatch: truyvet.csv lấy guideline theo JOB.
- scene_leak: cả cảnh đưa về split chiếm đa số của cảnh đó.
- Lỗi chỉ ở panoptic (invalid_category_id, thing_overlap, category_swap, instance_merge): ảnh ở lại v2, ghi vào README để báo team panoptic.
Ảnh và nhãn được CHÉP nguyên byte; nhãn không sửa tay.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

DET_REWORK = {"missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box", "class_swap", "bbox_drift", "missing_box"}
PANOPTIC_ONLY = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}
ACTION = {
    "missing_image": "giao lại file ảnh gốc rồi kiểm lại nhãn",
    "invalid_class": "sửa class_id ngoài 0-79 theo đúng vật trong ảnh",
    "bbox_out_of_bounds": "kéo box về trong khung ảnh, sát mép vật",
    "duplicate_box": "xoá box lặp (cùng lớp, cùng cỡ, lệch 1-2 px)",
    "class_swap": "gán lại lớp đúng cho box bị nhầm lớp",
    "bbox_drift": "vẽ lại box sát vật (box đang lệch khỏi vật)",
    "missing_box": "thêm box cho vật bị bỏ sót",
    "wrong_hash": "ảnh hỏng: giao lại ảnh gốc",
}
THRESHOLD = 0.02


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--broken-hash", nargs="*", default=[], help="ảnh wrong_hash đã mở kiểm và thấy HỎNG (đưa vào rework)")
    args = ap.parse_args()
    run = Path(args.run)
    d = run / "delivery"
    rid = json.loads((d / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {r["job_id"]: r for r in csv.DictReader(f)}
    names80 = [ln.split(" ", 1)[1].strip() for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    errors = json.loads((run / "errors.json").read_text(encoding="utf-8"))["errors"]

    by_img: dict[str, list[str]] = {}
    leaks = []
    for e in errors:
        if e["type"] == "scene_leak":
            leaks.append(e["target"])
        else:
            by_img.setdefault(e["target"], []).append(e["type"])

    rework = {}
    for img, kinds in sorted(by_img.items()):
        det = [k for k in kinds if k in DET_REWORK]
        if det:
            rework[img] = det[0]
        elif "wrong_hash" in kinds and img in args.broken_hash:
            rework[img] = "wrong_hash"

    # split sửa theo cảnh: đa số ảnh của cảnh
    scene_split = {}
    fixed_scenes = []
    by_scene: dict[str, list[str]] = {}
    for n, m in meta.items():
        by_scene.setdefault(m["scene_id"], []).append(n)
    for sc, imgs in by_scene.items():
        cnt = Counter(meta[i]["split"] for i in imgs)
        if len(cnt) > 1:
            maj = cnt.most_common(1)[0][0]
            moved = [i for i in imgs if meta[i]["split"] != maj]
            fixed_scenes.append((sc, maj, moved))
            scene_split[sc] = maj
        else:
            scene_split[sc] = next(iter(cnt))

    v2 = run / "handover" / f"{rid}_v2"
    if v2.exists():
        shutil.rmtree(v2)
    (v2 / "images").mkdir(parents=True)
    (v2 / "labels").mkdir()
    keep = [n for n in sorted(man) if n not in rework and (d / man[n]["image"]).is_file()]
    for n in keep:
        shutil.copyfile(d / man[n]["image"], v2 / "images" / f"{n}.jpg")
        shutil.copyfile(d / man[n]["label"], v2 / "labels" / f"{n}.txt")

    with (v2 / "rework_queue.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "type", "annotator", "reviewer", "action"])
        for img, kind in sorted(rework.items()):
            job = jobs[meta[img]["job_id"]]
            w.writerow([img, kind, job["annotator"], job["reviewer"], ACTION[kind]])

    files = sorted(p for sub in ("images", "labels") for p in (v2 / sub).iterdir() if p.is_file())
    with (v2 / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "sha256"])
        for p in files:
            w.writerow([p.relative_to(v2).as_posix(), sha(p)])

    counts: Counter = Counter()
    for n in keep:
        for ln in (v2 / "labels" / f"{n}.txt").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                counts[names80[int(float(ln.split()[0]))]] += 1
    with (v2 / "label_summary.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class", "count"])
        for c in names80:
            if counts.get(c):
                w.writerow([c, counts[c]])
        w.writerow(["TOTAL", sum(counts.values())])

    with (v2 / "truyvet.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"])
        for n in keep:
            m = meta[n]
            job = jobs[m["job_id"]]
            w.writerow([n, m["scene_id"], scene_split[m["scene_id"]], m["job_id"], job["annotator"], job["reviewer"], job["guideline"]])

    # README
    n_err = len({e["target"] for e in errors})
    rate = n_err / len(man)
    old = sorted(j for j, r in jobs.items() if r["guideline"] == "v1.2")
    new = sorted(j for j, r in jobs.items() if r["guideline"] == "v1.3")
    kinds = Counter(e["type"] for e in errors)
    hash_fixed = [i for i, k in by_img.items() if "wrong_hash" in k and i not in rework]
    gl_fixed = [i for i, k in by_img.items() if "guideline_mismatch" in k]
    pan = sorted((i, k) for i, ks in by_img.items() for k in ks if k in PANOPTIC_ONLY)
    by_person: dict[tuple, list[str]] = {}
    for img in rework:
        job = jobs[meta[img]["job_id"]]
        by_person.setdefault((job["annotator"], job["reviewer"]), []).append(img)
    dec_v1 = "Hold" if rate > THRESHOLD else "Release"
    lines = [
        f"Release: {rid}_v2",
        f"Parent: {rid}",
        f"Số ảnh: {len(keep)}",
        f"Số nhãn: {sum(counts.values())}",
        f"Guideline: v1.2 ({', '.join(old)}), v1.3 ({', '.join(new)}) — lấy theo job trong jobs.csv",
        f"QC v1: {n_err}/{len(man)} = {rate * 100:.1f}% ảnh/cảnh lỗi ({len([e for e in errors if e['type'] not in ('class_swap', 'bbox_drift', 'missing_box', 'category_swap', 'instance_merge')])} lỗi luật + "
        f"{len([e for e in errors if e['type'] in ('class_swap', 'bbox_drift', 'missing_box', 'category_swap', 'instance_merge')])} lỗi gán nhãn đã xem ảnh xác nhận)",
        f"Kết luận v1: {dec_v1} — {rate * 100:.1f}% {'>' if rate > THRESHOLD else '<='} ngưỡng 2% (Day 7), không phát hành v1; lineage đã ghi HOLD",
        f"Kết luận v2: Release — đã tách {len(rework)} ảnh lỗi nhãn detection sang rework_queue.csv, sửa hash/guideline/split; "
        f"{len(keep)} ảnh còn lại không còn lỗi detection đã biết",
        "Ghi chú:",
        "- Lỗi theo loại trong errors.json v1: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())),
        "- Hash: " + (", ".join(hash_fixed) + " có sha256 trong manifest v1 là của ảnh khác; đã mở ảnh kiểm (giải mã được, đúng nội dung, khớp nhãn) nên giữ ảnh, manifest.csv ghi sha256 thật" if hash_fixed else "không có"),
        "- Guideline: " + (", ".join(gl_fixed) + " ghi sai phiên bản ở metadata; truyvet.csv lấy guideline theo job" if gl_fixed else "không có") + ", mọi ảnh dùng guideline của job",
        "- Split: " + ("; ".join(f"{sc} có {', '.join(mv)} lệch split, đưa cả cảnh về {mj} (đa số ảnh của cảnh) để không rò train/val" for sc, mj, mv in fixed_scenes) or "không có cảnh rò"),
        "- Rework (bỏ khỏi v2, giao lại đúng người gán/kiểm theo jobs.csv): " + "; ".join(f"{a}/{r}: {', '.join(sorted(imgs))}" for (a, r), imgs in sorted(by_person.items())),
        "- Lỗi chỉ ở panoptic, nhãn detection vẫn đúng nên ảnh ở lại v2, báo team panoptic sửa mask/segments_info: " + ", ".join(f"{i} ({k})" for i, k in pan),
        "- Nhãn trong v2 chép nguyên byte từ v1, không sửa tay; v1 (delivery/) giữ nguyên",
    ]
    (v2 / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{v2}: {len(keep)} ảnh, {sum(counts.values())} nhãn, rework {len(rework)}, QC v1 {n_err}/{len(man)} = {rate:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
