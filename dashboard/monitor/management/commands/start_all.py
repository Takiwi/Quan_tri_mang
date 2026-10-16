"""Run router checks, WifiMon, and the Django development server together."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Check the router, start WifiMon, and then start the Django server."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--addrport",
            default="127.0.0.1:8000",
            help="Address and port for the Django server (default: 127.0.0.1:8000).",
        )
        parser.add_argument(
            "--sudo",
            action="store_true",
            help="Use sudo -n while checking client namespaces.",
        )

    def handle(self, *args, **options) -> None:
        project_root = Path(settings.BASE_DIR).parent

        self.stdout.write(self.style.NOTICE("Step 1/4: Starting PostgreSQL..."))
        postgres_command = [
            sys.executable,
            str(project_root / "scripts" / "start_postgres.py"),
        ]
        try:
            postgres_result = subprocess.run(
                postgres_command,
                cwd=project_root,
                check=False,
            )
        except OSError as exc:
            raise CommandError(f"Could not start PostgreSQL: {exc}") from exc
        if postgres_result.returncode != 0:
            raise CommandError(
                "PostgreSQL could not be started; WifiMon and Django were not started."
            )

        check_command = [sys.executable, "-m", "app.main"]
        if options["sudo"]:
            check_command.append("--sudo")

        self.stdout.write(
            self.style.NOTICE("Step 2/4: Checking router configuration...")
        )
        try:
            check_result = subprocess.run(check_command, cwd=project_root, check=False)
        except OSError as exc:
            raise CommandError(f"Could not run the router check: {exc}") from exc
        if check_result.returncode != 0:
            raise CommandError(
                "Router check failed or the router is not ready; "
                "WifiMon and Django were not started."
            )

        processes: list[subprocess.Popen] = []
        try:
            self.stdout.write(self.style.NOTICE("Step 3/4: Starting WifiMon..."))
            try:
                scanner = subprocess.Popen(
                    [sys.executable, "-m", "wifimon"],
                    cwd=project_root,
                )
                processes.append(scanner)

                self.stdout.write(self.style.NOTICE("Step 4/4: Starting Django..."))
                manage_py = Path(settings.BASE_DIR) / "manage.py"
                server = subprocess.Popen(
                    [
                        sys.executable,
                        str(manage_py),
                        "runserver",
                        options["addrport"],
                        "--noreload",
                    ],
                    cwd=settings.BASE_DIR,
                )
                processes.append(server)
            except OSError as exc:
                raise CommandError(f"Could not start a project process: {exc}") from exc

            self.stdout.write(
                self.style.SUCCESS(
                    f"All services are running. Open http://{options['addrport']}/ "
                    "(press Ctrl+C to stop)."
                )
            )

            while True:
                server_code = server.poll()
                if server_code is not None:
                    if server_code != 0:
                        raise CommandError(
                            f"Django server exited with code {server_code}."
                        )
                    return

                scanner_code = scanner.poll()
                if scanner_code is not None:
                    raise CommandError(
                        f"WifiMon exited with code {scanner_code}; "
                        "the Django server will be stopped."
                    )

                time.sleep(0.25)
        except KeyboardInterrupt:
            self.stdout.write("\nStopping project services...")
        finally:
            for process in reversed(processes):
                self._stop_process(process)

    @staticmethod
    def _stop_process(process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
