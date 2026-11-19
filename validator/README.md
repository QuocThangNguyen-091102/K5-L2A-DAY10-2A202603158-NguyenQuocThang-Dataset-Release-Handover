# Validator

```
python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]
```

Chỉ đọc thư mục delivery được truyền vào; chỉ thư viện chuẩn (+ `scripts/pngutil.py` để đọc PNG); không mạng. Không đọc `_private/`, `data_source/`, annotation COCO. Xem [GUIDE.md](../GUIDE.md) Pha 1–2.

## `--out`: lỗi luật (máy chứng minh được)

| Loại | Cách kiểm |
|---|---|
| `missing_image` | file ảnh trong manifest không tồn tại |
| `wrong_hash` | tự tính sha256 trên bytes (`rb`) của ảnh/nhãn/mask, so với manifest |
| `invalid_class` | class_id không phải số nguyên 0–79 |
| `bbox_out_of_bounds` | cạnh box ra ngoài [0, 1] quá 0,001 (làm tròn YOLO chỉ 1e-6) |
| `duplicate_box` | hai box cùng lớp, w/h lệch ≤ 1 px, tâm lệch ≤ 3 px mỗi trục |
| `scene_leak` | một `scene_id` có ảnh ở cả train và val (target = scene_id) |
| `guideline_mismatch` | `guideline_version` của ảnh khác guideline của **job** trong `jobs.csv` |
| `invalid_category_id` | `category_id` không có trong `categories` |
| `thing_overlap` | `area` khai trong `segments_info` lớn hơn số pixel đếm được trong mask (id = R + G·256 + B·256²) |

## `--candidates`: ứng viên lỗi gán nhãn (phải xem ảnh)

1. Đọc mask thành các đoạn pixel theo hàng cho từng segment (area, bbox pixel).
2. Ghép **một-một** box detection ↔ segment thing (bỏ crowd) theo IoU(box, bbox pixel của segment): lượt 1 cùng lớp (IoU ≥ 0,3), lượt 2 khác lớp (IoU ≥ 0,5). Lớp ghép qua **tên** (`classes.txt` ↔ `categories`).
3. Sinh ứng viên:
   - cặp ghép khác lớp → `class_swap|category_swap` (xem ảnh để biết bên nào sai);
   - cặp cùng lớp mà segment thò ra ngoài box (> 2 px và > 1% cạnh), hoặc < 97% pixel trong box, hoặc IoU < 0,80 → `bbox_drift` (hoặc `instance_merge` nếu phần thò ra lấp một box cùng lớp không có segment riêng);
   - segment ≥ 0,3% ảnh không ghép được: lấp ≥ 25% của ≥ 2 box cùng lớp → `instance_merge`; chồng lên box cùng lớp chưa ghép → `bbox_drift`; còn lại → `missing_box`;
   - box không ghép được mà bị segment cùng lớp (đã ghép với box khác) lấp ≥ 50% → `instance_merge`.
4. Gợi ý lệch tự nhiên (`natural_hint`, xếp cuối hàng đợi): segment chưa ghép trùng khung box cùng lớp IoU ≥ 0,7 (nguồn đã bỏ box trùng khung); hoặc segment nằm trọn trong box với 3/4 cạnh khớp (bị vật khác che).
5. Mỗi ảnh một ứng viên (điểm cao nhất); ảnh đã có lỗi luật không xét.

Ngưỡng chọn bằng số đo trên lô sạch và bộ tự gài lỗi `tools/selftest_crosscheck.py`: xem [submission/REPORT.md](../submission/REPORT.md) mục 1.
