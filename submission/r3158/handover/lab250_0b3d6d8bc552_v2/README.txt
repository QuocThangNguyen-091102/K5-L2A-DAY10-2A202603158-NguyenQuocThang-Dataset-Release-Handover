Release: lab250_0b3d6d8bc552_v2
Parent: lab250_0b3d6d8bc552
Số ảnh: 240
Số nhãn: 1699
Guideline: v1.2 (J01, J02, J03, J04), v1.3 (J05, J06, J07, J08, J09, J10) — lấy theo job trong jobs.csv
QC v1: 17/250 = 6.8% ảnh/cảnh lỗi (9 lỗi luật + 8 lỗi gán nhãn đã xem ảnh xác nhận)
Kết luận v1: Hold — 6.8% > ngưỡng 2% (Day 7), không phát hành v1; lineage đã ghi HOLD
Kết luận v2: Release — đã tách 10 ảnh lỗi nhãn detection sang rework_queue.csv, sửa hash/guideline/split; 240 ảnh còn lại không còn lỗi detection đã biết
Ghi chú:
- Lỗi theo loại trong errors.json v1: bbox_drift 2, bbox_out_of_bounds 1, category_swap 2, class_swap 1, duplicate_box 2, guideline_mismatch 1, instance_merge 1, invalid_class 2, missing_box 2, scene_leak 1, thing_overlap 1, wrong_hash 1
- Hash: 000000009914 có sha256 trong manifest v1 là của ảnh khác; đã mở ảnh kiểm (giải mã được, đúng nội dung, khớp nhãn) nên giữ ảnh, manifest.csv ghi sha256 thật
- Guideline: 000000017379 ghi sai phiên bản ở metadata; truyvet.csv lấy guideline theo job, mọi ảnh dùng guideline của job
- Split: scene_283 có 000000008690 lệch split, đưa cả cảnh về train (đa số ảnh của cảnh) để không rò train/val
- Rework (bỏ khỏi v2, giao lại đúng người gán/kiểm theo jobs.csv): A01/Q02: 000000017207; A01/Q03: 000000015254; A03/Q02: 000000025424; A03/Q03: 000000020107, 000000021465, 000000022969; A04/Q01: 000000007278, 000000008762; A05/Q01: 000000010995; A05/Q02: 000000005060
- Lỗi chỉ ở panoptic, nhãn detection vẫn đúng nên ảnh ở lại v2, báo team panoptic sửa mask/segments_info: 000000000285 (category_swap), 000000009891 (category_swap), 000000019109 (thing_overlap), 000000020247 (instance_merge)
- Nhãn trong v2 chép nguyên byte từ v1, không sửa tay; v1 (delivery/) giữ nguyên
