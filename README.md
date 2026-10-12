# WifiMon - Giám sát client Wi-Fi

WifiMon thu thập thông tin client từ router/server Linux qua SSH, phát hiện thay
đổi trạng thái và ghi dữ liệu vào SQLite. Dự án cũng có dashboard Django để xem
dữ liệu và một tiện ích kiểm tra trạng thái router.

## Yêu cầu

- Python 3.10 trở lên.
- Máy chạy WifiMon có thể kết nối SSH tới router/server Linux.
- Router/server có các lệnh `ip` và `bridge`, dịch vụ dnsmasq cùng file DHCP
  lease (mặc định `/var/lib/misc/dnsmasq.leases`).
- Tài khoản SSH cần đọc được dữ liệu DHCP và các thông tin mạng. Một số lệnh
  truy vấn namespace và bridge sử dụng `sudo`.

## Cài đặt

Từ thư mục gốc của dự án, tạo và kích hoạt môi trường ảo rồi cài thư viện:

### Windows PowerShell

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Nếu PowerShell chặn việc kích hoạt môi trường ảo, chỉ áp dụng cho cửa sổ hiện
tại rồi kích hoạt lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Cấu hình WifiMon

Tạo file `.env` ở thư mục gốc dự án và khai báo thông tin SSH mà WifiMon sử
dụng:

```dotenv
SSH_HOST=192.0.2.10
SSH_PORT=22
SSH_USER=your_ssh_username
SSH_PASSWORD=your_ssh_password
```

Không commit `.env` hoặc mật khẩu vào Git. Kết nối SSH của WifiMon hiện tự động
chấp nhận host key chưa biết; trước khi chạy trên mạng thật, hãy xác minh router
đích và cân nhắc thay đổi chính sách xác thực host key trong
`wifimon/collector.py`.

Các thiết lập thu thập nằm trong [`wifimon/config.yaml`](wifimon/config.yaml):

| Khóa | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `scan_interval` | `10` | Khoảng nghỉ giữa các lần quét, tính bằng giây |
| `client_threshold` | `5` | Phát cảnh báo khi số client kết nối vượt ngưỡng |
| `lease_file` | `/var/lib/misc/dnsmasq.leases` | Đường dẫn file DHCP lease trên máy đích |
| `bridge` | `br-lab` | Tên bridge cần kiểm tra |
| `client_prefix` | `client` | Prefix của network namespace client |
| `ssid_map` | — | Ánh xạ bridge/interface sang SSID hiển thị |

Sửa các giá trị này cho phù hợp với cấu hình router/server của bạn.

## Chạy chương trình giám sát

Chạy từ thư mục gốc dự án (trong terminal đã kích hoạt môi trường ảo):

```powershell
python -m wifimon
```

Trên Linux dùng cùng lệnh `python -m wifimon`. Chương trình kết nối SSH, tạo
hoặc mở `wifimon.db` tại thư mục hiện tại, sau đó liên tục thu thập dữ liệu và
hiển thị dashboard terminal. Dừng bằng `Ctrl+C`.

## Chạy web dashboard

Dashboard Django đọc cùng file `wifimon.db` ở thư mục gốc. Hãy chạy WifiMon
ít nhất một lần để khởi tạo các bảng SQLite, sau đó mở terminal khác, kích hoạt
cùng môi trường ảo và chạy:

```powershell
cd dashboard
python manage.py runserver
```

Truy cập <http://127.0.0.1:8000/>. Có thể chạy kiểm tra cấu hình Django trước
bằng `python manage.py check` trong thư mục `dashboard`.

Dashboard có trang tổng quan, danh sách và chi tiết client, cùng lịch sử sự
kiện với bộ lọc và phân trang. Các API JSON cũng được cung cấp tại:

- `/api/clients/`
- `/api/events/` (có thể giới hạn số bản ghi bằng `?limit=50`)
- `/api/stats/`
- `/api/scan-history/` (có thể giới hạn số bản ghi bằng `?limit=100`)

## Kiểm tra trạng thái router

Tiện ích `app` có bộ biến môi trường riêng. Tạo `.env` ở thư mục gốc (có thể
sao chép `.env.example`) và cấu hình các khóa sau:

| Biến | Bắt buộc | Ý nghĩa |
| --- | --- | --- |
| `HOST` | Có | Địa chỉ router/server |
| `SSH_USER` | Có | Tài khoản SSH |
| `PASSWORD` hoặc `KEY` | Có ít nhất một | Mật khẩu hoặc đường dẫn tới private key SSH |
| `PORT` | Không | Cổng SSH, mặc định `22` |
| `BRIDGE` | Có | Tên bridge cần kiểm tra |
| `PREFIX` | Có | Prefix của namespace client |
| `TRUST_NEW_HOST` | Không | Mặc định `false`; chỉ bật nếu chủ ý chấp nhận host key mới |
| `SUDO` | Không | Dùng `sudo -n` khi truy vấn namespace; mặc định `false` |

`app` sử dụng `HOST`, `PORT`, `PASSWORD` và `KEY`; các khóa này không thay thế
`SSH_HOST`, `SSH_PORT` và `SSH_PASSWORD` của WifiMon. Chạy từ thư mục gốc:

```powershell
python -m app.main
```

Thêm `--sudo` để yêu cầu `sudo -n` khi kiểm tra namespace:

```powershell
python -m app.main --sudo
```

## Dữ liệu và cấu trúc

- `wifimon.db`: SQLite dùng chung bởi WifiMon và dashboard.
- `wifimon/`: thu thập dữ liệu, phát hiện sự kiện, lưu trữ và giao diện terminal.
- `dashboard/`: ứng dụng Django và API đọc dữ liệu giám sát.
- `app/`: tiện ích chẩn đoán router và namespace qua SSH.
