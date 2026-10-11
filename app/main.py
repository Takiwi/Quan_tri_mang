import argparse
import sys

from dotenv import load_dotenv

if __package__:
    from . import check_state
else:
    import check_state


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()

    parser = argparse.ArgumentParser(description="Kiểm tra trạng thái router và client.")
    parser.add_argument(
        "--sudo",
        action="store_true",
        help="Dùng sudo -n khi kiểm tra network namespace.",
    )
    args = parser.parse_args()
    use_sudo = args.sudo or check_state.read_bool_env("SUDO")

    remote = check_state.Remote()
    try:
        check_state.check_status(remote, use_sudo=use_sudo)
    finally:
        remote.close()


if __name__ == "__main__":
    main()
