# WifiMon — Tài liệu dự án và nội dung thuyết trình

Tài liệu này tổng hợp mục tiêu, kiến trúc, cách hoạt động, cách cài đặt, cách
trình diễn và các giới hạn hiện tại của WifiMon. Có thể dùng trực tiếp làm tài
liệu chuẩn bị PowerPoint hoặc làm nội dung thuyết trình.

> **Lưu ý về phạm vi:** WifiMon là công cụ giám sát client trong mạng Wi-Fi/lab
> do người vận hành quản lý. Hệ thống đọc dữ liệu từ Ubuntu router/server qua
> SSH; không tự tạo AP, không thay thế router và không tự động chặn thiết bị.

## 1. Tóm tắt dự án

**WifiMon** là hệ thống giám sát client Wi-Fi theo chu kỳ. Ứng dụng kết nối tới
Ubuntu router/server qua SSH, thu thập thông tin client từ nhiều nguồn Linux,
hợp nhất kết quả theo địa chỉ MAC, phát hiện thay đổi trạng thái và lưu dữ liệu
vào PostgreSQL. Người dùng xem trạng thái hiện tại, lịch sử sự kiện và thống kê
qua dashboard web Django; Rich CLI được giữ làm phương án dự phòng.

### Thông tin nhanh

| Hạng mục | Nội dung |
| --- | --- |
| Tên dự án | WifiMon — Giám sát client Wi-Fi |
| Mục đích | Theo dõi client, trạng thái kết nối và sự kiện trong mạng lab/AP |
| Máy chạy ứng dụng | Windows hoặc Linux có Python |
| Máy được giám sát | Ubuntu/Linux router hoặc server có SSH |
| Ngôn ngữ/chính | Python |
| Thành phần chính | Paramiko, PostgreSQL (Docker), Django, Rich |
| Chu kỳ quét mặc định | 10 giây |
| Ngưỡng cảnh báo mặc định | Trên 5 client đang kết nối |
| Phạm vi mạng | Mạng/lab do người dùng quản trị; không phải công cụ giám sát mạng bên ngoài |

## 2. Bài toán và mục tiêu

### Bài toán

- Trạng thái client nằm rải rác trong DHCP lease, bảng neighbor, network
  namespace và bridge forwarding database (FDB).
- Việc kiểm tra bằng tay nhiều lệnh Linux khiến khó theo dõi biến động theo
  thời gian.
- Người vận hành cần biết client nào mới xuất hiện, quay lại, biến mất hoặc
  khiến số lượng client vượt ngưỡng.
- Cần một nơi lưu lịch sử để xem lại tình hình và trình bày trạng thái một cách
  trực quan.

### Mục tiêu

1. Thu thập thông tin client từ Ubuntu qua SSH theo chu kỳ.
2. Hợp nhất dữ liệu từ nhiều nguồn, dùng MAC làm khóa nhận diện chính.
3. Phát hiện các sự kiện kết nối mới, mất kết nối, quay lại và vượt ngưỡng.
4. Lưu client, sự kiện và lịch sử quét trong PostgreSQL.
5. Hiển thị dữ liệu trên dashboard web và API JSON; có Rich CLI dự phòng.
6. Có tiện ích kiểm tra nhanh các điều kiện cần thiết trên router/server.

### Ngoài phạm vi hiện tại

- Không cấu hình hoặc quản trị AP/router tự động.
- Không tự tạo AP hoặc cấp DHCP; các dịch vụ này được chuẩn bị riêng trên máy
  Ubuntu.
- Không tự chặn, cách ly hoặc ngắt kết nối client.
- Không có xác thực người dùng cho dashboard và API trong cấu hình phát triển
  hiện tại.
- Không có dịch vụ triển khai production hay cơ chế HA.

## 3. Kiến trúc tổng quan

```text
┌──────────────────────────── Máy Ubuntu/Linux được giám sát ───────────────────────────┐
│  hostapd / AP (nếu dùng)     dnsmasq / DHCP       bridge, ip neigh, namespace, FDB    │
└───────────────────────────────────┬───────────────────────────────────────────────────┘
                                    │ SSH
                                    ▼
┌──────────────────────── Máy chạy WifiMon ─────────────────────────────────────────────┐
│  Config → SSH Collector → Hợp nhất theo MAC → Detector → Alerts (terminal)            │
│                                      │                                                 │
│                                      ▼                                                 │
│                            PostgreSQL (Docker)                                       │
│                           ┌──────────┴─────────┐                                      │
│                           ▼                    ▼                                      │
│                  Rich CLI dự phòng     Django dashboard + JSON API                    │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Các thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| `wifimon/config.py` | Đọc YAML và `.env`, tạo cấu hình SSH và các mặc định |
| `wifimon/collector.py` | Kết nối SSH, thu thập dữ liệu từ Linux và hợp nhất client |
| `wifimon/detector.py` | So sánh kết quả quét với trạng thái PostgreSQL, tạo sự kiện |
| `wifimon/storage.py` | Tạo và truy vấn bảng PostgreSQL; cung cấp dữ liệu cho dashboard |
| `wifimon/alerts.py` | In cảnh báo bằng Rich ra terminal |
| `wifimon/cli.py` | Hiển thị dashboard terminal |
| `wifimon/main.py` | Khởi tạo thành phần và chạy vòng lặp quét |
| `app/` | Kiểm tra kết nối và trạng thái bridge, forwarding, dnsmasq, namespace |
| `dashboard/` | Trang web Django, các trang chi tiết và API JSON |

## 4. Luồng hoạt động của một lần quét

1. Đọc `wifimon/config.yaml` và biến môi trường trong `.env`.
2. Mở kết nối SSH tới Ubuntu router/server.
3. Đọc danh sách station trực tiếp trên interface AP bằng
   `iw dev <ap_interface> station dump`. Đây là nguồn có thẩm quyền để xác
   nhận client đang association. Đọc thêm:
   - **DHCP lease của dnsmasq:** IP, hostname và thời hạn lease.
   - **Neighbor/ARP (`ip neigh`):** ánh xạ IP–MAC và trạng thái neighbor.
   - **Network namespace:** interface, địa chỉ IP, MAC và trạng thái của các
     namespace có tên bắt đầu bằng prefix cấu hình.
   - **Bridge FDB (`bridge fdb`):** các MAC được bridge học.
   SSID được đọc từ `iw dev <ap_interface> info`, fallback về ánh xạ cấu hình.
4. Chuẩn hóa MAC và gộp enrichment theo station MAC. Lease, neighbor,
   namespace và FDB bổ sung IP/hostname/namespace, nhưng không được dùng để
   khẳng định client đang kết nối AP.
5. Detector so sánh danh sách hiện tại với bảng client trong PostgreSQL:
   - MAC chưa từng có: `client_connected`.
   - Client cũ đang disconnected nay kết nối lại: `client_returned`.
   - Client vắng mặt trong một lần quét AP: chuyển sang `stale`; chỉ phát
     `client_disconnected` sau số lượt vắng liên tiếp cấu hình.
   - Khi số client lần đầu vượt ngưỡng: `threshold_exceeded`; khi trở về mức
     cho phép: `threshold_recovered`.
6. Lưu trạng thái client, sự kiện và bản ghi tổng hợp của lần quét.
7. In cảnh báo và cập nhật dữ liệu cho dashboard Django; có thể bật Rich CLI.
8. Chờ chu kỳ kế tiếp; `Ctrl+C` để dừng.

### Trạng thái client

- `connected`: station xuất hiện trong danh sách AP ở lần quét thành công.
- `stale`: station vắng trong ít nhất một lần quét AP liên tiếp nhưng chưa đạt
  ngưỡng xác nhận mất.
- `disconnected`: station vắng qua số lần quét AP liên tiếp được cấu hình.

Nếu không đọc được station list, lượt quét được đánh dấu không đáng tin cậy và
bỏ qua cập nhật trạng thái, disconnect, threshold và scan history. `connected_since`
được ước tính từ trường `connected time` của `iw` (giây), không phải thời điểm
được ghi bởi đồng hồ AP; `first_seen` vẫn là thời điểm WifiMon phát hiện lần đầu.

## 5. Công nghệ sử dụng

| Công nghệ | Vai trò |
| --- | --- |
| Python 3.10+ | Ngôn ngữ ứng dụng |
| Paramiko | SSH từ ứng dụng tới Ubuntu/Linux |
| PyYAML | Đọc cấu hình YAML |
| python-dotenv | Nạp biến môi trường từ `.env` |
| PostgreSQL | Lưu client, sự kiện và lịch sử quét; chạy trong Docker Compose |
| Django | Dashboard web và JSON API |
| Rich | Giao diện terminal, bảng màu và cảnh báo |
| `iproute2` (`ip`, `bridge`) | Thông tin interface, namespace, neighbor và bridge FDB trên Linux |
| dnsmasq | DHCP lease mà collector có thể đọc |
| hostapd / iw / mac80211_hwsim | Công cụ tùy chọn để dựng AP và radio Wi-Fi mô phỏng trong lab Ubuntu |

`hostapd`, `iw` và `mac80211_hwsim` là hạ tầng lab, không phải thư viện Python
và không được WifiMon điều khiển tự động.

## 6. Cơ sở dữ liệu

WifiMon tự tạo các bảng khi khởi động. Django đọc cùng file `wifimon.db`; các
model Django được khai báo `managed=False`, vì vậy Django không quản lý schema
của những bảng này.

### `clients`

| Trường | Ý nghĩa |
| --- | --- |
| `mac` | MAC address, khóa chính |
| `ip` | Địa chỉ IP gần nhất |
| `hostname` | Hostname lấy từ DHCP lease nếu có |
| `ssid` | SSID đọc từ interface AP, fallback về ánh xạ cấu hình |
| `namespace` | Namespace client nếu phát hiện được |
| `connected_since` | Thời điểm association ước tính từ thời lượng station trên AP |
| `first_seen` | Thời điểm WifiMon phát hiện lần đầu |
| `last_seen` | Thời điểm cuối cùng được nhìn thấy trong snapshot AP |
| `state` | `connected`, `stale` hoặc `disconnected` |
| `source` | Nguồn xác nhận trạng thái, hiện là `ap_station` |
| `missed_scans` | Số lượt quét AP liên tiếp không thấy station |

### `events`

Lưu ID, thời điểm, loại sự kiện, MAC liên quan, nội dung và mức độ nghiêm trọng.

### `scan_history`

Lưu thời điểm quét, tổng số client và số client đang connected để hiển thị lịch
sử/thống kê.

## 7. Tính năng người dùng

### Dashboard terminal

- Thống kê tổng client, connected, stale và disconnected.
- Danh sách client với MAC, IP, hostname, SSID, namespace và thời gian.
- Các sự kiện gần đây.
- Cập nhật theo chu kỳ quét bằng Rich Live nếu thư viện Rich khả dụng.

### Dashboard web

- Trang tổng quan và thời điểm quét gần nhất.
- Danh sách client; hỗ trợ tìm kiếm theo MAC, IP, hostname và lọc trạng thái.
- Trang chi tiết client và các sự kiện liên quan.
- Trang lịch sử sự kiện có lọc loại/mức độ và phân trang.

### JSON API

| Endpoint | Nội dung |
| --- | --- |
| `/api/clients/` | Danh sách client |
| `/api/events/` | Sự kiện gần đây; nhận tham số `limit` |
| `/api/stats/` | Tổng số và số lượng theo trạng thái, lần quét cuối |
| `/api/scan-history/` | Lịch sử quét; nhận tham số `limit`, sắp tăng dần theo thời gian |

### Kiểm tra router/server

`app` kiểm tra khả năng truy vấn namespace, bridge, `ip_forward`, dnsmasq và
DHCP lease. Tiện ích này giúp kiểm tra điều kiện môi trường trước khi chạy đầy
đủ hệ thống; nó không kiểm tra mọi cấu hình radio/AP.

## 8. Môi trường mạng mô phỏng

Trong lab Ubuntu, có thể dựng AP và client ảo bằng `mac80211_hwsim`:

- `mac80211_hwsim` tạo radio Wi-Fi ảo để thử nghiệm mà không cần card Wi-Fi
  thật.
- `hostapd` đặt một radio ở chế độ AP và phát SSID.
- `dnsmasq` cấp IP qua DHCP cho client.
- `iw` kiểm tra interface và kết nối radio client tới SSID.
- `br-lab` nối phía AP vào mạng lab.
- Namespace `client1` tách client thử nghiệm khỏi network namespace chính.

Quy trình lệnh, cấu hình mẫu, cách kiểm tra và lưu ý an toàn nằm trong mục
**“Chuẩn bị Ubuntu router/server mô phỏng AP”** của [README.md](./README.md).
Phần mô phỏng mặc định chỉ là mạng nội bộ, không cấu hình NAT/Internet. Không
dùng SSID mở mẫu cho mạng thật và không thực hiện cấu hình bridge/interface
trên server đang SSH từ xa nếu chưa có phương án khôi phục.

## 9. Cài đặt và chạy

### Yêu cầu

- Python 3.10 trở lên trên máy chạy ứng dụng.
- Ubuntu/Linux router/server có SSH và các lệnh `ip`, `bridge`.
- dnsmasq và file lease theo đường dẫn cấu hình, mặc định
  `/var/lib/misc/dnsmasq.leases`.
- Tài khoản SSH đủ quyền đọc dữ liệu cần thiết và chạy truy vấn namespace/
  bridge theo cấu hình quyền.

### Cài thư viện

Từ thư mục gốc repository, trên Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Trên Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Cấu hình SSH

Tạo `.env` trong thư mục gốc. Ví dụ dưới đây dùng địa chỉ dành riêng cho tài
liệu; thay bằng thông tin máy lab của bạn:

```dotenv
SSH_HOST=192.0.2.10
SSH_PORT=22
SSH_USER=wifimon
SSH_PASSWORD=thay-bang-mat-khau

# Các biến app dùng để kiểm tra router
PORT=22
KEY=
BRIDGE=br-lab
PREFIX=client
TRUST_NEW_HOST=false
SUDO=false
```

Không đưa `.env`, mật khẩu hoặc private key vào Git. `SSH_PORT` được WifiMon
dùng; tiện ích `app` hiện dùng biến `PORT`. Nếu xác thực bằng SSH key, cấu hình
`KEY` theo hướng dẫn trong README và bỏ mật khẩu nếu không cần.

### Chạy từng thành phần

```bash
# Từ thư mục gốc: kiểm tra router/server
python -m app.main

# Từ thư mục gốc: chạy collector và detector (dashboard chính là Django)
python -m wifimon

# Từ thư mục gốc: bật Rich CLI dự phòng
python -m wifimon --cli

# Từ thư mục dashboard: chạy web dashboard
python manage.py runserver
```

Để kiểm tra router, `BRIDGE` và `PREFIX` phải khớp với cấu hình trên Ubuntu.
WifiMon cần `SSH_HOST`, `SSH_USER` và thông tin xác thực SSH. Đảm bảo quyền đọc
lease và quyền sudo cần thiết đã hoạt động trước khi đánh giá kết quả quét.

### Chạy cả hệ thống

Từ thư mục `dashboard`:

```bash
python manage.py start_all
```

Lệnh khởi động PostgreSQL trong Docker, kiểm tra router, khởi chạy WifiMon, rồi
chạy Django tại `http://127.0.0.1:8000/`. PostgreSQL được bind vào loopback
`127.0.0.1` và dữ liệu được giữ trong named volume riêng. Dừng các tiến trình
bằng `Ctrl+C`. Có thể dùng `--addrport` để chọn địa chỉ/cổng; chỉ bind
`0.0.0.0` trong mạng tin cậy và khi đã xem xét cấu hình bảo mật.

Tạo `.env` từ `.env.example` và đặt `DATABASE_URL` trỏ tới DB local, ví dụ
`postgresql://USER:PASSWORD@localhost:5436/WifiMon_db`. URL-encode ký tự đặc
biệt trong username/password. Có thể khởi động riêng database bằng
`python scripts/start_postgres.py`.

## 10. Cấu hình chính

Các khóa ứng dụng trong `wifimon/config.yaml`:

| Khóa | Mặc định | Tác dụng |
| --- | --- | --- |
| `scan_interval` | `10` | Số giây nghỉ giữa hai lượt quét |
| `client_threshold` | `5` | Cảnh báo một lần khi số station connected vừa vượt ngưỡng |
| `disconnect_missed_scans` | `2` | Số lượt quét AP liên tiếp không thấy client trước khi đánh dấu mất kết nối |
| `ap_interface` | `wlan0` | Interface AP được truy vấn bằng `iw` |
| `lease_file` | `/var/lib/misc/dnsmasq.leases` | Đường dẫn file DHCP lease trên máy remote |
| `bridge` | `br-lab` | Bridge được truy vấn và gắn nhãn SSID |
| `client_prefix` | `client` | Chỉ xử lý namespace có tên bắt đầu bằng prefix |
| `ssid_map` | `{}` | Ánh xạ tên bridge sang SSID hiển thị |

Thông tin SSH được nạp từ `.env`, không lưu trong YAML.

## 11. Kịch bản demo gợi ý

1. **Giới thiệu topology:** trình bày máy chạy WifiMon, máy Ubuntu, bridge,
   dnsmasq và hai radio ảo (nếu dùng mô phỏng).
2. **Kiểm tra hạ tầng:** chạy `python -m app.main`, giải thích kết quả bridge,
   forwarding, dnsmasq và namespace.
3. **Khởi chạy dịch vụ:** từ `dashboard`, chạy `python manage.py start_all`.
4. **Quan sát dashboard:** mở `http://127.0.0.1:8000/`, xem số lượng client,
   trạng thái, lần quét cuối và sự kiện.
5. **Tạo biến động có kiểm soát:** kết nối client lab hoặc dừng client để quan
   sát dữ liệu thay đổi ở các lượt quét. Chỉ demo trong mạng thử nghiệm.
6. **Xem API:** mở `/api/stats/`, `/api/clients/` hoặc `/api/events/` để minh
   họa khả năng lấy dữ liệu JSON.
7. **Kết thúc:** nhấn `Ctrl+C`, giải thích PostgreSQL giữ lại lịch sử đã ghi
   trong Docker volume.

Không tạo sự kiện giả trên mạng thật để minh họa. Nên chuẩn bị sẵn Ubuntu lab,
kiểm tra SSH và lease DHCP trước buổi trình bày.

## 12. Dàn ý PowerPoint đề xuất

### Slide 1 — Tiêu đề

- WifiMon — Hệ thống giám sát client Wi-Fi.
- Tên thành viên/nhóm, môn học, giảng viên, ngày trình bày.
- Hình gợi ý: dashboard hoặc sơ đồ topology.

### Slide 2 — Bối cảnh và vấn đề

- Thông tin client nằm ở nhiều nguồn trên router Linux.
- Khó quan sát thay đổi và tra cứu lịch sử bằng cách kiểm tra thủ công.
- Cần tập trung hóa trạng thái và cảnh báo.

### Slide 3 — Mục tiêu và phạm vi

- Thu thập, hợp nhất, phát hiện sự kiện, lưu lịch sử, hiển thị.
- Nêu rõ không tự quản trị AP, không chặn client, không thay router.

### Slide 4 — Công nghệ

- Python, Paramiko, PostgreSQL/Docker, Django, Rich, PyYAML, dotenv.
- Ubuntu/Linux: `iproute2`, dnsmasq; `hostapd`, `iw`, `mac80211_hwsim` cho lab.

### Slide 5 — Kiến trúc

- Dùng sơ đồ trong mục **Kiến trúc tổng quan**.
- Giải thích ranh giới giữa máy Ubuntu được giám sát và máy chạy ứng dụng.

### Slide 6 — Luồng xử lý

- SSH → thu thập nhiều nguồn → chuẩn hóa/gộp theo MAC → detector → PostgreSQL →
  dashboard/cảnh báo.
- Có thể chuyển thành sơ đồ pipeline ngang.

### Slide 7 — Nguồn dữ liệu và sự kiện

- Station list AP là nguồn xác nhận trạng thái; DHCP lease, neighbor/ARP,
  namespace và bridge FDB bổ sung thông tin.
- Sự kiện: connected, disconnected (sau nhiều lần vắng), returned,
  threshold exceeded và threshold recovered.
- `connected_since` là thời gian ước tính từ AP; `first_seen` là lần đầu WifiMon
  thấy client.
- Nêu MAC là khóa nhận diện chính.

### Slide 8 — Cơ sở dữ liệu

- Ba bảng: `clients`, `events`, `scan_history`.
- Nêu một vài trường tiêu biểu và cách dashboard Django cùng đọc PostgreSQL.

### Slide 9 — Giao diện và API

- Ảnh chụp dashboard tổng quan, danh sách client, lịch sử sự kiện.
- Nêu bốn API JSON và ví dụ endpoint thống kê.

### Slide 10 — Mô phỏng AP và demo

- `mac80211_hwsim` tạo radio ảo; `hostapd` phát AP; dnsmasq cấp IP.
- Trình bày topology và demo theo kịch bản ở mục 11.

### Slide 11 — Kết quả, giới hạn và bảo mật

- Kết quả: luồng giám sát đầu-cuối và dữ liệu lịch sử tập trung.
- Giới hạn: phụ thuộc quyền đọc AP/SSH; dashboard chưa có xác thực; cảnh báo
  hiện in console.
- Dùng trong lab được quản lý, bảo vệ SSH và không công khai development server.

### Slide 12 — Hướng phát triển và kết luận

- Thêm xác thực dashboard, phân quyền, TLS và triển khai production.
- Bổ sung kiểm thử trên nhiều driver/AP và cơ chế quản lý nhiều AP.
- Kết luận: WifiMon giúp tập trung hóa quan sát client và lịch sử cho môi trường
  Wi-Fi lab.

## 13. Giới hạn và điểm cần lưu ý khi thuyết trình

- **Không đồng nhất client với thiết bị vật lý:** MAC có thể bị ngẫu nhiên hóa
  hoặc thay đổi; MAC là định danh quan sát được, không phải danh tính người dùng.
- **Dữ liệu phụ thuộc quyền và cấu hình remote:** thiếu quyền đọc lease, namespace
  hoặc bridge có thể khiến một số nguồn không cung cấp dữ liệu.
- **Nguồn AP cần cấu hình đúng:** `ap_interface` phải trỏ tới interface AP;
  tài khoản SSH phải được phép chạy `iw ... station dump`.
- **Thời gian kết nối là ước tính:** WifiMon trừ `connected time` từ thời điểm
  đọc; không phải timestamp lịch sử do AP cung cấp. `first_seen` là lúc chương
  trình thấy client lần đầu.
- **Có grace period:** client chỉ bị đánh dấu mất sau số lần quét AP vắng liên
  tiếp cấu hình, mặc định 2; điều này giảm báo nhầm nhưng tạo độ trễ phát hiện.
- **Lượt đọc AP lỗi bị bỏ qua:** dashboard giữ trạng thái gần nhất, không phát
  disconnect/threshold hoặc ghi scan history từ snapshot không đáng tin cậy.
- **SSID nguồn dự phòng:** WifiMon ưu tiên SSID từ `iw`, nếu không đọc được thì
  dùng ánh xạ cấu hình.
- **SSH host key và sudo:** collector yêu cầu host key đã tin cậy và gửi mật
  khẩu sudo qua stdin. Vẫn nên dùng quyền sudo giới hạn và bảo vệ tài khoản.
- **Dashboard phát triển:** cấu hình Django hiện bật `DEBUG`, cho phép mọi host
  và dùng khóa bí mật mẫu. Không triển khai công khai hoặc trên mạng không tin
  cậy nếu chưa cấu hình lại.
- **Dữ liệu lưu lâu dài:** PostgreSQL chạy bằng Docker Compose, volume tên
  `wifimon-postgres-data`; dữ liệu SQLite cũ (nếu có) không được import hoặc
  xóa tự động.
- **Mạng AP mô phỏng:** cấu hình lab mẫu là mạng mở, không có NAT/Internet. Chỉ
  dùng trong môi trường thử nghiệm cô lập.

## 14. Cấu trúc repository

```text
app/
  main.py                  Điểm vào tiện ích kiểm tra router
  check_state.py           Truy vấn trạng thái Linux qua SSH
dashboard/
  manage.py                Điểm vào Django
  dashboard/               Cấu hình và URL Django
  monitor/
    models.py              Model đọc các bảng PostgreSQL do WifiMon tạo
    views.py               Trang dashboard và JSON API
    templates/             HTML của dashboard
    static/                CSS và JavaScript
    management/commands/
      start_all.py         Chạy kiểm tra, WifiMon và Django cùng nhau
wifimon/
  main.py                  Vòng lặp giám sát
  config.py, config.yaml   Nạp cấu hình
  collector.py             Thu thập dữ liệu qua SSH
  detector.py              Phát hiện thay đổi và sự kiện
  storage.py               PostgreSQL
  alerts.py, cli.py        Cảnh báo và Rich CLI dự phòng
docker-compose.yml         PostgreSQL local với Docker Compose
scripts/start_postgres.py  Khởi động DB theo DATABASE_URL
README.md                  Hướng dẫn cài đặt và dựng Ubuntu lab
PROJECT_PRESENTATION.md    Tài liệu dự án và dàn ý thuyết trình này
requirements.txt           Thư viện Python
```

## 15. Tóm tắt thuyết trình mẫu

> WifiMon là hệ thống giám sát client Wi-Fi dành cho môi trường Ubuntu/Linux
> lab. Ứng dụng kết nối SSH tới router/server và lấy danh sách association trực
> tiếp từ AP bằng `iw`; DHCP lease, neighbor, namespace và bridge FDB bổ sung
> IP, hostname và thông tin phụ. Hệ thống phát hiện client mới, mất kết nối sau
> nhiều lượt vắng liên tiếp, quay lại và vượt ngưỡng chỉ một lần khi có chuyển
> trạng thái. Thời điểm kết nối được ước tính từ thời lượng association do AP
> báo cáo, còn `first_seen` thể hiện lần đầu WifiMon phát hiện. Dữ liệu lưu
> trong PostgreSQL chạy bằng Docker, hiển thị trên Django và JSON API; Rich CLI
> là giao diện dự phòng. Mạng lab có thể mô
> phỏng bằng `mac80211_hwsim`, `hostapd` và `dnsmasq`; dashboard production,
> nhiều AP và kiểm thử đa dạng thiết bị là các hướng phát triển.
