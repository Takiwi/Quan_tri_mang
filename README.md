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
dụng. Các biến dùng chung/riêng cho WifiMon và tiện ích kiểm tra được ghi chú
bên dưới:

```dotenv
SSH_HOST=192.0.2.10
SSH_PORT=22
SSH_USER=wifimon
SSH_PASSWORD=thay-bang-mat-khau-ssh

# app/check_state.py dùng PORT thay cho SSH_PORT
PORT=22
KEY=

# Phải khớp tên bridge và prefix namespace trên Ubuntu
BRIDGE=br-lab
PREFIX=client
TRUST_NEW_HOST=false
SUDO=false
```

Thay `192.0.2.10` bằng IP quản trị Ubuntu thực tế; dải `192.0.2.0/24` chỉ dành
cho ví dụ tài liệu, không phải địa chỉ server để kết nối.

Không commit `.env` hoặc mật khẩu vào Git. Kết nối SSH của WifiMon hiện tự động
chấp nhận host key chưa biết; trước khi chạy trên mạng thật, hãy xác minh router
đích và cân nhắc thay đổi chính sách xác thực host key trong
`wifimon/collector.py`.

Tiện ích `app` từ chối host key chưa được tin cậy theo mặc định. Hãy kết nối SSH
thủ công lần đầu và xác minh fingerprint máy chủ trước khi chấp nhận. `KEY` là
đường dẫn tới private key trên máy chạy ứng dụng; nếu dùng SSH key, có thể bỏ
`SSH_PASSWORD` nhưng cần cấu hình quyền `sudo` phù hợp cho các lệnh truy vấn
namespace/bridge.

Các thiết lập thu thập nằm trong [`wifimon/config.yaml`](wifimon/config.yaml):

| Khóa               | Mặc định                       | Ý nghĩa                                         |
| ------------------ | ------------------------------ | ----------------------------------------------- |
| `scan_interval`    | `10`                           | Khoảng nghỉ giữa các lần quét, tính bằng giây   |
| `client_threshold` | `5`                            | Phát cảnh báo khi số client kết nối vượt ngưỡng |
| `lease_file`       | `/var/lib/misc/dnsmasq.leases` | Đường dẫn file DHCP lease trên máy đích         |
| `bridge`           | `br-lab`                       | Tên bridge cần kiểm tra                         |
| `client_prefix`    | `client`                       | Prefix của network namespace client             |
| `ssid_map`         | —                              | Ánh xạ bridge/interface sang SSID hiển thị      |

Sửa các giá trị này cho phù hợp với cấu hình router/server của bạn.

## Chuẩn bị Ubuntu router/server

### 1. Cài gói và bật IPv4 forwarding

```bash
sudo apt update
sudo apt install -y openssh-server iproute2 dnsmasq isc-dhcp-client
sudo systemctl enable --now ssh
```

Bật IPv4 forwarding ngay và giữ lại sau khi khởi động lại:

```bash
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-wifimon.conf
sudo sysctl --system
```

### 2. Tạo bridge thử nghiệm

Chỉ dùng các lệnh này nếu `br-lab` chưa tồn tại và subnet `10.20.0.0/24` chưa
bị dùng trên mạng của bạn:

```bash
sudo ip link add br-lab type bridge
sudo ip address add 10.20.0.1/24 dev br-lab
sudo ip link set br-lab up
```

Các lệnh trên tạo bridge tạm thời; bridge sẽ mất sau khi Ubuntu reboot. Trên
máy dùng thật, hãy thêm bridge vào cấu hình Netplan hiện có hoặc thiết lập bằng
công cụ quản lý mạng của máy đó. Không ghi đè cấu hình Netplan hiện hữu nếu
chưa hiểu các interface/địa chỉ đang hoạt động, nhất là khi đang SSH từ xa.

### 3. Cấu hình dnsmasq làm DHCP cho bridge

Tạo file `/etc/dnsmasq.d/wifimon.conf`:

```ini
interface=br-lab
bind-interfaces
port=0
dhcp-authoritative
dhcp-range=10.20.0.100,10.20.0.200,255.255.255.0,12h
dhcp-leasefile=/var/lib/misc/dnsmasq.leases
```

`port=0` tắt phần DNS của dnsmasq; ví dụ chỉ dùng dịch vụ DHCP trên lab bridge.
Chỉ đặt `dhcp-authoritative` khi dnsmasq này là DHCP server duy nhất trên
`br-lab`. Nếu `dnsmasq` không khởi động được, kiểm tra lỗi và cấu hình đang có:

```bash
sudo dnsmasq --test
sudo systemctl restart dnsmasq
sudo systemctl enable dnsmasq
sudo systemctl status dnsmasq --no-pager
sudo journalctl -u dnsmasq -n 50 --no-pager
```

### 4. Tạo một client network namespace để thử DHCP

Chạy một lần trên lab mới. Lệnh tạo namespace sẽ báo lỗi nếu `client1` đã tồn
tại; khi đó bỏ qua bước tạo lại hoặc dùng tên khác bắt đầu bằng `client`.

```bash
sudo ip netns add client1
sudo ip link add veth-client1 type veth peer name eth0 netns client1
sudo ip link set veth-client1 master br-lab
sudo ip link set veth-client1 up
sudo ip -n client1 link set lo up
sudo ip -n client1 link set eth0 up
sudo ip netns exec client1 dhclient -v eth0
```

`client1` được nối vào bridge bằng một cặp veth và xin địa chỉ DHCP. Đây là
client thử nghiệm trong namespace, không phải thiết bị Wi-Fi thật. Để xóa riêng
client thử nghiệm này:

```bash
sudo ip netns delete client1
```

Lệnh xóa namespace sẽ ngắt client và xóa cặp veth tương ứng.

### 5. Cấp quyền SSH

Tạo hoặc chọn một tài khoản SSH không phải root; tài khoản cần đọc file lease và
chạy `ip`, `bridge`, `ip netns`. Các truy vấn namespace/bridge của WifiMon có
thể dùng `sudo`. Trong lab, cách đơn giản là dùng `SSH_PASSWORD` đồng thời là
mật khẩu SSH và mật khẩu `sudo` của tài khoản. Nếu đăng nhập bằng key hoặc không
muốn WifiMon gửi mật khẩu tới `sudo`, hãy cấu hình quyền `sudo` giới hạn cho
những lệnh cần thiết và kiểm thử quyền trước; không bật `NOPASSWD: ALL` trên máy
dùng thật.

`python -m app.main --sudo` sử dụng `sudo -n` chỉ cho phần đọc địa chỉ bên trong
namespace. Khi dùng `start_all --sudo`, tài khoản SSH phải chạy được phần đó
không cần nhập mật khẩu `sudo`; cờ này không thay quyền `sudo` mà WifiMon cần
cho truy vấn bridge/namespace.

### 6. Kiểm tra trên Ubuntu và từ máy chạy WifiMon

Trên Ubuntu, xác nhận các thành phần đã sẵn sàng:

```bash
ip -br address show br-lab
cat /proc/sys/net/ipv4/ip_forward
systemctl is-active dnsmasq
ip netns list
sudo ip netns exec client1 ip -br address
sudo cat /var/lib/misc/dnsmasq.leases
```

Kết quả mong đợi: bridge có `10.20.0.1/24`, forwarding in `1`, dnsmasq in
`active`, danh sách có `client1` và client nhận một IP `10.20.0.x`. File lease
có thể chưa có dòng cho tới khi client xin DHCP thành công.

Trên máy chạy ứng dụng, điền địa chỉ quản trị Ubuntu thật vào `SSH_HOST`, đặt `PORT`
và `SSH_PORT` đúng cổng SSH, cùng thông tin đăng nhập. Địa chỉ quản trị này
không nhất thiết là địa chỉ bridge lab `10.20.0.1`. Kiểm tra kết nối:

```bash
ssh wifimon@192.0.2.10
```

Sau đó từ thư mục dự án chạy `python -m app.main`. Chỉ tiếp tục khi bridge,
forwarding và dnsmasq đều `[OK]`; nếu chưa có namespace client, hãy tạo client
như bước trên. Chương trình có thể vẫn cho biết router sẵn sàng khi chưa có
namespace, nhưng WifiMon sẽ không có client lab để giám sát.

## Chạy toàn bộ hệ thống

Lệnh `start_all` lần lượt kiểm tra router bằng `app`, chạy WifiMon ở tiến trình
nền, rồi khởi động dashboard Django. Khi kiểm tra router không thành công hoặc
bridge/forwarding/dnsmasq chưa sẵn sàng, các bước tiếp theo sẽ không chạy. Nếu
WifiMon dừng bất ngờ, Django cũng sẽ được dừng. Nhấn `Ctrl+C` để kết thúc các
tiến trình.

Từ thư mục `dashboard`:

```powershell
python manage.py start_all
```

Mở <http://127.0.0.1:8000/>. Để dùng cổng/địa chỉ khác, thêm `--addrport`,
chẳng hạn `python manage.py start_all --addrport 0.0.0.0:8000`. Nếu tài khoản SSH
cần quyền `sudo -n` để kiểm tra namespace, thêm `--sudo` hoặc đặt `SUDO=true`
trong `.env`.

Lệnh này dùng chung `SSH_HOST`, `SSH_USER`, `SSH_PASSWORD` và `KEY` cho bước
kiểm tra router và WifiMon. Cần đặt cả `PORT` (được `app` sử dụng) lẫn
`SSH_PORT` (được WifiMon sử dụng). `BRIDGE`, `PREFIX`, `TRUST_NEW_HOST` và
`SUDO` chỉ được dùng bởi bước kiểm tra router.

Dashboard Django đọc file `wifimon.db` tại thư mục gốc; WifiMon tự tạo các bảng
khi khởi động.

Có thể chạy riêng từng thành phần khi cần chẩn đoán:

- Từ thư mục gốc: `python -m app.main` để kiểm tra router.
- Từ thư mục gốc: `python -m wifimon` để chỉ chạy WifiMon.
- Từ thư mục `dashboard`: `python manage.py runserver` để chỉ chạy web.

Có thể chạy `python manage.py check` trong thư mục `dashboard` để kiểm tra cấu
hình Django.

Dashboard có trang tổng quan, danh sách và chi tiết client, cùng lịch sử sự
kiện với bộ lọc và phân trang. Các API JSON cũng được cung cấp tại:

- `/api/clients/`
- `/api/events/` (có thể giới hạn số bản ghi bằng `?limit=50`)
- `/api/stats/`
- `/api/scan-history/` (có thể giới hạn số bản ghi bằng `?limit=100`)

## Kiểm tra trạng thái router

Để chạy riêng bước kiểm tra, dùng `.env` ở thư mục gốc với các khóa:

| Biến                      | Bắt buộc       | Ý nghĩa                                                     |
| ------------------------- | -------------- | ----------------------------------------------------------- |
| `SSH_HOST`                | Có             | Địa chỉ router/server                                       |
| `SSH_USER`                | Có             | Tài khoản SSH                                               |
| `SSH_PASSWORD` hoặc `KEY` | Có ít nhất một | Mật khẩu SSH hoặc đường dẫn private key                     |
| `PORT`                    | Không          | Cổng SSH, mặc định `22`                                     |
| `BRIDGE`                  | Có             | Tên bridge cần kiểm tra                                     |
| `PREFIX`                  | Có             | Prefix của namespace client                                 |
| `TRUST_NEW_HOST`          | Không          | Mặc định `false`; chỉ bật nếu chủ ý chấp nhận host key mới  |
| `SUDO`                    | Không          | Dùng `sudo -n` để đọc thông tin namespace; mặc định `false` |

`PORT` dùng cho `app`; WifiMon dùng `SSH_PORT`. Chạy từ thư mục gốc:

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
