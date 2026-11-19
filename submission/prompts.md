# Dùng AI

Làm cá nhân; giảng viên cho phép dùng AI ở mọi bước. Công cụ: Claude Code (VS Code).

| # | Việc | AI sai ở đâu | Tôi kiểm lại thế nào |
|---|---|---|---|
| 1 | Viết validator (luật + đối chiếu det ↔ panoptic) | Ngưỡng ban đầu bỏ sót box lệch nhỏ sát mép và thiếu box nằm trong box vật khác | Đo trên lô sạch (0 báo nhầm) và lô tự gài lỗi (recall 0.99); lỗi luật F1 ≈ 1.0 trên 7 seed |
| 2 | Công cụ xem ảnh | Font mất dấu, nhãn che vật khi phóng to | Mở ảnh xuất ra, sửa rồi xem lại |
| 3 | Đề xuất kết luận cho 12 ứng viên seed 3158 | Ban đầu coi 3 ca hai vật chồng khít và 1 ca bị che là lỗi | Tự mở lại từng ảnh; đo IoU trùng khung, kiểm cạnh box; ghi rejected kèm lý do |
| 4 | Dựng lô v2 | File CSV ghi CRLF làm lệch mã .sha256 khi clone | Clone lại repo, chạy check_handover: 17/17 PASS |
| 5 | Tự đo sau review | F1 lỗi gán nhãn ≈ 0.9, còn ít nhất 1 kết luận chưa đúng | Không dò từng dòng (RULES); xem lại ca kém chắc nhất |
