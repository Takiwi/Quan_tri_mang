"""
alerts.py - Quản lý cảnh báo / thông báo sự kiện

Hiện tại chỉ in cảnh báo ra console bằng thư viện Rich.
Trong tương lai có thể mở rộng gửi email / Telegram.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from wifimon.detector import Event


# Bảng màu theo mức độ nghiêm trọng
_SEVERITY_STYLES = {
    "info": "bold green",
    "warning": "bold yellow",
    "critical": "bold red",
}

# Biểu tượng theo loại sự kiện
_EVENT_ICONS = {
    "client_connected": "🟢",
    "client_disconnected": "🔴",
    "client_returned": "🔵",
    "threshold_exceeded": "⚠️",
    "threshold_recovered": "✅",
}


class AlertManager:
    """
    Quản lý việc gửi cảnh báo khi có sự kiện mạng.

    Hiện tại chỉ hiển thị trên console. Có thể mở rộng thêm
    các kênh thông báo khác (email, Telegram, webhook, ...).
    """

    def __init__(self) -> None:
        self.console = Console()

    def send(self, event: "Event") -> None:
        """
        Gửi cảnh báo ra console với màu sắc theo mức độ nghiêm trọng.

        Args:
            event: Đối tượng Event chứa thông tin sự kiện cần cảnh báo.
        """
        style = _SEVERITY_STYLES.get(event.severity, "bold white")
        icon = _EVENT_ICONS.get(event.event_type, "ℹ️")

        # Xây dựng nội dung cảnh báo
        header = f"{icon}  [{style}][{event.severity.upper()}][/{style}]"
        detail = (
            f" {event.message}  "
            f"(MAC={event.mac}, IP={event.ip}, Host={event.hostname})"
        )
        timestamp_str = f"  ⏰ {event.timestamp}"

        self.console.print(header + detail + timestamp_str)
