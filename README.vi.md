# Angelica Wardrobe — khung thời trang của game MMO, dựng lại thành ứng dụng 3D độc lập

*[English](README.md)*

Bộ công cụ đọc file dữ liệu của client **Thế Giới Hoàn Mỹ** (bản Việt của Perfect World, engine Angelica) và dựng
lại khung "Thu thập" thời trang trong game thành một ứng dụng 3D chạy riêng: mọi bộ thời trang mặc trên chính
nhân vật của bạn, đúng giao diện, màu nhuộm, hiệu ứng và động tác của game.

> **Không kèm dữ liệu game.** Repo chỉ có code. Mô hình, ảnh, giao diện, dữ liệu thuộc về nhà phát hành; công cụ
> tự tạo chúng trên máy từ bản game bạn đã có.

## Làm được gì

- **Đọc các định dạng không có tài liệu** của engine (tự dò ngược): gói `.pck/.pkx`, `elements.data` (CSDL game,
  nén MPPC từng bản ghi), mô hình `.ski`, khung xương `.bon`, động tác `.stck`, hiệu ứng `.gfx`, vật liệu `.mtl`,
  giao diện AUI XML và bảng chữ `.stf`.
- **Chuyển** hơn 2.300 mô hình thời trang sang glTF (`.glb`) có xương, giữ nguyên ảnh DDS gốc của game nên trình
  duyệt vẽ đúng khối DXT và mipmap như game.
- **Dựng lại khung thời trang từ chính file giao diện của game** (vị trí, khung, chữ, cách cuộn) với dữ liệu thật:
  315 bộ nữ / 258 bộ nam trong 6 nhóm sưu tập, tên, mô tả, độ hiếm, màu gốc, linh sủng, hiệu ứng.
- **Viết lại logic engine tìm được trong file chạy của game** (dịch ngược x86):
  - nặn mặt theo thanh trượt dị dung (nhóm xương, hệ số, các phép dời / xoay / co giãn),
  - dáng người theo thanh trượt (độ dài / độ dày / tỉ lệ từng xương như engine cập nhật xương),
  - shader thời trang (mặt nạ nhuộm trong không gian gamma, kênh nb_, phản chiếu, độ trong suốt).
- **Tự đối chiếu với game**: ảnh chụp cửa sổ game được so với ảnh trang web để khớp camera (Nelder–Mead trên
  tương quan cạnh), ánh sáng (sai số màu) và độ nét (năng lượng tần số cao); số đo dáng người đã kiểm tra khớp
  với game đang chạy.
- **Chạy như ứng dụng**: chương trình C# nhỏ bật máy chủ tại máy và mở trang trong cửa sổ riêng, không cần mạng.

## Chạy với bản game của bạn

Cần: Windows, Python 3.11+, `pip install -r requirements.txt`, client TGHM / Perfect World.

1. Đặt `tools/` trong thư mục game, hoặc tạo `tools/config.local.json`:
   `{"game": "D:\\Games\\TGHM Online", "data": "E:\\TGHM_Data"}` (thư mục kết quả, vài GB).
2. Trích đồ thời trang: `py tools/extract_fashion.py`
3. Xuất giao diện game: `py tools/build_ui.py`
4. Dựng tủ đồ (mô hình, ảnh, danh mục): `py tools/build_wardrobe.py`
5. Chép trang và tải three.js: `py tools/deploy_viewer.py`, rồi
   `powershell -File tools/viewer/get_three.ps1 -Out <data>\3D`
6. Mở `<data>\3D\XEM_TU_DO.bat`, hoặc tạo ứng dụng bằng `tools/viewer/launcher/build.ps1`.

Nhân vật mẫu là kiểu dị dung mới nhất bạn lưu trong game (`element\userdata\character\customize`).

## Cách làm

Dự án làm cùng trợ lý AI (Claude Code): AI làm phần lớn việc dò ngược, viết code và so ảnh; tôi đặt mục tiêu,
vào game chụp ảnh đối chiếu, kiểm tra kết quả với game và quyết định thế nào là "giống hệt game" ở từng bước.

## Giấy phép

Code: MIT (xem `LICENSE`). Dữ liệu, mô hình, ảnh, giao diện của game không thuộc giấy phép này và không được
phát tán.
