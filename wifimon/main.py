"""
main.py - Vòng lặp quét chính của hệ thống giám sát Wi-Fi

Quy trình:
  1. Tải cấu hình từ config.yaml và .env
  2. Thiết lập kết nối SSH tới Ubuntu Server
  3. Khởi tạo SQLite storage
  4. Bắt đầu vòng lặp quét:
     a. Thu thập client (collector)
     b. Phát hiện sự kiện (detector)
     c. Gửi cảnh báo (alerts)
     d. Cập nhật dashboard Rich (cli)
  5. Nhấn Ctrl+C để dừng
"""

from __future__ import annotations

import sys
import time

from dotenv import load_dotenv

from wifimon.alerts import AlertManager
from wifimon.cli import Dashboard
from wifimon.collector import RemoteCollector, create_ssh_connection
from wifimon.config import load_config
from wifimon.detector import Detector
from wifimon.storage import Storage

try:
    from rich.live import Live
except ImportError:
    Live = None  # type: ignore[assignment,misc]


def main() -> None:
    """Điểm vào chính - chạy vòng lặp giám sát."""

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
    storage = Storage(db_path="wifimon.db")
    collector = RemoteCollector(ssh_client, config)
    detector = Detector(storage, config)
    alert_mgr = AlertManager()
    dashboard = Dashboard(storage)

    print("📡 Bắt đầu giám sát... (Ctrl+C để dừng)\n")

    try:
        if Live is not None:
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
            # Fallback: in text đơn giản
            while True:
                _scan_cycle_simple(collector, detector, alert_mgr, storage)
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
    dashboard: Dashboard,
    live: "Live",
) -> None:
    """Thực hiện một chu kỳ quét với Rich Live dashboard."""
    try:
        # Thu thập client
        clients = collector.collect_all()

        # Phát hiện sự kiện
        events = detector.detect(clients)

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
) -> None:
    """Thực hiện một chu kỳ quét (fallback không dùng Rich Live)."""
    try:
        clients = collector.collect_all()
        events = detector.detect(clients)

        for event in events:
            alert_mgr.send(event)

        # In tóm tắt
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

