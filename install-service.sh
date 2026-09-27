#!/usr/bin/env bash
# Install on the Linux server: sudo bash install-service.sh
set -euo pipefail
if [[ $(uname -s) != Linux ]] || ! command -v systemctl >/dev/null; then
  echo 'This installer requires Linux with systemd. Run it on your server.' >&2
  exit 1
fi
if [[ ${EUID} -ne 0 ]]; then
  echo 'Run: sudo bash install-service.sh' >&2
  exit 1
fi
app_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
run_user=${OXYGEN_SERVICE_USER:-${SUDO_USER:-}}
if [[ -z "$run_user" || "$run_user" == root ]]; then
  echo 'Run sudo from your normal server account, or set OXYGEN_SERVICE_USER to a non-root account.' >&2
  exit 1
fi
id "$run_user" >/dev/null
python_bin="$app_dir/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  echo 'Create the virtual environment first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt' >&2
  exit 1
fi
# Check imports as the service user, not as root.
runuser -u "$run_user" -- "$python_bin" -c 'import fastapi, uvicorn' || {
  echo 'Install requirements.txt into .venv and ensure the service account can read it.' >&2
  exit 1
}
# Keep existing custom configuration on reinstall. The default database stays in the checkout.
config_path=/etc/oxygen-tracker.env
if [[ ! -e "$config_path" ]]; then
  install -m 600 /dev/null "$config_path"
  cat > "$config_path" <<'CONFIG'
OXYGEN_HOST=0.0.0.0
PORT=8080
OXYGEN_PIN=6882
# Optional: OXYGEN_DB=/absolute/path/to/existing/oxygen.sqlite3
CONFIG
fi
runuser -u "$run_user" -- mkdir -p "$app_dir/data"
runuser -u "$run_user" -- test -w "$app_dir/data" || {
  echo 'The service account needs write access to the existing data directory.' >&2
  exit 1
}
unit_path=/etc/systemd/system/oxygen-tracker.service
if [[ -e "$unit_path" ]]; then
  cp -p "$unit_path" "$unit_path.backup-$(date +%Y%m%d-%H%M%S)"
fi
# Quote paths for systemd, including spaces and percent specifiers.
"$python_bin" - "$app_dir" "$run_user" "$unit_path" <<'PY'
import sys
from pathlib import Path
app_dir, user, destination = sys.argv[1:]
def quote(value):
    if any(c in value for c in '\n\r\x00'):
        raise SystemExit('Unsupported newline in path or account name.')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'
unit = f'''[Unit]
Description=MUUC Oxygen Tracker (FastAPI)
After=network.target

[Service]
Type=simple
User={quote(user)}
WorkingDirectory={quote(app_dir)}
EnvironmentFile=/etc/oxygen-tracker.env
ExecStart={quote(app_dir + '/.venv/bin/python')} {quote(app_dir + '/server.py')}
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
'''
Path(destination).write_text(unit)
PY
chmod 644 "$unit_path"
systemd-analyze verify "$unit_path"
systemctl daemon-reload
systemctl enable oxygen-tracker.service
systemctl restart oxygen-tracker.service
sleep 2
if ! systemctl is-active --quiet oxygen-tracker.service; then
  journalctl -u oxygen-tracker.service -n 30 --no-pager
  echo 'Service did not start. Stop any old process on the same port and inspect the logs.' >&2
  exit 1
fi
systemctl status oxygen-tracker.service --no-pager
printf '\nInstalled. Logs: sudo journalctl -u oxygen-tracker -f\nConfiguration: sudo nano /etc/oxygen-tracker.env\n'
