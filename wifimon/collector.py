"""
collector.py - Thu thập thông tin client từ Ubuntu Server qua SSH

Kết hợp nhiều nguồn dữ liệu:
  - DHCP lease file (dnsmasq)
  - ARP / ip neigh
  - Network namespace
  - Bridge FDB
để tạo danh sách ClientInfo thống nhất.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import paramiko


@dataclass
class ClientInfo:
    """Thông tin một client Wi-Fi / mạng."""

    mac: str = ""  # Địa chỉ MAC (lowercase, dấu :)
    ip: str = ""  # Địa chỉ IP
    hostname: str = ""  # Tên máy từ DHCP lease
    ssid: str = ""  # SSID ánh xạ từ interface
    namespace: str = ""  # Network namespace (nếu có)
    first_seen: str = ""  # ISO datetime lần đầu phát hiện
    connected_since: str = ""  # Thời điểm association ước tính từ AP
    last_seen: str = ""  # ISO datetime lần quét hiện tại
    state: str = "connected"  # 'connected' | 'stale' | 'disconnected'
    source: str = ""  # Nguồn xác nhận trạng thái


@dataclass
class CollectionResult:
    """Snapshot client và trạng thái tin cậy của lần đọc danh sách AP."""

    clients: list[ClientInfo]
    station_scan_ok: bool
    errors: list[str] = field(default_factory=list)


def _normalize_mac(mac: str) -> str:
    """Chuẩn hóa MAC address về lowercase, dấu hai chấm."""
    mac = mac.strip().lower()
    # Loại bỏ ký tự phân cách rồi chèn lại dấu :
    raw = re.sub(r"[:\-\.]", "", mac)
    if len(raw) != 12:
        return mac
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


def _now_iso() -> str:
    """Trả về thời gian hiện tại dạng ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_station_dump(output: str, now: datetime | None = None) -> list[dict]:
    """Parse ``iw station dump``; connected_since là thời điểm suy ra gần đúng."""
    current_time = now or datetime.now(timezone.utc)
    stations: list[dict] = []
    current_station: dict | None = None

    for line in output.splitlines():
        station_match = re.match(r"\s*Station\s+([0-9a-fA-F:]{17})\b", line)
        if station_match:
            if current_station:
                stations.append(current_station)
            current_station = {
                "mac": _normalize_mac(station_match.group(1)),
                "connected_since": "",
            }
            continue

        if current_station:
            time_match = re.match(r"\s*connected time:\s+(\d+)\s+seconds\b", line)
            if time_match:
                connected_time = int(time_match.group(1))
                current_station["connected_since"] = (
                    current_time - timedelta(seconds=connected_time)
                ).isoformat(timespec="seconds")

    if current_station:
        stations.append(current_station)
    return stations


def create_ssh_connection(config: dict | None = None) -> paramiko.SSHClient:
    """
    Tạo kết nối SSH tới Ubuntu Server từ biến môi trường hoặc config dict.

    Biến môi trường cần thiết: SSH_HOST, SSH_PORT, SSH_USER, SSH_PASSWORD.
    """
    if config and "ssh" in config:
        ssh_cfg = config["ssh"]
    else:
        ssh_cfg = {
            "host": os.environ.get("SSH_HOST", ""),
            "port": int(os.environ.get("SSH_PORT", 22)),
            "user": os.environ.get("SSH_USER", ""),
            "password": os.environ.get("SSH_PASSWORD", ""),
        }

    host = ssh_cfg.get("host", "")
    port = int(ssh_cfg.get("port", 22))
    user = ssh_cfg.get("user", "")
    password = ssh_cfg.get("password", "")

    if not host or not user:
        raise ValueError("Thiếu SSH_HOST hoặc SSH_USER trong cấu hình.")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    client.connect(
        hostname=host,
        port=port,
        username=user,
        password=password or None,
        timeout=10,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


class RemoteCollector:
    """
    Thu thập thông tin client mạng từ Ubuntu Server qua SSH.

    Xác nhận association qua AP station list; dùng DHCP, ARP, namespace và
    bridge FDB để bổ sung thông tin client.
    """

    def __init__(self, ssh_client: paramiko.SSHClient, config: dict) -> None:
        self.ssh = ssh_client
        self.config = config
        self.password = config.get("ssh", {}).get("password", "") or os.environ.get(
            "SSH_PASSWORD", ""
        )
        self.lease_file = config.get("lease_file", "/var/lib/misc/dnsmasq.leases")
        self.bridge = config.get("bridge", "br-lab")
        self.ap_interface = config.get("ap_interface", "wlan0")
        self.prefix = config.get("client_prefix", "client")
        self.ssid_map: dict[str, str] = config.get("ssid_map", {})
        self.errors: list[str] = []

    # ------------------------------------------------------------------ #
    #  Thực thi lệnh trên remote                                         #
    # ------------------------------------------------------------------ #

    def run_cmd(
        self, cmd: str, timeout: int = 15, sudo: bool = False
    ) -> tuple[int, str, str]:
        """
        Chạy lệnh trên remote qua SSH.

        Nếu cần mật khẩu sudo, gửi qua stdin thay vì đưa vào command string.
        """
        if sudo and self.password:
            full_cmd = f"sudo -S -p '' -- sh -c {shlex.quote(cmd)}"
        elif sudo:
            full_cmd = f"sudo -n {cmd}"
        else:
            full_cmd = cmd

        stdin, stdout, stderr = self.ssh.exec_command(full_cmd, timeout=timeout)
        if sudo and self.password:
            stdin.write(f"{self.password}\n")
            stdin.flush()
            stdin.channel.shutdown_write()
        out = stdout.read().decode(errors="replace").strip()
        err = stderr.read().decode(errors="replace").strip()
        code = stdout.channel.recv_exit_status()
        return code, out, err

    def _run_collection_command(
        self, source: str, cmd: str, sudo: bool = False
    ) -> tuple[bool, str]:
        code, output, error = self.run_cmd(cmd, sudo=sudo)
        if code != 0:
            self.errors.append(f"{source}: {error or f'lệnh thoát mã {code}'}")
            return False, ""
        return True, output

    # ------------------------------------------------------------------ #
    #  Thu thập từ DHCP Lease                                             #
    # ------------------------------------------------------------------ #

    def collect_leases(self) -> list[dict]:
        """
        Đọc file lease của dnsmasq.

        Mỗi dòng có dạng: ``<timestamp> <mac> <ip> <hostname> <client-id>``
        """
        succeeded, out = self._run_collection_command(
            "DHCP lease", f"cat {shlex.quote(self.lease_file)}"
        )
        if not succeeded or not out:
            return []

        results: list[dict] = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            ts_epoch, mac, ip, hostname = parts[0], parts[1], parts[2], parts[3]

            # Chuyển epoch -> ISO
            try:
                lease_time = datetime.fromtimestamp(
                    int(ts_epoch), tz=timezone.utc
                ).isoformat(timespec="seconds")
            except (ValueError, OSError):
                lease_time = ""

            results.append(
                {
                    "mac": _normalize_mac(mac),
                    "ip": ip,
                    "hostname": hostname if hostname != "*" else "",
                    "lease_time": lease_time,
                    "source": "lease",
                }
            )
        return results

    # ------------------------------------------------------------------ #
    #  Thu thập từ ARP / ip neigh                                         #
    # ------------------------------------------------------------------ #

    def collect_arp(self) -> list[dict]:
        """
        Chạy ``ip neigh show`` để lấy bảng ARP/Neighbor.

        Trạng thái ARP: REACHABLE, STALE, DELAY, FAILED, ...
        """
        succeeded, out = self._run_collection_command(
            "Neighbor table", "ip neigh show"
        )
        if not succeeded or not out:
            return []

        results: list[dict] = []
        for line in out.splitlines():
            # Dạng: 192.168.1.10 dev br-lab lladdr aa:bb:cc:dd:ee:ff REACHABLE
            parts = line.split()
            if len(parts) < 5:
                continue

            ip = parts[0]
            mac = ""
            arp_state = parts[-1]  # Trạng thái cuối dòng

            # Tìm MAC sau từ khóa lladdr
            if "lladdr" in parts:
                idx = parts.index("lladdr")
                if idx + 1 < len(parts):
                    mac = _normalize_mac(parts[idx + 1])

            if not mac:
                continue

            # Ánh xạ trạng thái ARP -> trạng thái client
            if arp_state in ("REACHABLE", "DELAY", "PROBE"):
                state = "connected"
            elif arp_state == "STALE":
                state = "stale"
            else:
                state = "disconnected"

            results.append(
                {
                    "mac": mac,
                    "ip": ip,
                    "state": state,
                    "source": "arp",
                }
            )
        return results

    # ------------------------------------------------------------------ #
    #  Thu thập từ Network Namespace                                      #
    # ------------------------------------------------------------------ #

    def collect_namespaces(self) -> list[dict]:
        """
        Liệt kê namespace bắt đầu bằng prefix, rồi lấy thông tin IP
        của mỗi namespace bằng ``ip netns exec <ns> ip -br addr``.
        """
        succeeded, out = self._run_collection_command(
            "Network namespaces", "ip netns list"
        )
        if not succeeded or not out:
            return []

        namespaces = [
            line.split()[0]
            for line in out.splitlines()
            if line.strip() and line.split()[0].startswith(self.prefix)
        ]

        results: list[dict] = []
        for ns in namespaces:
            namespace_ok, ns_out = self._run_collection_command(
                f"Namespace {ns}",
                f"ip netns exec {shlex.quote(ns)} ip -br addr",
                sudo=True,
            )
            if not namespace_ok or not ns_out:
                continue

            for line in ns_out.splitlines():
                parts = line.split()
                if len(parts) < 3:
                    continue

                iface = parts[0]
                iface_state = parts[1]  # UP / DOWN
                addrs = parts[2:]  # Danh sách IP/prefix

                if iface == "lo":
                    continue

                ip = ""
                for addr in addrs:
                    # Lấy IPv4 (bỏ prefix length)
                    if "." in addr:
                        ip = addr.split("/")[0]
                        break

                # Lấy MAC từ namespace
                mac_ok, mac_out = self._run_collection_command(
                    f"Namespace {ns} MAC",
                    f"ip netns exec {shlex.quote(ns)} cat /sys/class/net/{shlex.quote(iface)}/address",
                    sudo=True,
                )
                mac = _normalize_mac(mac_out) if mac_ok and mac_out else ""

                state = "connected" if iface_state == "UP" else "disconnected"

                results.append(
                    {
                        "mac": mac,
                        "ip": ip,
                        "namespace": ns,
                        "state": state,
                        "source": "namespace",
                    }
                )
        return results

    # ------------------------------------------------------------------ #
    #  Thu thập từ Bridge FDB                                             #
    # ------------------------------------------------------------------ #

    def collect_fdb(self) -> list[dict]:
        """
        Chạy ``bridge fdb show br <bridge>`` để lấy các MAC đã học
        trên bridge.
        """
        succeeded, out = self._run_collection_command(
            "Bridge FDB",
            f"bridge fdb show br {shlex.quote(self.bridge)}",
            sudo=True,
        )
        if not succeeded or not out:
            return []

        results: list[dict] = []
        seen_macs: set[str] = set()
        for line in out.splitlines():
            # Dạng: aa:bb:cc:dd:ee:ff dev veth-client1 master br-lab
            parts = line.split()
            if not parts:
                continue

            mac = _normalize_mac(parts[0])
            # Bỏ qua MAC broadcast / multicast / permanent
            if mac.startswith("33:33:") or mac.startswith("01:00:5e"):
                continue
            if mac == "ff:ff:ff:ff:ff:ff":
                continue
            if "permanent" in line.lower() or "self" in line.lower():
                continue

            if mac not in seen_macs:
                seen_macs.add(mac)
                results.append(
                    {
                        "mac": mac,
                        "source": "fdb",
                    }
                )
        return results

    # ------------------------------------------------------------------ #
    #  Tổng hợp tất cả nguồn                                             #
    # ------------------------------------------------------------------ #

    def collect_all(self) -> CollectionResult:
        """Lấy station trực tiếp từ AP rồi làm giàu bằng lease và bảng Linux."""
        self.errors = []
        now = _now_iso()

        if not self.ap_interface:
            return CollectionResult(
                clients=[],
                station_scan_ok=False,
                errors=["AP station list: ap_interface chưa được cấu hình"],
            )

        station_ok, station_output = self._run_collection_command(
            "AP station list",
            f"iw dev {shlex.quote(self.ap_interface)} station dump",
            sudo=True,
        )
        if not station_ok:
            return CollectionResult([], False, self.errors.copy())

        interface_ok, interface_info = self._run_collection_command(
            "AP interface info",
            f"iw dev {shlex.quote(self.ap_interface)} info",
            sudo=True,
        )
        ssid_match = (
            re.search(r"^\s*ssid\s+(.+?)\s*$", interface_info, re.MULTILINE)
            if interface_ok
            else None
        )
        ssid = (
            ssid_match.group(1)
            if ssid_match
            else self.ssid_map.get(self.bridge, "")
        )

        leases = self.collect_leases()
        arps = self.collect_arp()
        namespaces = self.collect_namespaces()
        fdbs = self.collect_fdb()

        merged = {
            station["mac"]: {
                **station,
                "ip": "",
                "hostname": "",
                "namespace": "",
            }
            for station in _parse_station_dump(station_output)
        }

        for items in (leases, arps, namespaces, fdbs):
            for item in items:
                data = merged.get(item.get("mac", ""))
                if not data:
                    continue
                for key in ("ip", "hostname", "namespace"):
                    if item.get(key):
                        data[key] = item[key]

        clients = [
            ClientInfo(
                mac=mac,
                ip=data["ip"],
                hostname=data["hostname"],
                ssid=ssid,
                namespace=data["namespace"],
                first_seen=now,
                connected_since=data["connected_since"],
                last_seen=now,
                state="connected",
                source="ap_station",
            )
            for mac, data in merged.items()
        ]
        return CollectionResult(clients, True, self.errors.copy())
