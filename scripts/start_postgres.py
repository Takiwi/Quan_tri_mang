"""Start the project PostgreSQL container using credentials from DATABASE_URL."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL is missing from .env.", file=sys.stderr)
        return 1

    try:
        parsed = urlsplit(database_url)
        database_port = parsed.port or 5432
    except ValueError:
        print("DATABASE_URL is malformed or contains an invalid port.", file=sys.stderr)
        return 1
    if parsed.scheme not in {"postgres", "postgresql"}:
        print("DATABASE_URL must use postgres:// or postgresql://.", file=sys.stderr)
        return 1
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        print(
            "DATABASE_URL host must be localhost or 127.0.0.1 for this local Docker setup.",
            file=sys.stderr,
        )
        return 1
    if not parsed.username or not parsed.password or not parsed.path.strip("/"):
        print(
            "DATABASE_URL must include a username, password, and database name.",
            file=sys.stderr,
        )
        return 1
    if not 1 <= database_port <= 65535:
        print("DATABASE_URL port must be between 1 and 65535.", file=sys.stderr)
        return 1

    environment = os.environ.copy()
    environment["POSTGRES_USER"] = unquote(parsed.username)
    environment["POSTGRES_PASSWORD"] = unquote(parsed.password)
    environment["POSTGRES_DB"] = unquote(parsed.path.lstrip("/"))
    environment["POSTGRES_PORT"] = str(database_port)

    command = [
        "docker",
        "compose",
        "-f",
        str(PROJECT_ROOT / "docker-compose.yml"),
        "up",
        "-d",
        "--wait",
        "postgres",
    ]
    try:
        return subprocess.run(command, cwd=PROJECT_ROOT, env=environment).returncode
    except OSError as exc:
        print(f"Could not start Docker Compose: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
