"""
main.py - Vòng lặp quét chính của hệ thống giám sát Wi-Fi

Quy trình:
  1. Tải cấu hình từ config.yaml và .env
  2. Thiết lập kết nối SSH tới Ubuntu Server
  3. Khởi tạo PostgreSQL storage
  4. Bắt đầu vòng lặp quét:
     a. Thu thập client (collector)
     b. Phát hiện sự kiện (detector)
     c. Gửi cảnh báo (alerts)
     d. Cập nhật dashboard Rich (cli)
  5. Nhấn Ctrl+C để dừng
"""

from __future__ import annotations

import sys
import argparse
import time
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from wifimon.alerts import AlertManager
from wifimon.collector import RemoteCollector, create_ssh_connection
from wifimon.config import load_config
from wifimon.detector import Detector
from wifimon.storage import Storage

if TYPE_CHECKING:
    from wifimon.cli import Dashboard
    from rich.live import Live as RichLive

try:
    from rich.live import Live
except ImportError:
    Live = None  # type: ignore[assignment,misc]


def main() -> None:
    """Điểm vào chính - chạy vòng lặp giám sát."""
    parser = argparse.ArgumentParser(description="WifiMon Wi-Fi client monitor")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Hiển thị dashboard Rich trong terminal thay cho dashboard Django.",
    )
    args = parser.parse_args()

    # Đảm bảo console hỗ trợ UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Tải biến môi trường
    load_dotenv()

    # Tải cấu hình
    config = load_config()
    scan_interval = config.get("scan_interval", 10)

    print("🚀 Khởi động WifiMon - Giám sát Client Wi-Fi")
    print(f"   SSH: {config['ssh']['user']}@{config['ssh']['host']}:{config['ssh']['port']}")
    print(f"   Chu kỳ quét: {scan_interval}s | Ngưỡng: {config.get('client_threshold', 5)} client")
    print()

    # Thiết lập kết nối SSH
    print("🔗 Đang kết nối SSH tới server...")
    try:
        ssh_client = create_ssh_connection(config)
    except Exception as exc:
        print(f"❌ Không thể kết nối SSH: {exc}")
        sys.exit(1)
    print("✅ Kết nối SSH thành công!")

    # Khởi tạo các thành phần
    storage = Storage()
    collector = RemoteCollector(ssh_client, config)
    detector = Detector(storage, config)
    alert_mgr = AlertManager()
    if args.cli:
        from wifimon.cli import Dashboard

        dashboard = Dashboard(storage)
    else:
        dashboard = None

    mode = "CLI dự phòng" if args.cli else "dashboard Django"
    print(f"📡 Bắt đầu giám sát ({mode})... (Ctrl+C để dừng)\n")

    try:
        if args.cli and Live is not None and dashboard is not None:
            # Chế độ dashboard real-time với Rich Live
            with Live(
                dashboard.render_all(),
                refresh_per_second=1,
                screen=False,
            ) as live:
                while True:
                    _scan_cycle(collector, detector, alert_mgr, dashboard, live)
                    time.sleep(scan_interval)
        else:
            # Default headless mode leaves the web UI as the primary dashboard.
            while True:
                _scan_cycle_simple(
                    collector, detector, alert_mgr, storage, dashboard
                )
                time.sleep(scan_interval)

    except KeyboardInterrupt:
        print("\n\n🛑 Đã dừng giám sát.")
    finally:
        ssh_client.close()
        storage.close()
        print("👋 Đã đóng kết nối. Tạm biệt!")


def _scan_cycle(
    collector: RemoteCollector,
    detector: Detector,
    alert_mgr: AlertManager,
    dashboard: "Dashboard",
    live: "RichLive",
) -> None:
    """Thực hiện một chu kỳ quét với Rich Live dashboard."""
    try:
        # Thu thập client
        result = collector.collect_all()
        for error in result.errors:
            alert_mgr.console.print(f"[yellow]⚠ Thu thập chưa đầy đủ: {error}[/yellow]")
        if not result.station_scan_ok:
            alert_mgr.console.print(
                "[yellow]Bỏ qua lượt quét: không xác nhận được danh sách station từ AP; "
                "giữ nguyên trạng thái đã lưu.[/yellow]"
            )
            return

        # Phát hiện sự kiện
        events = detector.detect(result.clients)

        # Gửi cảnh báo cho các sự kiện
        for event in events:
            alert_mgr.send(event)

        # Cập nhật dashboard
        live.update(dashboard.render_all())

    except Exception as exc:
        # Không crash vòng lặp khi gặp lỗi
        alert_mgr.console.print(f"[bold red]⚠ Lỗi khi quét: {exc}[/bold red]")


def _scan_cycle_simple(
    collector: RemoteCollector,
    detector: Detector,
    alert_mgr: AlertManager,
    storage: Storage,
    dashboard: "Dashboard | None" = None,
) -> None:
    """Thực hiện một chu kỳ quét (fallback không dùng Rich Live)."""
    try:
        result = collector.collect_all()
        for error in result.errors:
            print(f"⚠ Thu thập chưa đầy đủ: {error}")
        if not result.station_scan_ok:
            print(
                "[Bỏ qua] Không xác nhận được danh sách station từ AP; "
                "giữ nguyên trạng thái đã lưu."
            )
            return

        events = detector.detect(result.clients)

        for event in events:
            alert_mgr.send(event)

        if dashboard is not None:
            dashboard.console.print(dashboard.render_all())
            return

        # Log summary for the default headless web-dashboard mode.
        all_clients = storage.get_all_clients()
        connected = sum(1 for c in all_clients if c["state"] == "connected")
        print(
            f"[Quét] Tổng: {len(all_clients)} | "
            f"Kết nối: {connected} | "
            f"Sự kiện: {len(events)}"
        )

    except Exception as exc:
        print(f"⚠ Lỗi khi quét: {exc}")


if __name__ == "__main__":
    main()
