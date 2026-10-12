"""
storage.py - Lưu trữ dữ liệu giám sát Wi-Fi bằng SQLite

Quản lý 3 bảng:
  - clients:      thông tin client hiện tại
  - events:       lịch sử sự kiện / cảnh báo
  - scan_history: lịch sử quét (thống kê tổng hợp)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wifimon.collector import ClientInfo


def _now_iso() -> str:
    """Trả về thời gian hiện tại dạng ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    """Quản lý SQLite database cho hệ thống giám sát Wi-Fi."""

    def __init__(self, db_path: str = "wifimon.db") -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    # ------------------------------------------------------------------ #
    #  Khởi tạo bảng                                                     #
    # ------------------------------------------------------------------ #

    def init_db(self) -> None:
        """Tạo các bảng nếu chưa tồn tại."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                mac       TEXT PRIMARY KEY,
                ip        TEXT DEFAULT '',
                hostname  TEXT DEFAULT '',
                ssid      TEXT DEFAULT '',
                namespace TEXT DEFAULT '',
                first_seen TEXT DEFAULT '',
                last_seen  TEXT DEFAULT '',
                state     TEXT DEFAULT 'connected'
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  TEXT NOT NULL,
                event_type TEXT NOT NULL,
                mac        TEXT DEFAULT '',
                message    TEXT DEFAULT '',
                severity   TEXT DEFAULT 'info'
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_history (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp         TEXT NOT NULL,
                total_clients     INTEGER DEFAULT 0,
                connected_clients INTEGER DEFAULT 0
            )
            """
        )

        self.conn.commit()

    # ------------------------------------------------------------------ #
    #  CRUD cho clients                                                   #
    # ------------------------------------------------------------------ #

    def upsert_client(self, client: "ClientInfo") -> None:
        """
        Chèn hoặc cập nhật thông tin client.

        - Nếu client mới: dùng first_seen = last_seen = thời gian hiện tại.
        - Nếu client đã có: giữ nguyên first_seen, cập nhật last_seen.
        """
        cursor = self.conn.cursor()

        # Kiểm tra client đã tồn tại chưa
        existing = self.get_client_by_mac(client.mac)
        if existing:
            # Giữ first_seen cũ
            first_seen = existing["first_seen"]
        else:
            first_seen = client.first_seen or _now_iso()

        cursor.execute(
            """
            INSERT INTO clients (mac, ip, hostname, ssid, namespace, first_seen, last_seen, state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                ip        = excluded.ip,
                hostname  = excluded.hostname,
                ssid      = excluded.ssid,
                namespace = excluded.namespace,
                last_seen = excluded.last_seen,
                state     = excluded.state
            """,
            (
                client.mac,
                client.ip,
                client.hostname,
                client.ssid,
                client.namespace,
                first_seen,
                client.last_seen or _now_iso(),
                client.state,
            ),
        )
        self.conn.commit()

    def get_all_clients(self) -> list[dict]:
        """Lấy danh sách tất cả client."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM clients ORDER BY last_seen DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_client_by_mac(self, mac: str) -> dict | None:
        """Lấy thông tin một client theo MAC address."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM clients WHERE mac = ?", (mac,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_connected_clients(self) -> list[dict]:
        """Lấy danh sách client đang kết nối."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM clients WHERE state = 'connected' ORDER BY last_seen DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def mark_disconnected(self, mac: str, timestamp: str = "") -> None:
        """Đánh dấu client đã mất kết nối."""
        ts = timestamp or _now_iso()
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE clients SET state = 'disconnected', last_seen = ? WHERE mac = ?",
            (ts, mac),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ #
    #  CRUD cho events                                                    #
    # ------------------------------------------------------------------ #

    def add_event(
        self,
        event_type: str,
        mac: str = "",
        message: str = "",
        severity: str = "info",
    ) -> None:
        """Thêm một sự kiện mới vào lịch sử."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO events (timestamp, event_type, mac, message, severity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_now_iso(), event_type, mac, message, severity),
        )
        self.conn.commit()

    def get_events(self, limit: int = 50) -> list[dict]:
        """Lấy danh sách sự kiện gần nhất."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_events_by_mac(self, mac: str, limit: int = 50) -> list[dict]:
        """Lấy danh sách sự kiện của một client."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM events WHERE mac = ? ORDER BY id DESC LIMIT ?",
            (mac, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    #  CRUD cho scan_history                                              #
    # ------------------------------------------------------------------ #

    def add_scan_record(self, total: int, connected: int) -> None:
        """Thêm bản ghi lịch sử quét."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO scan_history (timestamp, total_clients, connected_clients)
            VALUES (?, ?, ?)
            """,
            (_now_iso(), total, connected),
        )
        self.conn.commit()

    def get_scan_history(self, limit: int = 100) -> list[dict]:
        """Lấy lịch sử quét gần nhất."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM scan_history ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    #  Xuất dữ liệu cho Django / API                                     #
    # ------------------------------------------------------------------ #

    def export_json(self) -> dict:
        """
        Xuất toàn bộ dữ liệu dưới dạng dict (JSON-serializable)
        để Django views có thể sử dụng.
        """
        clients = self.get_all_clients()
        connected = [c for c in clients if c["state"] == "connected"]
        disconnected = [c for c in clients if c["state"] == "disconnected"]

        return {
            "clients": clients,
            "events": self.get_events(limit=100),
            "scan_history": self.get_scan_history(limit=100),
            "stats": {
                "total_clients": len(clients),
                "connected_clients": len(connected),
                "disconnected_clients": len(disconnected),
                "last_scan": (
                    self.get_scan_history(limit=1)[0]["timestamp"]
                    if self.get_scan_history(limit=1)
                    else ""
                ),
            },
        }

    # ------------------------------------------------------------------ #
    #  Đóng kết nối                                                       #
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Đóng kết nối SQLite."""
        self.conn.close()

