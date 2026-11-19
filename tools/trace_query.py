#!/usr/bin/env python3
"""Truy vết ticket của team AI -> trace.json (tier_a, tier_b, notify). Chỉ đọc delivery/.

  python tools/trace_query.py runs/r3158/delivery --out runs/r3158/trace.json

Tiêu chí:
- Lớp bị đổi quy tắc và phiên bản guideline mới: đọc từ guideline/changelog.md (mục chứa "Lớp `X`").
- Job theo guideline CŨ: phiên bản ghi ở JOB (jobs.csv) cũ hơn phiên bản mới, KHÔNG dùng guideline ghi ở
  từng ảnh (metadata) vì đó có thể chính là lỗi guideline_mismatch.
- "Có lớp đó": ảnh có ít nhất một box detection lớp X trong labels/ của lô.
- tier_a: các ảnh trên nằm trong cảnh team AI nêu ở incoming/ticket.md.
- tier_b: các ảnh trên ở cảnh khác (chưa ai báo).
- notify: người gán + người kiểm của các job chứa ảnh tầng a và b.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def ver(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    d = Path(args.delivery)
    changelog = (d / "guideline" / "changelog.md").read_text(encoding="utf-8")
    ticket = (d / "incoming" / "ticket.md").read_text(encoding="utf-8")

    rule_class, new_ver = None, None
    for sec in re.split(r"^##\s+", changelog, flags=re.M)[1:]:
        head, body = sec.split("\n", 1)
        m = re.search(r"Lớp\s+`([^`]+)`", body)
        if m:
            rule_class, new_ver = m.group(1), head.strip().split()[0]
            break
    if not rule_class:
        raise SystemExit("không tìm thấy lớp bị đổi quy tắc trong changelog")
    scenes = sorted(set(re.findall(r"scene_\w+", ticket)))

    classes = {}
    for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            k, n = ln.split(" ", 1)
            classes[int(k)] = n.strip()
    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]
    with (d / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {r["job_id"]: r for r in csv.DictReader(f)}
    old_jobs = {j for j, r in jobs.items() if ver(r["guideline"]) < ver(new_ver)}

    def has_class(name: str) -> bool:
        p = d / "labels" / f"{name}.txt"
        if not p.is_file():
            return False
        for ln in p.read_text(encoding="utf-8").splitlines():
            parts = ln.split()
            try:
                c = float(parts[0])
            except (ValueError, IndexError):
                continue
            if c == int(c) and classes.get(int(c)) == rule_class:
                return True
        return False

    hit = [m for m in meta if m["job_id"] in old_jobs and has_class(m["image"])]
    tier_a = sorted(m["image"] for m in hit if m["scene_id"] in scenes)
    tier_b = sorted(m["image"] for m in hit if m["scene_id"] not in scenes)
    hit_jobs = {m["job_id"] for m in hit}
    notify = sorted({jobs[j]["annotator"] for j in hit_jobs} | {jobs[j]["reviewer"] for j in hit_jobs})
    doc = {"tier_a": tier_a, "tier_b": tier_b, "notify": notify}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"lớp đổi quy tắc: {rule_class} (từ {new_ver}); cảnh được báo: {scenes}; job guideline cũ: {sorted(old_jobs)}")
    print(f"tier_a {len(tier_a)} ảnh, tier_b {len(tier_b)} ảnh, notify {notify} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
