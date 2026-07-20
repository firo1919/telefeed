"""
Systemd User Service Management for TeleFeed.

Allows installing, removing, starting, stopping, checking status,
and viewing live logs of the TeleFeed background systemd service.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from telefeed.config import XDG_CONFIG_HOME
from telefeed.display import print_error, print_info, print_success, print_warning


SYSTEMD_USER_DIR = XDG_CONFIG_HOME / "systemd" / "user"
SERVICE_FILE_PATH = SYSTEMD_USER_DIR / "telefeed.service"


def get_telefeed_exec() -> str:
    """Return the absolute command string to execute TeleFeed."""
    which_path = shutil.which("telefeed")
    if which_path:
        return which_path
    
    # Fallback to current sys.executable -m telefeed
    return f"{sys.executable} -m telefeed"


def install_service() -> bool:
    """Install and enable the systemd user service for TeleFeed."""
    if shutil.which("systemctl") is None:
        print_error("systemctl is not available on this system.")
        return False

    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    telefeed_cmd = get_telefeed_exec()

    service_content = f"""[Unit]
Description=TeleFeed Telegram Feed Aggregator Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={telefeed_cmd} fetch --live --notify
Restart=on-failure
RestartSec=15
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""

    with SERVICE_FILE_PATH.open("w", encoding="utf-8") as f:
        f.write(service_content)

    print_success(f"Wrote systemd unit file to [bold]{SERVICE_FILE_PATH}[/bold]")

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "telefeed.service"], check=True)
        print_success("TeleFeed systemd service enabled and started!")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to enable systemd service: {e}")
        return False


def uninstall_service() -> bool:
    """Disable and remove the systemd user service for TeleFeed."""
    if SERVICE_FILE_PATH.exists():
        try:
            subprocess.run(["systemctl", "--user", "disable", "--now", "telefeed.service"], check=False)
            SERVICE_FILE_PATH.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            print_success("TeleFeed systemd service removed.")
            return True
        except Exception as e:
            print_error(f"Error removing service: {e}")
            return False
    else:
        print_warning("Service is not installed.")
        return True


def service_action(action: str) -> None:
    """Run start, stop, restart, or status for telefeed.service."""
    valid_actions = {"start", "stop", "restart", "status"}
    if action not in valid_actions:
        print_error(f"Invalid action {action!r}. Must be one of {valid_actions}")
        return

    try:
        subprocess.run(["systemctl", "--user", action, "telefeed.service"])
    except Exception as e:
        print_error(f"Failed to run systemctl --user {action}: {e}")


def service_logs() -> None:
    """Tail systemd user logs for telefeed.service."""
    try:
        subprocess.run(["journalctl", "--user", "-u", "telefeed.service", "-n", "50", "-f"])
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print_error(f"Failed to fetch journalctl logs: {e}")
