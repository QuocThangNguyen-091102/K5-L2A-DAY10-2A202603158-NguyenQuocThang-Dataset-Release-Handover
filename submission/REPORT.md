# Báo cáo — Nguyễn Quốc Thắng (làm cá nhân, seed 3158)

Làm một mình vì các nhóm trong lớp đã đủ người; giảng viên cho phép dùng AI hỗ trợ ở mọi bước vì làm một mình.

## 1. Số liệu luyện tập

Mọi số dưới đây là output thật của `scripts/score_findings.py` (chế độ học viên, làm tròn 1 chữ số) và của validator.

**F1 theo seed (rule / cross_check / overall):**

| Lô | Cách tạo | rule | cross_check | overall | Ghi chú |
|---|---|---:|---:|---:|---|
| r3158 (seed nộp) | `run_lab.py --seeds 3158` | 1.0 | 0.9 | 0.9 | 9 lỗi luật + 8 lỗi gán nhãn đã xem ảnh xác nhận |
| r11, r22, r33, r101, r2024, r9999 | `inject_release.py` | 1.0 | — | 0.7–0.8 | chỉ chạy luật để kiểm validator (chưa review nên overall thấp) |
| opaque777 | `inject_release.py --opaque` (giả lập đề ẩn: tên `img_XXXX`, segment id đánh lại, byte ảnh đổi) | 1.0 | — | 0.8 | chỉ luật; truy vết 1.0 / 1.0 / 1.0 |

Truy vết trên r3158, r11, r22, r33, opaque777: tier_a 1.0 · tier_b 1.0 · notify 1.0.

**Số ứng viên trên lô sạch (`--no-faults`, 50 ảnh pool calib): 0 ứng viên, 0 lỗi luật.**
Hàng đợi trên seed luyện tập: **12 ảnh** (8 confirmed, 4 rejected). Các seed khác: 8–11 ảnh/lô.

**Ngưỡng đã chọn và cách chọn (không dùng `_private`):**

1. Đo trên lô sạch (435 cặp box ↔ segment thing, 50 ảnh): ghép một-một theo IoU giữa box detection và bbox **pixel** của segment, thì cả 435 box đều ghép được; **100% pixel** của segment nằm trong box; segment thò ra ngoài box tối đa **0,5 px**; IoU(box, bbox segment) ≥ **0,91** với segment ≥ 400 px; không có segment thing nào ≥ 0,3% ảnh mà không có box. Nghĩa là với cách ghép bằng pixel mask, nhiễu tự nhiên gần bằng 0.
2. Đặt ngưỡng cách xa mức tự nhiên đó (`validator/validate.py`, khối THAM SỐ): drift khi segment thò ra > 2 px và > 1% cạnh box, hoặc < 97% pixel nằm trong box, hoặc IoU < 0,80; missing_box khi segment ≥ 0,3% ảnh (≥ 400 px) không ghép được box; instance_merge khi một segment lấp ≥ 25% diện tích của ≥ 2 box cùng lớp; class/category_swap khi cặp ghép (IoU ≥ 0,5) khác lớp.
3. Đo recall bằng **bộ tự gài lỗi** của mình (`tools/selftest_crosscheck.py`): chép lô sạch, tự gài 5 loại lỗi gán nhãn (biết đáp án vì tự gài), mức lỗi rộng hơn mặc định (drift 0,06–0,3 và thử cả 0,04–0,12). Kết quả: **261/262 lỗi bị bắt (recall 0,99–1,00), 0 ảnh sạch bị báo**. Hai lần chỉnh dựa trên bộ này: hạ ngưỡng thò ra từ 3% xuống 1% cạnh box (bỏ sót box lệch sát mép ảnh); và coi mọi segment lớn chưa ghép là ứng viên missing_box (trước đó bỏ sót khi segment nằm trong box của vật khác cùng lớp).

Validator ghi `errors.json` chỉ gồm lỗi luật; lỗi gán nhãn chỉ vào `errors.json` sau khi xem ảnh (`scripts/merge_review.py`). Ảnh đã có lỗi luật không xét đối chiếu (mỗi ảnh mang nhiều nhất một lỗi, theo `docs/DELIVERY.md`).

**Hai loại lệch tự nhiên gặp khi xem ảnh** (đều ghi `rejected` có lý do trong `review_log.csv`):
- *Box trùng khung đã bị bỏ ở nguồn:* lô được tạo sau khi bỏ box trùng (cùng lớp, IoU > 0,7). Khi hai vật chồng khít (người lớn bế em bé, hai cầu thủ chồng nhau, ngựa mẹ và ngựa con), chỉ còn một box, và segment của vật kia trùng khung box còn lại với IoU ≥ 0,7. Box bị xoá thật thì không còn box nào trùng khung. Validator đánh dấu `natural_hint` và xếp cuối hàng đợi; 3 ca ở seed 3158 (000000001818, 000000012748, 000000000872).
- *Vật bị che:* segment nằm trọn trong box, 3/4 cạnh khớp đúng, chỉ một cạnh box rộng hơn vì vật phía trước che mất (000000004134). Box lệch thật bị tịnh tiến nên không giữ được 3 cạnh khớp.

## 2. Vì sao báo hết ứng viên làm F1 giảm?

Số trên seed 3158 (cùng 9 lỗi luật, chỉ khác phần lỗi gán nhãn):

| Cách làm | Số mục nộp | F1 lỗi gán nhãn | F1 tổng |
|---|---:|---:|---:|
| Chỉ lỗi luật | 9 | — | ≈ 0.7 |
| Nộp hết 12 ứng viên, không xem ảnh (cặp lệch lớp đoán `class_swap`) | 21 | ≈ 0.7 | ≈ 0.8 |
| Đối chiếu + xem ảnh (bản nộp) | 17 | ≈ 0.9 | ≈ 0.9 |

F1 là trung bình điều hoà của precision và recall, nên mỗi mục báo thừa bị trừ như một mục bỏ sót. Nộp hết ứng viên thêm 4 FP chắc chắn (4 ca lệch tự nhiên ở trên), và với 3 cặp lệch lớp thì nếu đoán sai bên (detection hay panoptic sai) mỗi ca thành **1 FP + 1 FN** vì cặp `(type, target)` sai type. Recall không tăng thêm (ứng viên nào thật thì bản review cũng giữ), nên precision giảm kéo F1 xuống. Xem ảnh giữ nguyên recall và bỏ FP: chỉ ảnh mới cho biết bên nào ghi đúng vật (ví dụ 000000015254: box ghi `spoon` nhưng ảnh là bó cà rốt, nên detection sai, `class_swap`; 000000000285: ảnh là con gấu, panoptic ghi `bed`, nên `category_swap`).

F1 seed nộp là ≈ 0,9 chứ chưa phải 1,0: có ít nhất một chỗ sai hoặc thiếu trong phần gán nhãn. Theo RULES, tôi **không** đổi thử từng dòng rồi chấm lại để dò ra ca nào. Ca tôi kém chắc nhất là 000000009891 (túi có quai xách ghi `handbag`, panoptic ghi `backpack`): đã phóng to 5 lần và giữ kết luận theo những gì thấy trong ảnh.

## 3. Quyết định và lineage

- **QC v1: 17/250 = 6,8%** ảnh/cảnh lỗi (9 lỗi luật + 8 lỗi gán nhãn; `scene_leak` tính một lần cho cả cảnh). 6,8% > 2% (ngưỡng Day 7) nên **Hold**. Ngưỡng tính theo **tỉ lệ ảnh lỗi** chứ không theo số lỗi, vì một lô to hơn có nhiều lỗi hơn mà vẫn có thể tốt; tỉ lệ mới so được giữa các lô.
- Lineage (`submission/lineage.jsonl`): `inject` → `train R-021` (đã train trên v1) → `decision HOLD` cho `lab250_0b3d6d8bc552` → `release lab250_0b3d6d8bc552_v2 --parent lab250_0b3d6d8bc552`.
- `lineage.py impact` → `R-021: affected=True action=review_or_retrain`. **R-021 phải xem lại hoặc train lại** vì model đã học từ v1 có 6,8% ảnh lỗi: box lệch (2 ảnh), thiếu box (2 ảnh, ví dụ đuôi xe buýt chiếm nửa ảnh không có box), box nhầm lớp, box lặp, class_id 80 và các cảnh rò train/val (scene_283 có ảnh ở cả hai split, làm số đo val bị lạc quan). Sửa dataset thành v2 không sửa được trọng số đã học: phải đánh giá lại R-021 trên tập val sạch của v2, và nếu sai lệch đáng kể thì train lại trên v2. Lineage cho biết chính xác run nào dùng lô bị Hold.

## 4. Hash chứng minh gì, không chứng minh gì?

- **Chứng minh:** file không đổi một byte nào kể từ lúc lập manifest. `manifest.csv` của v2 có sha256 của 480 file; `.sha256` của zip tái lập được (`pack_release.py` cố định thứ tự, thời gian, quyền), nên người nhận đóng gói lại ra đúng mã. `check_handover.py` H1/H7 dùng hash để chứng minh v1 (`delivery/`) không bị sửa và nhãn trong v2 là bản chép nguyên của v1, không sửa tay.
- **Không chứng minh:** nhãn **đúng**. Hash của một nhãn sai vẫn khớp hoàn hảo. Hash cũng không nói ảnh có đúng nội dung không: ở 000000009914, sha256 trong manifest v1 là hash **hợp lệ** nhưng của ảnh khác (000000013348). Phải mở ảnh ra mới biết ảnh còn nguyên (giải mã được, đúng đĩa bánh mì, khớp nhãn) và chỉ manifest sai; vì vậy v2 giữ ảnh và ghi hash thật. Hash cũng không nói ai làm, theo guideline nào; những điều đó nằm ở truy vết và lineage.

## 5. Truy vết

- Ticket: model bỏ sót `bottle` bị che/ở mép; team AI thấy ở `scene_317`, `scene_909`. Changelog: v1.3 bắt buộc gán box cho `bottle` bị che > 50% hoặc cắt ở mép (v1.2 cho phép bỏ qua).
- **Tiêu chí:** ảnh thuộc **job** có guideline cũ v1.2 trong `jobs.csv` (J01–J04) **và** có ít nhất một box detection `bottle` trong `labels/` của lô. **tier_a**: các ảnh đó nằm trong scene_317/scene_909 (2 ảnh); **tier_b**: các ảnh đó ở cảnh khác, chưa ai báo (4 ảnh); **notify**: người gán + người kiểm của các job chứa ảnh tầng a, b: A04, A05, Q01, Q02.
- **Vì sao guideline theo job, không theo ảnh:** guideline là thứ người gán nhận khi mở job; ảnh trong cùng job được gán theo cùng một bản. Trường `guideline_version` ở từng ảnh có thể chính là lỗi `guideline_mismatch` (ở lô này 000000017379 ghi v1.2 nhưng job J07 là v1.3). Lấy theo ảnh sẽ kéo sai ảnh vào hoặc bỏ sót ảnh.
- Công cụ: `tools/trace_query.py` (đọc changelog, ticket, jobs, metadata, labels; không hard-code lớp hay cảnh nên dùng được cho đề ẩn).

## 6. Bug hoặc điểm chưa rõ trong lab

1. **`run_lab.py` lỗi trên Windows** khi không bật UTF-8 cho tiến trình con: `python -X utf8 scripts/run_lab.py ...` vẫn `CalledProcessError`, vì cờ `-X utf8` không truyền sang `inject_release.py` (con in tiếng Việt ra console cp1252). Cách chạy được: đặt biến môi trường `PYTHONUTF8=1` trước khi gọi. Tôi không sửa script.
2. **Lệch tự nhiên do bỏ box trùng khung:** việc bỏ box trùng (IoU > 0,7) khi tạo lô làm một số vật chồng khít không có box riêng, nên trông giống hệt `missing_box`. Đây là thiếu nhãn có thật trong dữ liệu (nên báo team gán nhãn) nhưng không phải lỗi gài của lô; tôi ghi `rejected` kèm lý do.
