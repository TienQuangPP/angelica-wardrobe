<p align="center">
  <img src="docs/banner.svg" alt="Angelica Wardrobe — dò ngược engine game MMO để dựng lại khung thời trang thành ứng dụng 3D độc lập" width="100%">
</p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
  <img alt="three.js r160" src="https://img.shields.io/badge/three.js-r160-000000?logo=threedotjs&logoColor=white">
  <img alt="glTF 2.0" src="https://img.shields.io/badge/glTF-2.0-87C540?logo=khronosgroup&logoColor=white">
  <img alt="Windows" src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white">
  <img alt="Giấy phép MIT" src="https://img.shields.io/badge/license-MIT-ff8fc8">
  <img alt="Làm cùng Claude Code" src="https://img.shields.io/badge/built%20with-Claude%20Code-D97757">
</p>

<p align="center">
  <a href="README.md">English</a> · <b>Tiếng Việt</b> ·
  <a href="#làm-được-gì">Tính năng</a> · <a href="#cách-hoạt-động">Cách hoạt động</a> ·
  <a href="#chạy-với-bản-game-của-bạn">Cách chạy</a> · <a href="docs/FORMATS.md">Ghi chú định dạng</a>
</p>

Bộ công cụ đọc file dữ liệu của client **Thế Giới Hoàn Mỹ** (bản Việt của Perfect World, engine Angelica) và dựng
lại khung "Thu thập" thời trang trong game thành một ứng dụng 3D chạy riêng: mọi bộ thời trang mặc trên chính
nhân vật của bạn, đúng giao diện, màu nhuộm, hiệu ứng và động tác của game.

> [!NOTE]
> **Không kèm dữ liệu game.** Repo chỉ có code. Mô hình, ảnh, giao diện, dữ liệu thuộc về nhà phát hành; công cụ
> tự tạo chúng trên máy từ bản game bạn đã có.

## Làm được gì

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🔍 Đọc định dạng không có tài liệu</h3>
      Tự dò ngược: gói <code>.pck/.pkx</code>, <code>elements.data</code> (nén MPPC từng bản ghi), mô hình
      <code>.ski</code>, khung xương <code>.bon</code>, động tác <code>.stck</code>, hiệu ứng <code>.gfx</code>,
      vật liệu <code>.mtl</code>, giao diện AUI, bảng chữ <code>.stf</code>.
    </td>
    <td width="50%" valign="top">
      <h3>🧊 Chuyển sang glTF</h3>
      Hơn 2.300 mô hình thời trang có xương xuất ra <code>.glb</code>, giữ nguyên ảnh DDS gốc của game nên trình
      duyệt vẽ đúng khối DXT và mipmap như game.
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>🧠 Viết lại logic engine</h3>
      Tìm trong mã x86 của game: nặn mặt theo thanh trượt dị dung, quy tắc xương cho dáng người, shader thời
      trang (mặt nạ nhuộm trong không gian gamma, kênh nb_, phản chiếu, độ trong suốt).
    </td>
    <td valign="top">
      <h3>🪟 Dựng lại khung trong game</h3>
      Từ chính file giao diện của game: vị trí, khung, chữ, cách cuộn, với dữ liệu thật — 315 bộ nữ / 258 bộ nam
      trong 6 nhóm, độ hiếm, màu gốc, linh sủng, hiệu ứng.
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>📏 Tự đối chiếu với game</h3>
      So ảnh chụp game với ảnh trang: khớp camera bằng Nelder–Mead trên tương quan cạnh, ánh sáng theo sai số
      màu, độ nét theo năng lượng tần số cao; số đo dáng người đã kiểm tra khớp với game đang chạy.
    </td>
    <td valign="top">
      <h3>🖥️ Chạy như ứng dụng</h3>
      Chương trình C# nhỏ bật máy chủ tại máy và mở trang trong cửa sổ riêng. Không cần mạng.
    </td>
  </tr>
</table>

## Cách hoạt động

<p align="center"><img src="docs/pipeline.svg" alt="Client game → bộ đọc → logic engine → dữ liệu tủ đồ → ứng dụng, đối chiếu bằng ảnh chụp game" width="100%"></p>

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

Code: MIT (xem [`LICENSE`](LICENSE)). Dữ liệu, mô hình, ảnh, giao diện của game không thuộc giấy phép này và không
được phát tán.
