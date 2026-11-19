# Công cụ (ngoài validator)

| File | Việc | Pillow? |
|---|---|---|
| `review_tool.py` | vẽ box detection + viền segment panoptic cho từng ứng viên, kèm hàng phóng to; tạo `review_todo.csv` | có (chỉ công cụ xem ảnh) |
| `trace_query.py` | ticket + changelog + jobs → `trace.json` (tier_a, tier_b, notify) | không |
| `make_handover.py` | delivery v1 + `errors.json` → lô v2 (images, labels, rework_queue, manifest, label_summary, truyvet, README) | không |
| `selftest_crosscheck.py` | tự gài lỗi gán nhãn lên bản chép của lô sạch, đo recall/FP của validator (không đọc `_private`) | không |

Windows: đặt `$env:PYTHONUTF8=1` (PowerShell) hoặc `export PYTHONUTF8=1` (Git Bash) trước khi chạy, để script in được tiếng Việt.

## Đề ẩn: 40 phút

Chuẩn bị trước: đã `git pull`, đặt `PYTHONUTF8=1`, Pillow đã cài (`python -c "import PIL"`).

1. **(1')** Tải `de_an.zip` (tab Releases của repo đề hoặc kênh giảng viên), giải nén vào thư mục gốc repo, sẽ có `delivery/`.
2. **(1')** Lỗi luật + ứng viên + truy vết:
   ```
   python validator/validate.py delivery --out submission/de_an/rules.json --candidates submission/de_an/candidates.json
   python tools/trace_query.py delivery --out submission/de_an/trace.json
   python tools/review_tool.py --delivery delivery --candidates submission/de_an/candidates.json --out runs/de_an_review
   ```
   (`runs/` không commit; ảnh review chỉ để xem.)
3. **(~30')** Mở từng `runs/de_an_review/<ảnh>.png`, chép `runs/de_an_review/review_todo.csv` thành `submission/de_an/review_log.csv`, sửa từng dòng:
   - `type`: một loại duy nhất (`class_swap`, `category_swap`, `bbox_drift`, `missing_box`, `instance_merge`).
   - `verdict`: `confirmed` hoặc `rejected`.
   - `note`: ≥ 20 ký tự, nói **thấy gì** (vật gì, màu gì, ở đâu, box/segment sai thế nào); không chép giống nhau.
   Cần nhìn kỹ hơn: `python tools/review_tool.py --delivery delivery --image img_0123 --out runs/de_an_review`.
4. **(1')** Chốt và nộp:
   ```
   python scripts/merge_review.py --rules submission/de_an/rules.json --review submission/de_an/review_log.csv --out submission/de_an/errors.json
   git add submission/de_an
   git commit -m "De an: errors, candidates, review_log, trace"
   git push
   ```
   **Không** commit `delivery/` (đã có trong `.gitignore`).

### Cách quyết định khi xem ảnh

| Validator gợi ý | Nhìn gì | Kết luận |
|---|---|---|
| `class_swap\|category_swap` (box và segment trùng chỗ, khác lớp) | vật thật trong ảnh là gì | detection ghi sai → `class_swap`; panoptic ghi sai → `category_swap` |
| `bbox_drift` | box có bị dời khỏi vật không (một phía trống, phía kia vật thò ra) | dời → `confirmed`. Nếu segment nằm trọn trong box, 3 cạnh khớp, một phía bị vật khác che → `rejected` (bị che, lệch tự nhiên) |
| `missing_box` | vật đáng kể có segment mà không có box | không có box nào trùng khung → `confirmed`. Gợi ý ghi "TRÙNG KHUNG ... IoU ≥ 0.7" (hai vật chồng khít, chỉ còn một box vì nguồn bỏ box trùng) → `rejected` |
| `instance_merge` | một segment (cùng màu vàng) phủ **hai** vật tách biệt cùng lớp | đúng là hai vật → `confirmed` |

Mỗi ảnh mang nhiều nhất một lỗi: nếu ảnh đã có lỗi luật thì validator không đưa vào hàng đợi.
