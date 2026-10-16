"""
storage.py - Lưu trữ dữ liệu giám sát Wi-Fi bằng PostgreSQL

Quản lý 3 bảng:
  - clients:      thông tin client hiện tại
  - events:       lịch sử sự kiện / cảnh báo
  - scan_history: lịch sử quét (thống kê tổng hợp)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

if TYPE_CHECKING:
    from wifimon.collector import ClientInfo


def _now_iso() -> str:
    """Trả về thời gian hiện tại dạng ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _psycopg_database_url(database_url: str) -> str:
    """Normalize URL options and localhost for psycopg/Docker loopback."""
    parsed = urlsplit(database_url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    schemas = [value for key, value in query if key == "schema"]
    if any(schema != "public" for schema in schemas):
        raise ValueError(
            "DATABASE_URL schema must be public; configure other schemas with "
            "a PostgreSQL search_path option."
        )
    query = [(key, value) for key, value in query if key != "schema"]
    hostname = parsed.hostname or ""
    if hostname == "localhost":
        userinfo = parsed.netloc.rpartition("@")[0]
        userinfo = f"{userinfo}@" if userinfo else ""
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{userinfo}127.0.0.1{port}"
    else:
        netloc = parsed.netloc
    return urlunsplit(parsed._replace(netloc=netloc, query=urlencode(query)))


class Storage:
    """Quản lý PostgreSQL database cho hệ thống giám sát Wi-Fi."""

    def __init__(self, database_url: str | None = None) -> None:
        load_dotenv(Path(__file__).parent.parent / ".env")
        self.database_url = database_url or os.environ.get("DATABASE_URL", "")
        if not self.database_url:
            raise ValueError("Thiếu DATABASE_URL trong cấu hình.")
        self.conn = psycopg.connect(
            _psycopg_database_url(self.database_url),
            row_factory=dict_row,
        )
        self.init_db()

    # ------------------------------------------------------------------ #
    #  Khởi tạo bảng                                                     #
    # ------------------------------------------------------------------ #

    def init_db(self) -> None:
        """Tạo các bảng PostgreSQL nếu chưa tồn tại và cập nhật schema."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                mac       TEXT PRIMARY KEY,
                ip        TEXT DEFAULT '',
                hostname  TEXT DEFAULT '',
                ssid      TEXT DEFAULT '',
                namespace TEXT DEFAULT '',
                connected_since TEXT DEFAULT '',
                first_seen TEXT DEFAULT '',
                last_seen  TEXT DEFAULT '',
                state     TEXT DEFAULT 'connected',
                source    TEXT DEFAULT '',
                missed_scans INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id         BIGSERIAL PRIMARY KEY,
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
                id                BIGSERIAL PRIMARY KEY,
                timestamp         TEXT NOT NULL,
                total_clients     INTEGER DEFAULT 0,
                connected_clients INTEGER DEFAULT 0
            )
            """
        )

        cursor.execute(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS connected_since TEXT DEFAULT ''"
        )
        cursor.execute(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS source TEXT DEFAULT ''"
        )
        cursor.execute(
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS "
            "missed_scans INTEGER NOT NULL DEFAULT 0"
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
            INSERT INTO clients (
                mac, ip, hostname, ssid, namespace, connected_since,
                first_seen, last_seen, state, source, missed_scans
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            ON CONFLICT(mac) DO UPDATE SET
                ip = CASE WHEN excluded.ip != '' THEN excluded.ip ELSE clients.ip END,
                hostname = CASE
                    WHEN excluded.hostname != '' THEN excluded.hostname
                    ELSE clients.hostname
                END,
                ssid = CASE WHEN excluded.ssid != '' THEN excluded.ssid ELSE clients.ssid END,
                namespace = CASE
                    WHEN excluded.namespace != '' THEN excluded.namespace
                    ELSE clients.namespace
                END,
                connected_since = CASE
                    WHEN excluded.connected_since != '' THEN excluded.connected_since
                    ELSE clients.connected_since
                END,
                last_seen = excluded.last_seen,
                state     = excluded.state,
                source    = excluded.source,
                missed_scans = 0
            """,
            (
                client.mac,
                client.ip,
                client.hostname,
                client.ssid,
                client.namespace,
                client.connected_since,
                first_seen,
                client.last_seen or _now_iso(),
                client.state,
                client.source,
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
        cursor.execute("SELECT * FROM clients WHERE mac = %s", (mac,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_connected_clients(self) -> list[dict]:
        """Lấy danh sách client đang kết nối."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM clients WHERE state = 'connected' ORDER BY last_seen DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def record_missed_scan(self, mac: str, disconnect_after: int) -> bool:
        """Record one authoritative AP scan miss and return whether it disconnected."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT state, missed_scans FROM clients WHERE mac = %s", (mac,)
        )
        row = cursor.fetchone()
        if row is None:
            return False

        missed_scans = row["missed_scans"] + 1
        disconnected = missed_scans >= disconnect_after
        state = "disconnected" if disconnected else "stale"
        cursor.execute(
            "UPDATE clients SET state = %s, missed_scans = %s WHERE mac = %s",
            (state, missed_scans, mac),
        )
        self.conn.commit()
        return disconnected and row["state"] != "disconnected"

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
            VALUES (%s, %s, %s, %s, %s)
            """,
            (_now_iso(), event_type, mac, message, severity),
        )
        self.conn.commit()

    def get_events(self, limit: int = 50) -> list[dict]:
        """Lấy danh sách sự kiện gần nhất."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT %s", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_events_by_mac(self, mac: str, limit: int = 50) -> list[dict]:
        """Lấy danh sách sự kiện của một client."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM events WHERE mac = %s ORDER BY id DESC LIMIT %s",
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
            VALUES (%s, %s, %s)
            """,
            (_now_iso(), total, connected),
        )
        self.conn.commit()

    def get_scan_history(self, limit: int = 100) -> list[dict]:
        """Lấy lịch sử quét gần nhất."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM scan_history ORDER BY id DESC LIMIT %s", (limit,)
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
        """Đóng kết nối PostgreSQL."""
        self.conn.close()
