"""
Background Service Management for TeleFeed.

On Linux: Uses systemd user services.
On Windows: Uses a VBScript in the Startup folder.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from telefeed.config import XDG_CONFIG_HOME, DEFAULT_STATE_DIR
from telefeed.display import print_error, print_info, print_success, print_warning


IS_WINDOWS = platform.system().lower() == "windows"

SYSTEMD_USER_DIR = XDG_CONFIG_HOME / "systemd" / "user"
SERVICE_FILE_PATH = SYSTEMD_USER_DIR / "telefeed.service"

if IS_WINDOWS:
    STARTUP_DIR = Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    WINDOWS_VBS_PATH = STARTUP_DIR / "telefeed_background.vbs"


def get_telefeed_exec() -> str:
    """Return the absolute command string to execute TeleFeed."""
    which_path = shutil.which("telefeed")
    if which_path:
        return which_path
    
    # Fallback to current sys.executable -m telefeed
    return f"{sys.executable} -m telefeed"


def install_service() -> bool:
    """Install and enable the background service for TeleFeed."""
    telefeed_cmd = get_telefeed_exec()

    if IS_WINDOWS:
        # Create a VBS script to run it invisibly
        if not STARTUP_DIR.exists():
            print_error("Cannot find Windows Startup directory.")
            return False
            
        log_file = DEFAULT_STATE_DIR / "telefeed.log"
        DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Use pythonw if falling back, else just use the executable (it's a console script, but VBS vbHide hides it)
        # We wrap the command in cmd /c to redirect output to a log file
        vbs_content = f"""Set WshShell = CreateObject("WScript.Shell")\nWshShell.Run "cmd /c """ + f'""{telefeed_cmd}"" fetch --live --notify >> ""{log_file}"" 2>&1", 0, False\n'

        with WINDOWS_VBS_PATH.open("w", encoding="utf-8") as f:
            f.write(vbs_content)
        
        print_success(f"Wrote Windows startup script to [bold]{WINDOWS_VBS_PATH}[/bold]")
        
        # Start it immediately
        subprocess.run(["wscript", str(WINDOWS_VBS_PATH)], check=False)
        print_success("TeleFeed background service started!")
        return True

    else:
        # Linux systemd logic
        if shutil.which("systemctl") is None:
            print_error("systemctl is not available on this system.")
            return False

        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)

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
    """Disable and remove the background service for TeleFeed."""
    if IS_WINDOWS:
        if WINDOWS_VBS_PATH.exists():
            WINDOWS_VBS_PATH.unlink()
            print_success("TeleFeed startup script removed.")
            service_action("stop")
            return True
        else:
            print_warning("Service is not installed.")
            return True
    else:
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

    if IS_WINDOWS:
        if action == "start":
            if WINDOWS_VBS_PATH.exists():
                subprocess.run(["wscript", str(WINDOWS_VBS_PATH)], check=False)
                print_success("Started TeleFeed.")
            else:
                print_error("Service not installed. Run 'telefeed service install' first.")
        elif action == "stop":
            # Attempt to kill python processes running telefeed
            try:
                # Use WMIC to find the process with telefeed in the command line
                subprocess.run(
                    'wmic process where "CommandLine like \'%telefeed fetch --live%\'" call terminate',
                    shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                print_success("Stopped TeleFeed.")
            except Exception as e:
                print_error(f"Error stopping service: {e}")
        elif action == "restart":
            service_action("stop")
            service_action("start")
        elif action == "status":
            print_info("Status check is not natively supported on Windows. Check logs instead.")
    else:
        try:
            subprocess.run(["systemctl", "--user", action, "telefeed.service"])
        except Exception as e:
            print_error(f"Failed to run systemctl --user {action}: {e}")


def service_logs() -> None:
    """Tail systemd user logs or Windows log file."""
    if IS_WINDOWS:
        log_file = DEFAULT_STATE_DIR / "telefeed.log"
        if not log_file.exists():
            print_warning(f"Log file not found at {log_file}")
            return
        
        print_info(f"Tailing logs from {log_file} (Press Ctrl+C to stop)")
        try:
            # Simple tail implementation for Windows using PowerShell
            subprocess.run(["powershell", "-Command", f"Get-Content -Path '{log_file}' -Wait -Tail 50"])
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print_error(f"Failed to read logs: {e}")
    else:
        try:
            subprocess.run(["journalctl", "--user", "-u", "telefeed.service", "-n", "50", "-f"])
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print_error(f"Failed to fetch journalctl logs: {e}")
