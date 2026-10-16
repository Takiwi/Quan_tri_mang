"""
cli.py - Dashboard terminal real-time bằng thư viện Rich

Hiển thị:
  - Bảng thống kê tổng quan
  - Bảng danh sách client (MAC, IP, Hostname, SSID, Namespace, State, ...)
  - Bảng sự kiện gần đây
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from wifimon.storage import Storage


# Bảng màu theo trạng thái client
_STATE_COLORS = {
    "connected": "green",
    "stale": "yellow",
    "disconnected": "red",
}

# Bảng màu theo mức độ nghiêm trọng sự kiện
_SEVERITY_COLORS = {
    "info": "blue",
    "warning": "yellow",
    "critical": "red",
}


class Dashboard:
    """Dashboard real-time trên terminal, sử dụng Rich."""

    def __init__(self, storage: "Storage") -> None:
        self.storage = storage
        self.console = Console()

    # ------------------------------------------------------------------ #
    #  Bảng thống kê                                                     #
    # ------------------------------------------------------------------ #

    def render_stats(self) -> Panel:
        """Tạo panel thống kê tổng quan."""
        clients = self.storage.get_all_clients()
        connected = sum(1 for c in clients if c["state"] == "connected")
        stale = sum(1 for c in clients if c["state"] == "stale")
        disconnected = sum(1 for c in clients if c["state"] == "disconnected")

        history = self.storage.get_scan_history(limit=1)
        last_scan = history[0]["timestamp"] if history else "Chưa quét"

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold cyan")
        table.add_column("Value")

        table.add_row("Tổng client:", str(len(clients)))
        table.add_row("Đang kết nối:", Text(str(connected), style="bold green"))
        table.add_row("Đang xác minh mất:", Text(str(stale), style="bold yellow"))
        table.add_row("Mất kết nối:", Text(str(disconnected), style="bold red"))
        table.add_row("Lần quét cuối:", last_scan)

        return Panel(table, title="📊 Thống kê", border_style="cyan")

    # ------------------------------------------------------------------ #
    #  Bảng danh sách client                                              #
    # ------------------------------------------------------------------ #

    def render_clients(self) -> Panel:
        """Tạo bảng danh sách tất cả client."""
        clients = self.storage.get_all_clients()

        table = Table(
            title=None,
            show_lines=False,
            header_style="bold magenta",
            row_styles=["", "dim"],
        )

        table.add_column("#", style="dim", width=4)
        table.add_column("MAC Address", min_width=17)
        table.add_column("IP Address", min_width=15)
        table.add_column("Hostname", min_width=12)
        table.add_column("SSID", min_width=10)
        table.add_column("Namespace", min_width=10)
        table.add_column("Trạng thái", min_width=12)
        table.add_column("Kết nối AP từ", min_width=20)
        table.add_column("Phát hiện lần đầu", min_width=20)
        table.add_column("Cập nhật lần cuối", min_width=20)

        for idx, client in enumerate(clients, start=1):
            state = client.get("state", "unknown")
            color = _STATE_COLORS.get(state, "white")
            state_text = Text(state.upper(), style=f"bold {color}")

            table.add_row(
                str(idx),
                client.get("mac", ""),
                client.get("ip", ""),
                client.get("hostname", "") or "-",
                client.get("ssid", "") or "-",
                client.get("namespace", "") or "-",
                state_text,
                client.get("connected_since", "") or "-",
                client.get("first_seen", ""),
                client.get("last_seen", ""),
            )

        if not clients:
            table.add_row("-", "Chưa có client nào", "", "", "", "", "", "", "", "")

        return Panel(table, title="👥 Danh sách Client", border_style="blue")

    # ------------------------------------------------------------------ #
    #  Bảng sự kiện gần đây                                               #
    # ------------------------------------------------------------------ #

    def render_events(self, limit: int = 10) -> Panel:
        """Tạo bảng sự kiện gần nhất."""
        events = self.storage.get_events(limit=limit)

        table = Table(
            show_lines=False,
            header_style="bold yellow",
        )

        table.add_column("Thời gian", min_width=20)
        table.add_column("Loại sự kiện", min_width=20)
        table.add_column("MAC", min_width=17)
        table.add_column("Chi tiết", min_width=30)
        table.add_column("Mức độ", min_width=10)

        for event in events:
            severity = event.get("severity", "info")
            color = _SEVERITY_COLORS.get(severity, "white")
            severity_text = Text(severity.upper(), style=f"bold {color}")

            table.add_row(
                event.get("timestamp", ""),
                event.get("event_type", ""),
                event.get("mac", "") or "-",
                event.get("message", ""),
                severity_text,
            )

        if not events:
            table.add_row("Chưa có sự kiện nào", "", "", "", "")

        return Panel(table, title="🔔 Sự kiện gần đây", border_style="yellow")

    # ------------------------------------------------------------------ #
    #  Tổng hợp toàn bộ                                                   #
    # ------------------------------------------------------------------ #

    def render_all(self) -> Group:
        """Kết hợp tất cả panel thành một giao diện duy nhất."""
        return Group(
            Text(
                "═══ WIFIMON - Giám sát Client Wi-Fi ═══",
                style="bold white on blue",
                justify="center",
            ),
            Text(""),
            self.render_stats(),
            Text(""),
            self.render_clients(),
            Text(""),
            self.render_events(),
        )
