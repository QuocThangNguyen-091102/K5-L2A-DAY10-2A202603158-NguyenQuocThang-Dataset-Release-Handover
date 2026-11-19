# Làm cá nhân — Nguyễn Quốc Thắng

- Seed luyện tập: 3158
- Repo: https://github.com/QuocThangNguyen-091102/K5-L2A-Day10-2A202603158-NguyenQuocThang-Dataset-Release-Handover
- Hình thức: làm một mình (các nhóm trong lớp đã đủ người); giảng viên cho phép dùng AI hỗ trợ ở mọi bước.

| Họ và tên | MSHV | Tài khoản GitHub | Phần chính |
|---|---|---|---|
| Nguyễn Quốc Thắng | 2A202603158 | QuocThangNguyen-091102 | toàn bộ: validator luật, đối chiếu, review ảnh, bàn giao v2, truy vết, bảo mật, đề ẩn |

## Chia việc theo pha (một người)

| Pha | Sản phẩm |
|---|---|
| P0 | tải dữ liệu, `runs/r3158`, lô sạch `runs/clean`, 6 seed thử thêm + 1 lô `--opaque` |
| P1 | `validator/validate.py` (9 loại lỗi luật) |
| P2 | đối chiếu detection ↔ panoptic trong validator, `tools/selftest_crosscheck.py`, `tools/review_tool.py`, `review_log.csv` |
| P3 | lineage HOLD v1, impact R-021 |
| P4 | `tools/make_handover.py`, lô v2, `check_handover.py` 17/17 PASS |
| P5 | `tools/trace_query.py`, `trace.json` |
| P6 | `security.md`; quy trình đề ẩn ở `tools/README.md` |
