import os, sys, subprocess
from pathlib import Path
from typing import Optional

SERVICE_NAME = "cz-visa-monitor"

def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]

def _detect_python_exe() -> str:
    proj = _root_dir()
    # Prefer uv venv at .venv/bin/python, then $VIRTUAL_ENV/bin/python, then current interpreter
    candidates = [
        proj / ".venv" / "bin" / "python",
        Path(os.environ["VIRTUAL_ENV"]) / "bin" / "python" if os.environ.get("VIRTUAL_ENV") else None,
        Path(sys.executable),
    ]
    for c in candidates:
        if c and c.exists():
            return c.as_posix()
    return sys.executable  # fallback

def _unit_text(python_exe: str, env_path: str) -> str:
    proj = _root_dir()
    script = proj / "visa_status.py"
    return f"""[Unit]
Description=CZ Visa Monitor (sequential)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={proj.as_posix()}
ExecStart={python_exe} {script.as_posix()} monitor -e {Path(env_path).resolve().as_posix()}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

def _need_root():
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise SystemExit("Require root: please run with sudo")

def install(env_path: str, service_name: Optional[str] = None, python_exe: Optional[str] = None):
    _need_root()
    name = service_name or SERVICE_NAME
    unit_path = Path(f"/etc/systemd/system/{name}.service")
    py = python_exe or _detect_python_exe()
    unit_path.write_text(_unit_text(py, env_path), encoding="utf-8")
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", name], check=True)
    print(f"Installed systemd service: {unit_path} (python={py})")

def uninstall(service_name: Optional[str] = None):
    _need_root()
    name = service_name or SERVICE_NAME
    subprocess.run(["systemctl", "disable", name], check=False)
    subprocess.run(["systemctl", "stop", name], check=False)
    unit_path = Path(f"/etc/systemd/system/{name}.service")
    if unit_path.exists():
        unit_path.unlink()
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print(f"Uninstalled systemd service: {name}")

def start(service_name: Optional[str] = None):
    _need_root()
    name = service_name or SERVICE_NAME
    subprocess.run(["systemctl", "start", name], check=True)

def stop(service_name: Optional[str] = None):
    _need_root()
    name = service_name or SERVICE_NAME
    subprocess.run(["systemctl", "stop", name], check=True)

def reload(service_name: Optional[str] = None):
    _need_root()
    name = service_name or SERVICE_NAME
    subprocess.run(["systemctl", "reload-or-restart", name], check=True)

def status(service_name: Optional[str] = None):
    name = service_name or SERVICE_NAME
    subprocess.run(["systemctl", "status", name])