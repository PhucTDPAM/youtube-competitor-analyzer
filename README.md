# YouTube Competitor Analyzer

Ứng dụng dòng lệnh lấy dữ liệu từ kênh YouTube đối thủ thông qua **YouTube Data API v3** chính thức của Google (cách hợp lệ, không vi phạm điều khoản dịch vụ YouTube — không dùng kỹ thuật scraping trực tiếp trang web).

Dữ liệu lấy được, xuất ra file Excel gồm 3 sheet:

- **Kenh**: tên kênh, mô tả kênh, **từ khoá kênh**, số subscriber, tổng video, tổng lượt xem.
- **Video**: ngày đăng, tiêu đề, mô tả, số like, số view, số lượng comment, **từ khoá video** (tags).
- **Comment**: toàn bộ nội dung comment của từng video (tác giả, nội dung, số like, ngày đăng).

## Bước 1: Lấy YouTube Data API Key (miễn phí)

1. Truy cập https://console.cloud.google.com/
2. Đăng nhập bằng tài khoản Google, tạo một **Project mới** (hoặc chọn project có sẵn).
3. Vào menu **APIs & Services > Library**, tìm **"YouTube Data API v3"** và bấm **Enable**.
4. Vào **APIs & Services > Credentials** > **Create Credentials** > **API key**.
5. Copy API key vừa tạo (khuyến khích bấm "Restrict key" và giới hạn chỉ cho phép gọi YouTube Data API v3 để bảo mật).

Lưu ý: Mỗi API key có **quota miễn phí 10.000 unit/ngày**. Lấy danh sách video + chi tiết tốn ít unit, nhưng lấy **toàn bộ comment** của các video có hàng nghìn comment sẽ tốn nhiều unit hơn — nếu hết quota, đợi sang ngày hôm sau (quota reset theo giờ Thái Bình Dương) hoặc dùng `--max-videos` để giới hạn số video.

## Bước 2: Cài đặt

Mở PowerShell tại thư mục `youtube_competitor_analyzer`:

```powershell
pip install -r requirements.txt
```

## Bước 3: Cấu hình API key

Copy file `.env.example` thành `.env`, rồi dán API key vào:

```powershell
copy .env.example .env
```

Mở file `.env` và sửa thành:

```
YOUTUBE_API_KEY=api_key_that_ban_vua_lay
```

## Bước 4: Chạy ứng dụng

Có 2 cách dùng: **giao diện web** (khuyến khích, dễ dùng) hoặc **dòng lệnh**.

### Cách A — Giao diện web (Streamlit)

```powershell
streamlit run app.py --server.address localhost
```

Trình duyệt sẽ tự mở tại `http://localhost:8501`. Nếu không tự mở, copy link đó dán vào trình duyệt.

> Lưu ý bảo mật: luôn thêm `--server.address localhost` như trên. Nếu bỏ qua, Streamlit mặc định lắng nghe trên `0.0.0.0` — nếu máy bạn có địa chỉ IP public/router mở port, người lạ trên Internet có thể truy cập app và dùng ké API key của bạn.

Cách dùng trong giao diện:

1. Dán link/@handle/Channel ID kênh đối thủ, tuỳ chọn giới hạn số video / số comment nếu muốn (mặc định **lấy toàn bộ kênh**).
2. Bấm **"1. Tìm kênh & Quét quy mô"** — app sẽ hiện tên kênh, tổng số video, ước tính tổng số comment và cảnh báo nếu quota có thể không đủ.
3. Xem ước tính xong, bấm **"2. Lấy toàn bộ dữ liệu (video + comment) & Xuất Excel"** — có thanh tiến trình theo từng video.
4. Khi xong, xem trước dữ liệu ngay trên web (3 tab: Kênh / Video / Comment) và bấm **"Tải file Excel kết quả"** để tải về.

### Cách B — Dòng lệnh (CLI)

```powershell
python main.py "https://www.youtube.com/@TenKenhDoiThu" --out doi_thu.xlsx
```

Tham số:

- `channel` (bắt buộc): link kênh, `@handle`, hoặc Channel ID (bắt đầu bằng `UC...`).
- `--max-videos`: số video mới nhất muốn lấy (mặc định **0 = lấy toàn bộ kênh**). Kênh có hàng trăm/nghìn video sẽ chạy lâu và tốn nhiều quota.
- `--include-replies`: nếu muốn lấy cả các câu trả lời (reply) bên dưới mỗi comment, không chỉ comment gốc.
- `--max-comments-per-video`: giới hạn số comment tối đa lấy cho mỗi video (mặc định 0 = lấy toàn bộ). **Khuyến khích đặt giá trị này** (vd `500`) với các kênh lớn/viral — video có hàng trăm nghìn comment sẽ ngốn quota rất nhanh (thử nghiệm thực tế: chỉ 3 video của MrBeast đã trả về 152.669 comment).
- `--out`: tên file Excel xuất ra (mặc định `ket_qua_doi_thu.xlsx`).

Ví dụ giới hạn lại cho an toàn quota:

```powershell
python main.py "@TenKenhDoiThu" --max-videos 50 --max-comments-per-video 300 --out an_toan.xlsx
```

## Lưu ý

- Một số video có thể **tắt tính năng bình luận** → ứng dụng sẽ bỏ qua và ghi số comment = 0 cho video đó.
- Một số kênh **ẩn số lượt like** → cột `so_like` sẽ hiển thị "An".
- Không phải video nào cũng có **từ khoá (tags)** — tuỳ thuộc người đăng có khai báo hay không, tags không hiển thị công khai trên trang xem video mà chỉ lấy được qua API.
- File `.env` chứa API key riêng của bạn — không chia sẻ hoặc đưa lên Git công khai.
