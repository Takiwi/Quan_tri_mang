"""
config.py - Tải và phân tích cấu hình từ config.yaml và biến môi trường .env

Cung cấp hàm load_config() trả về dict chứa toàn bộ cấu hình,
bao gồm thông tin SSH từ biến môi trường.
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


# Đường dẫn mặc định tới file config.yaml (cùng thư mục với module này)
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"

# Đường dẫn mặc định tới file .env (thư mục cha của package)
_DEFAULT_ENV_PATH = Path(__file__).parent.parent / ".env"


def load_config(config_path: str | None = None, env_path: str | None = None) -> dict:
    """
    Tải cấu hình từ file YAML và biến môi trường.

    Args:
        config_path: Đường dẫn tới file config.yaml. Mặc định là config.yaml trong thư mục package.
        env_path: Đường dẫn tới file .env. Mặc định là .env trong thư mục gốc dự án.

    Returns:
        dict chứa toàn bộ cấu hình bao gồm cả thông tin SSH.
    """
    # Tải biến môi trường từ .env
    env_file = Path(env_path) if env_path else _DEFAULT_ENV_PATH
    load_dotenv(dotenv_path=str(env_file))

    # Đọc file config.yaml
    cfg_file = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    with open(cfg_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Đảm bảo các giá trị mặc định
    config.setdefault("scan_interval", 10)
    config.setdefault("client_threshold", 5)
    config.setdefault("lease_file", "/var/lib/misc/dnsmasq.leases")
    config.setdefault("bridge", "br-lab")
    config.setdefault("client_prefix", "client")
    config.setdefault("ssid_map", {})

    # Thêm thông tin SSH từ biến môi trường
    config["ssh"] = {
        "host": os.environ.get("SSH_HOST", ""),
        "port": int(os.environ.get("SSH_PORT", 22)),
        "user": os.environ.get("SSH_USER", ""),
        "password": os.environ.get("SSH_PASSWORD", ""),
    }

    return config
