# Bảo mật khi làm việc

> Gắn với lô vừa bàn giao: `lab250_0b3d6d8bc552` (v1, HOLD) và `lab250_0b3d6d8bc552_v2` (seed 3158).

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp

Không chép. Lô `lab250_0b3d6d8bc552` có 250 ảnh, nhãn, mask và cả giấy tờ nội bộ (jobs.csv ghi mã người gán A01–A05, người kiểm Q01–Q03, ticket của team AI). USB dễ mất, không mã hoá, và khi đã ra khỏi máy công ty thì không còn ai kiểm soát được bản sao: không thu hồi được, không biết ai đã xem. Gửi qua email cá nhân cũng sai vì dữ liệu nằm trên hộp thư ngoài hệ thống của công ty, có thể bị đồng bộ, sao lưu, quét. Nhờ người khác làm hộ thì người đó không phải người được giao job, mà lineage và truy vết (truyvet.csv, rework_queue.csv) đều dựa trên việc ai gán, ai kiểm. Cách đúng: dừng ở mốc gần nhất, commit phần code (validator, công cụ) lên repo, để dữ liệu ở lại máy/kho của công ty; nếu cần làm thêm thì xin quyền truy cập từ xa qua kênh công ty (VPN, máy ảo) hoặc báo trưởng nhóm để dời hạn.

## 2. Năm việc: được hay không

- **Mở job được giao trên máy công ty: ĐƯỢC.** Đúng người, đúng việc, đúng thiết bị được quản lý; thao tác được ghi lại.
- **Chụp màn hình gửi người quen: KHÔNG.** Ảnh chụp màn hình vẫn là dữ liệu (lô này có ảnh người thật, ví dụ 000000005060), và gửi ra ngoài là rò rỉ không thu hồi được. Hỏi chuyên môn thì mô tả bằng lời, không kèm dữ liệu.
- **Chép lô ra USB: KHÔNG.** Lý do như mục 1: mất kiểm soát bản sao, không mã hoá, không truy vết được.
- **Dán nhãn thật lên chatbot: KHÔNG.** Dữ liệu thật của dự án sẽ nằm trên máy chủ của bên thứ ba, có thể bị lưu hoặc dùng để huấn luyện. Bài lab này được dán vì ảnh COCO là dữ liệu công khai; với dữ liệu thật của khách hàng thì không, trừ khi công ty đã duyệt công cụ đó.
- **Đưa tài khoản CVAT cho đồng nghiệp: KHÔNG.** Mọi nhãn sẽ ghi dưới tên mình, nên lineage, rework_queue và danh sách notify trong trace.json đều trỏ sai người. Đồng nghiệp cần quyền thì xin quản trị cấp tài khoản riêng.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ

Kết luận: **Hold + báo người phụ trách**. Ví dụ trong lô seed 3158: `000000005060` (người đàn ông áo polo xanh chụp ảnh trong gương, mặt nhìn thẳng, rõ nét) và `000000012748` (người đàn ông áo đỏ bế em bé, thấy rõ mặt cả hai, có trẻ em). Cả hai ảnh đang nằm trong lô; `000000012748` còn ở lại v2.

Việc cần làm: không phát hành lô có ảnh này cho tới khi xử lý xong; báo trưởng nhóm dữ liệu / người phụ trách bảo mật (DPO), kèm tên ảnh và vị trí, không gửi ảnh qua kênh ngoài. Không tự làm mờ và không tự xoá vì: (1) làm mờ là sửa ảnh, sha256 trong manifest đổi, nhãn và mask phải gán lại, nên phải ra thành một phiên bản mới có lineage, không sửa lén trong v1; (2) cách làm mờ, phạm vi (mọi mặt hay chỉ mặt rõ, có trẻ em thì sao) và có giữ bản gốc hay không là quyết định của người phụ trách theo quy định, không phải của một người gán nhãn; (3) xoá ảnh làm mất bằng chứng và làm lệch số liệu QC, truy vết. Trạng thái lô: Hold cho tới khi người phụ trách quyết định và lô mới được đóng gói lại.
