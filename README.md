# WifiMon - Giám sát client Wi-Fi

WifiMon thu thập thông tin client từ router/server Linux qua SSH, phát hiện thay
đổi trạng thái và ghi dữ liệu vào PostgreSQL. Dashboard Django là giao diện
chính; Rich CLI vẫn có thể bật làm phương án dự phòng. Dự án cũng có tiện ích
kiểm tra trạng thái router.

## Yêu cầu

- Python 3.10 trở lên.
- Máy chạy WifiMon có thể kết nối SSH tới router/server Linux.
- Router/server Linux có AP interface mà `iw` đọc được, cùng các lệnh `ip`,
  `bridge`, dịch vụ dnsmasq và file DHCP lease (mặc định
  `/var/lib/misc/dnsmasq.leases`).
- Tài khoản SSH cần đọc được dữ liệu DHCP và các thông tin mạng. Một số lệnh
  truy vấn station AP, namespace và bridge sử dụng `sudo`.

## Cài đặt

Từ thư mục gốc của dự án, tạo và kích hoạt môi trường ảo rồi cài thư viện:

### Windows PowerShell

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Tạo `.env` từ mẫu và chỉnh thông tin SSH, PostgreSQL:

```powershell
Copy-Item .env.example .env
```

`DATABASE_URL` phải trỏ tới PostgreSQL local, ví dụ
`postgresql://USER:PASSWORD@localhost:5436/WifiMon_db`. Mã hóa URL các ký tự đặc
biệt trong username/password (ví dụ `@` thành `%40`). Không đưa `.env` lên Git.

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

Tạo `.env` từ mẫu bằng `cp .env.example .env`, sau đó cập nhật cấu hình SSH và
`DATABASE_URL` theo môi trường của bạn.

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

Không commit `.env` hoặc mật khẩu vào Git. WifiMon và tiện ích `app` chỉ chấp
nhận host key đã có trong `known_hosts`. Hãy kết nối SSH thủ công lần đầu, xác
minh fingerprint máy chủ rồi mới chấp nhận host key.

Tiện ích `app` cũng từ chối host key chưa được tin cậy theo mặc định. `KEY` là
đường dẫn tới private key trên máy chạy ứng dụng; nếu dùng SSH key, có thể bỏ
`SSH_PASSWORD` nhưng cần cấu hình quyền `sudo` phù hợp cho các lệnh truy vấn
namespace/bridge.

Các thiết lập thu thập nằm trong [`wifimon/config.yaml`](wifimon/config.yaml):

| Khóa               | Mặc định                       | Ý nghĩa                                         |
| ------------------ | ------------------------------ | ----------------------------------------------- |
| `scan_interval` | `10` | Khoảng nghỉ giữa các lần quét, tính bằng giây |
| `client_threshold` | `5` | Cảnh báo khi số station đang kết nối vượt ngưỡng |
| `disconnect_missed_scans` | `2` | Số lượt AP liên tiếp không thấy client trước khi đánh dấu mất kết nối |
| `ap_interface` | `wlan0` | Interface AP; dùng để đọc station và SSID qua `iw` |
| `lease_file` | `/var/lib/misc/dnsmasq.leases` | Đường dẫn file DHCP lease trên máy đích |
| `bridge` | `br-lab` | Tên bridge cần kiểm tra và ánh xạ SSID dự phòng |
| `client_prefix` | `client` | Prefix của network namespace client |
| `ssid_map` | — | Ánh xạ bridge sang SSID dự phòng |

Sửa các giá trị này cho phù hợp với cấu hình router/server của bạn.

## Chuẩn bị Ubuntu router/server mô phỏng AP

Các bước dưới đây tạo một AP Wi-Fi và một client Wi-Fi ảo trên cùng máy Ubuntu.
`mac80211_hwsim` mô phỏng radio 802.11 bằng phần mềm, nên không cần card Wi-Fi
thật. AP dùng `hostapd`, còn `dnsmasq` cấp địa chỉ DHCP. Mạng này chỉ là lab cục
bộ, không tự cung cấp Internet.

Nên thực hiện trong máy ảo Ubuntu hoặc máy lab riêng. Các lệnh tạo bridge và
thay đổi interface có thể làm gián đoạn kết nối; không chạy chúng trên máy
đang được quản trị từ xa nếu chưa có cách khôi phục.

### 1. Cài công cụ và nạp radio Wi-Fi ảo

```bash
sudo apt update
sudo apt install -y hostapd iw dnsmasq iproute2 kmod isc-dhcp-client openssh-server
sudo systemctl enable --now ssh
sudo modprobe mac80211_hwsim radios=2
iw dev
```

Module tạo hai radio Wi-Fi ảo (thường xuất hiện là `wlan0` và `wlan1`): một
radio làm AP, radio còn lại làm client. Xem kết quả `iw dev` và dùng đúng tên
interface trên máy của bạn ở các bước sau; không giả định tên nếu máy có sẵn
card Wi-Fi khác. `iw` là công cụ xem và điều khiển interface Wi-Fi ở mức thấp.

### 2. Tạo bridge và bật IPv4 forwarding

Chỉ dùng subnet `10.20.0.0/24` nếu dải này chưa được sử dụng trên máy/mạng của
bạn. Nếu `br-lab` đã tồn tại, bỏ qua các lệnh tạo bridge bên dưới và kiểm tra
địa chỉ/cấu hình hiện có trước; không thêm địa chỉ trùng lặp.

```bash
sudo ip link add br-lab type bridge
sudo ip address add 10.20.0.1/24 dev br-lab
sudo ip link set br-lab up
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-wifimon.conf
sudo sysctl --system
```

Bridge là cầu nối lớp 2 cho lưu lượng giữa AP và mạng lab. Ở cấu hình bên dưới,
`hostapd` tự đưa interface AP vào `br-lab`; không thêm interface client vào
bridge bằng tay. `ip_forward=1` cho phép Ubuntu chuyển tiếp IPv4 và được tiện
ích kiểm tra trạng thái của dự án yêu cầu; các bước này chưa cấu hình NAT hay
đường ra Internet.

Bridge tạo bằng `ip` chỉ tồn tại đến khi reboot. Cấu hình radio, bridge và
namespace trong hướng dẫn này là lab tạm thời; sau khi khởi động lại, hãy tạo
lại chúng. Không ghi đè Netplan hoặc cấu hình mạng hiện hữu.

### 3. Cấu hình hostapd cho AP

Tạo `/etc/hostapd/hostapd.conf`, thay `wlan0` bằng interface radio AP của bạn:

```ini
interface=wlan0
driver=nl80211
bridge=br-lab
ssid=WifiMon-Lab
hw_mode=g
channel=1
auth_algs=1
wmm_enabled=0
```

`hostapd` điều khiển radio ở chế độ access point (AP), phát SSID `WifiMon-Lab`
trên băng tần 2.4 GHz, kênh 1. Cấu hình mẫu để mạng mở cho dễ thử nghiệm; chỉ
dùng trong lab cô lập, không dùng cho mạng thật. `bridge=br-lab` gắn phía AP
vào bridge để client Wi-Fi gửi DHCP tới máy Ubuntu. Đặt `ap_interface` trong
`wifimon/config.yaml` trùng với giá trị `interface` trong file hostapd.

Khởi động hostapd sau khi đã tạo bridge:

```bash
sudo systemctl unmask hostapd
sudo systemctl restart hostapd
sudo systemctl status hostapd --no-pager
sudo journalctl -u hostapd -n 50 --no-pager
```

Nếu dịch vụ lỗi, xác nhận tên interface, file cấu hình và `br-lab` trước khi
tiếp tục.

### 4. Cấu hình dnsmasq cấp DHCP

Tạo `/etc/dnsmasq.d/wifimon.conf`:

```ini
interface=br-lab
bind-interfaces
port=0
dhcp-authoritative
dhcp-range=10.20.0.100,10.20.0.200,255.255.255.0,12h
dhcp-leasefile=/var/lib/misc/dnsmasq.leases
```

`dnsmasq` lắng nghe DHCP trên bridge, cấp client địa chỉ từ `10.20.0.100` đến
`10.20.0.200` và lưu lease để WifiMon đọc. `port=0` tắt DNS của dnsmasq; ở đây
chỉ dùng DHCP. Chỉ dùng `dhcp-authoritative` khi dnsmasq này là DHCP server duy
nhất trên `br-lab`.

Kiểm tra cấu hình rồi khởi động dịch vụ:

```bash
sudo dnsmasq --test
sudo systemctl restart dnsmasq
sudo systemctl status dnsmasq --no-pager
sudo journalctl -u dnsmasq -n 50 --no-pager
```

Nếu dnsmasq không khởi động, kiểm tra cấu hình dnsmasq có sẵn trên Ubuntu và
xem log; có thể máy đang chạy một dịch vụ khác chiếm cổng hoặc đã có cấu hình
DHCP trùng lặp.

### 5. Kết nối client Wi-Fi ảo

Tạo namespace `client1` để tách client khỏi network namespace chính của Ubuntu.
Thay `wlan1` bằng interface radio còn lại. Lệnh di chuyển interface đặt radio
client vào namespace, nhưng không thay đổi AP:

```bash
sudo ip netns add client1
sudo ip link set wlan1 netns client1
sudo ip -n client1 link set lo up
sudo ip -n client1 link set wlan1 up
sudo ip netns exec client1 iw dev wlan1 connect -w WifiMon-Lab
sudo ip netns exec client1 dhclient -v wlan1
```

`iw ... connect` khiến radio client dò và kết nối tới SSID; `dhclient` gửi yêu
cầu DHCP để nhận địa chỉ từ dnsmasq. Namespace là một vùng mạng Linux riêng:
nó giúp kiểm thử như một client độc lập, đồng thời cho phép tiện ích `app`
nhận diện client có prefix `client`. Nếu báo `File exists`, namespace hoặc kết
nối đã tồn tại; kiểm tra trạng thái trước khi chạy lại.

### 6. Cấp quyền SSH

Tạo hoặc chọn một tài khoản SSH không phải root; tài khoản cần đọc file lease và
chạy `ip`, `bridge`, `ip netns`, `iw`. Một số truy vấn namespace/bridge/AP dùng
`sudo`. Trong lab, cách đơn giản là dùng `SSH_PASSWORD` đồng thời là mật khẩu
SSH và mật khẩu `sudo` của tài khoản. WifiMon gửi mật khẩu sudo qua stdin của
kênh SSH, không chèn vào chuỗi lệnh. Nếu đăng nhập bằng key hoặc không muốn
WifiMon gửi mật khẩu tới `sudo`, hãy cấu hình quyền sudo giới hạn cho những lệnh
cần thiết và kiểm thử quyền trước; không bật `NOPASSWD: ALL` trên máy dùng thật.

WifiMon truy vấn client đang association bằng
`sudo iw dev <ap_interface> station dump`; vì vậy cần quyền đọc station trên
interface AP. Khi lệnh này lỗi, lượt quét được bỏ qua và không làm thay đổi
trạng thái client trong DB. Các nguồn DHCP/neighbor/namespace/FDB chỉ bổ sung
IP, hostname và thông tin phụ; chúng không được dùng thay danh sách station của
AP.

`python -m app.main --sudo` sử dụng `sudo -n` chỉ cho phần đọc địa chỉ bên trong
namespace. Khi dùng `start_all --sudo`, tài khoản SSH phải chạy được phần đó
không cần nhập mật khẩu `sudo`; cờ này không thay quyền `sudo` mà WifiMon cần
cho truy vấn bridge/namespace.

### 7. Kiểm tra trên Ubuntu và từ máy chạy WifiMon

Trên Ubuntu, xác nhận các thành phần đã sẵn sàng:

```bash
ip -br address show br-lab
cat /proc/sys/net/ipv4/ip_forward
iw dev
sudo iw dev wlan0 station dump
sudo iw dev wlan0 info
systemctl is-active dnsmasq
systemctl is-active hostapd
ip netns list
sudo ip netns exec client1 ip -br address show wlan1
sudo cat /var/lib/misc/dnsmasq.leases
```

Kết quả mong đợi: bridge có `10.20.0.1/24`, forwarding in `1`, cả hai dịch vụ
ở trạng thái `active`, namespace có `client1` và interface client nhận IP
`10.20.0.x`. `iw dev wlan0 station dump` liệt kê MAC client đã association;
`iw dev wlan0 info` hiển thị SSID AP. `iw dev` cho biết interface nào đang là
AP/client; file lease có thể chưa có dòng cho tới khi client kết nối và xin
DHCP thành công.

Trên máy chạy ứng dụng, điền địa chỉ quản trị Ubuntu thật vào `SSH_HOST`, đặt `PORT`
và `SSH_PORT` đúng cổng SSH, cùng thông tin đăng nhập. Địa chỉ quản trị này
không nhất thiết là địa chỉ bridge lab `10.20.0.1`. Kiểm tra kết nối:

```bash
ssh wifimon@192.0.2.10
```

Sau đó từ thư mục dự án chạy `python -m app.main`. Trước khi chạy WifiMon, xác
nhận bridge, forwarding, dnsmasq, hostapd và truy vấn `iw ... station dump` đều
hoạt động. Nếu vừa reboot Ubuntu, hãy nạp lại module, tạo bridge và namespace,
rồi khởi động lại hostapd/dnsmasq trước khi chạy kiểm tra.

## Chạy toàn bộ hệ thống

Lệnh `start_all` khởi động PostgreSQL bằng Docker Compose, kiểm tra router bằng
`app`, chạy WifiMon ở tiến trình nền, rồi khởi động dashboard Django. PostgreSQL
được bind vào loopback (`127.0.0.1`) và dữ liệu lưu trong named volume riêng.
Khi DB hoặc kiểm tra router không sẵn sàng, các bước tiếp theo sẽ không chạy.
Nếu WifiMon dừng bất ngờ, Django cũng sẽ được dừng. Nhấn `Ctrl+C` để kết thúc
các tiến trình.

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

WifiMon tự tạo/cập nhật các bảng `clients`, `events` và `scan_history` khi khởi
động; Django đọc cùng PostgreSQL. Dữ liệu SQLite cũ (nếu có) được giữ nguyên,
không tự động import sang database mới.

Có thể chạy riêng từng thành phần khi cần chẩn đoán:

- Từ thư mục gốc: `python -m app.main` để kiểm tra router.
- Từ thư mục gốc: `python scripts/start_postgres.py` để khởi động riêng DB.
- Từ thư mục gốc: `python -m wifimon` để chạy WifiMon không có terminal dashboard.
- Từ thư mục gốc: `python -m wifimon --cli` để bật Rich CLI dự phòng.
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

- PostgreSQL: lưu bảng `clients`, `events`, `scan_history`; được khởi chạy bằng
  Docker Compose và dùng volume `wifimon-postgres-data`.
- `wifimon.db` cũ (nếu có): không còn được dùng và không bị xóa/import.
- `wifimon/`: thu thập dữ liệu, phát hiện sự kiện, lưu trữ và giao diện terminal.
- `dashboard/`: ứng dụng Django và API đọc dữ liệu giám sát.
- `app/`: tiện ích chẩn đoán router và namespace qua SSH.
