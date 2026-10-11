import os
import shlex

import paramiko

LEASE_FILE = "/var/lib/misc/dnsmasq.leases"


def read_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} phải có giá trị true/false.")


class Remote:
    def __init__(self):
        host = os.getenv("HOST", "").strip()
        user = os.getenv("SSH_USER", "").strip()
        raw_port = os.getenv("PORT", "22").strip()
        password = os.getenv("PASSWORD") or None
        key = os.getenv("KEY") or None

        missing = [
            name
            for name, value in (("HOST", host), ("SSH_USER", user))
            if not value
        ]
        if missing:
            raise ValueError(f"Thiếu biến môi trường: {', '.join(missing)}")
        if not password and not key:
            raise ValueError("Cần cấu hình PASSWORD hoặc KEY để xác thực SSH.")

        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError("PORT phải là số nguyên.") from exc
        if not 1 <= port <= 65535:
            raise ValueError("PORT phải nằm trong khoảng 1 đến 65535.")

        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        if read_bool_env("TRUST_NEW_HOST"):
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            self.client.set_missing_host_key_policy(paramiko.RejectPolicy())

        connect_options = {
            "hostname": host,
            "port": port,
            "username": user,
            "timeout": 10,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if password:
            connect_options["password"] = password
        if key:
            connect_options["key_filename"] = key

        try:
            self.client.connect(**connect_options)
        except Exception:
            self.client.close()
            raise

    def run(self, cmd: str, timeout: int = 15):
        _, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode(errors="replace").strip()
        err = stderr.read().decode(errors="replace").strip()
        code = stdout.channel.recv_exit_status()
        return code, out, err

    def close(self):
        self.client.close()


def check_namespace(r: Remote, prefix: str):
    code, out, _ = r.run("ip netns list")
    namespaces = (
        [line.split()[0] for line in out.splitlines() if line.strip()]
        if code == 0
        else []
    )

    return {
        "namespace": namespaces,
        "client_namespaces": [name for name in namespaces if name.startswith(prefix)],
    }


def check_bridge(r: Remote, bridge: str):
    code, out, _ = r.run(f"ip -br addr show {shlex.quote(bridge)}")
    return {
        "bridge_exists": code == 0,
        "bridge_addrs": out.split()[2:] if code == 0 and out else [],
    }


def check_ip_forward(r: Remote):
    code, out, _ = r.run("cat /proc/sys/net/ipv4/ip_forward")
    return {"ip_forward": out if code == 0 else "unknown"}


def check_dnsmasq(r: Remote):
    installed_code, _, _ = r.run("command -v dnsmasq")
    status_code, out, _ = r.run("systemctl is-active dnsmasq")
    return {
        "dnsmasq_installed": installed_code == 0,
        "dnsmasq_status": out if status_code == 0 or out else "unknown",
    }


def check_lease_dhcp(r: Remote):
    code, out, _ = r.run(
        f"wc -l < {shlex.quote(LEASE_FILE)} 2>/dev/null"
    )
    return {"dhcp_lease_count": int(out) if code == 0 and out.isdigit() else None}


def check_status(r: Remote, use_sudo: bool = False):
    bridge = os.getenv("BRIDGE", "").strip()
    prefix = os.getenv("PREFIX", "").strip()
    missing = [
        name
        for name, value in (("BRIDGE", bridge), ("PREFIX", prefix))
        if not value
    ]
    if missing:
        raise ValueError(f"Thiếu biến môi trường: {', '.join(missing)}")

    state = {}
    state.update(check_namespace(r, prefix))
    state.update(check_bridge(r, bridge))
    state.update(check_ip_forward(r))
    state.update(check_dnsmasq(r))
    state.update(check_lease_dhcp(r))

    sudo = "sudo -n " if use_sudo else ""
    details = {}
    for namespace in state["client_namespaces"]:
        code, out, err = r.run(
            f"{sudo}ip netns exec {shlex.quote(namespace)} ip -br addr"
        )
        details[namespace] = (
            out
            if code == 0
            else f"(không đọc được: {err or 'cần quyền root hoặc bật SUDO'})"
        )
    state["client_details"] = details
    state["router_ready"] = (
        state["bridge_exists"]
        and state["ip_forward"] == "1"
        and state["dnsmasq_status"] == "active"
    )

    print_report(state, bridge)


def print_report(state, bridge: str):
    def mark(ok: bool):
        return "[OK]   " if ok else "[THIEU]"

    print("== Router ==")
    print(
        f"{mark(state['bridge_exists'])} bridge {bridge}: "
        f"{' '.join(state['bridge_addrs']) or 'chưa có'}"
    )
    print(f"{mark(state['ip_forward'] == '1')} ip_forward = {state['ip_forward']}")
    print(f"{mark(state['dnsmasq_installed'])} dnsmasq đã cài")
    print(
        f"{mark(state['dnsmasq_status'] == 'active')} "
        f"dnsmasq đang chạy ({state['dnsmasq_status']})"
    )
    print(f"        DHCP lease hiện có: {state['dhcp_lease_count']}")

    print("\n== Client (namespace) ==")
    if not state["client_namespaces"]:
        print("[THIEU] chưa có namespace client nào")
    for namespace in state["client_namespaces"]:
        print(f"[OK]   {namespace}")
        for line in state["client_details"][namespace].splitlines():
            print(f"         {line}")

    print("\n== Kết luận ==")
    if state["router_ready"] and state["client_namespaces"]:
        print("Router và client đã sẵn sàng.")
    elif state["router_ready"]:
        print("Router đã sẵn sàng, cần tạo client.")
    else:
        print("Cần tạo/cấu hình router (xem các dòng [THIEU] ở trên).")
