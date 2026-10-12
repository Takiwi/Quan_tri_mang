"""
detector.py - So sánh kết quả quét hiện tại với DB, sinh sự kiện

Phát hiện 4 loại sự kiện:
  - client_connected:     client mới kết nối
  - client_disconnected:  client mất kết nối
  - client_returned:      client quay lại sau khi mất kết nối
  - threshold_exceeded:   số client vượt ngưỡng cấu hình
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wifimon.collector import ClientInfo
    from wifimon.storage import Storage


def _now_iso() -> str:
    """Trả về thời gian hiện tại dạng ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Event:
    """Mô tả một sự kiện giám sát mạng."""

    event_type: str     # 'client_connected', 'client_disconnected', ...
    mac: str            # MAC address liên quan
    ip: str             # IP address
    hostname: str       # Hostname
    message: str        # Mô tả sự kiện
    timestamp: str      # Thời gian xảy ra (ISO 8601)
    severity: str       # 'info', 'warning', 'critical'


class Detector:
    """
    So sánh danh sách client hiện tại với dữ liệu trong DB
    để phát hiện các thay đổi và sinh sự kiện.
    """

    def __init__(self, storage: "Storage", config: dict) -> None:
        self.storage = storage
        self.threshold = config.get("client_threshold", 5)

    def detect(self, current_clients: list["ClientInfo"]) -> list[Event]:
        """
        So sánh trạng thái hiện tại với DB. Trả về danh sách sự kiện.

        Quy trình:
          1. Lấy danh sách client đã biết từ DB.
          2. Phát hiện client mới / quay lại.
          3. Phát hiện client mất kết nối.
          4. Kiểm tra ngưỡng.
          5. Cập nhật DB.
        """
        events: list[Event] = []
        now = _now_iso()

        # Lấy trạng thái cũ từ DB
        old_clients = {c["mac"]: c for c in self.storage.get_all_clients()}

        # MAC hiện tại đang kết nối
        current_macs = set()
        connected_count = 0

        for client in current_clients:
            current_macs.add(client.mac)

            if client.state == "connected":
                connected_count += 1

            old = old_clients.get(client.mac)

            if old is None:
                # ---- Client mới hoàn toàn ----
                events.append(
                    Event(
                        event_type="client_connected",
                        mac=client.mac,
                        ip=client.ip,
                        hostname=client.hostname,
                        message=f"Client mới kết nối: {client.hostname or client.mac} ({client.ip})",
                        timestamp=now,
                        severity="info",
                    )
                )
            elif old["state"] == "disconnected" and client.state == "connected":
                # ---- Client quay lại ----
                events.append(
                    Event(
                        event_type="client_returned",
                        mac=client.mac,
                        ip=client.ip,
                        hostname=client.hostname,
                        message=f"Client quay lại: {client.hostname or client.mac} ({client.ip})",
                        timestamp=now,
                        severity="info",
                    )
                )

            # Cập nhật DB với thông tin mới nhất
            self.storage.upsert_client(client)

        # ---- Phát hiện client mất kết nối ----
        for mac, old in old_clients.items():
            if mac not in current_macs and old["state"] != "disconnected":
                # Client không còn trong lần quét này -> mất kết nối
                self.storage.mark_disconnected(mac, now)
                events.append(
                    Event(
                        event_type="client_disconnected",
                        mac=mac,
                        ip=old.get("ip", ""),
                        hostname=old.get("hostname", ""),
                        message=f"Client mất kết nối: {old.get('hostname') or mac} ({old.get('ip', '')})",
                        timestamp=now,
                        severity="warning",
                    )
                )

        # ---- Kiểm tra ngưỡng ----
        if connected_count > self.threshold:
            events.append(
                Event(
                    event_type="threshold_exceeded",
                    mac="",
                    ip="",
                    hostname="",
                    message=(
                        f"Số client kết nối ({connected_count}) "
                        f"vượt ngưỡng ({self.threshold})"
                    ),
                    timestamp=now,
                    severity="critical",
                )
            )

        # Lưu sự kiện vào DB
        for event in events:
            self.storage.add_event(
                event_type=event.event_type,
                mac=event.mac,
                message=event.message,
                severity=event.severity,
            )

        # Ghi lịch sử quét
        total = len(current_clients)
        self.storage.add_scan_record(total=total, connected=connected_count)

        return events

