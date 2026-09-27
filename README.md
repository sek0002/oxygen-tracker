# O₂ cylinder tracker

A small server-hosted app for two independent G oxygen cylinders. The whole app runs from one Python process; SQLite stores the shared history. FastAPI and Uvicorn serve the app. No Node installation, frontend build, or cloud database account is required.

## Deploy from GitHub

See **[DEPLOY.md](DEPLOY.md)** for cloning, Docker with automatic HTTPS, existing reverse proxies, a Linux service, updates and backups.

## Start

Requires Python 3.11 or newer.

```sh
cd oxygen-tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn server:app --host 0.0.0.0 --port 8070 --no-proxy-headers
```

Open http://127.0.0.1:8070 and sign in with PIN **6882**.

For access over a trusted local network:

```sh
OXYGEN_HOST=0.0.0.0 PORT=8070 python3 server.py
```

For an internet-facing server, run behind an HTTPS reverse proxy such as Caddy or nginx. `Caddyfile.example` shows the proxy configuration. Keep the Python port bound to localhost when the proxy runs on the same host. The four-digit PIN is intentionally a simple shared access code; requests are limited to 10 failed attempts per 15 minutes, and sessions expire after 12 hours. Behind a proxy, the attempt limit is shared by its users.

## Run in the background (Linux)

After creating `.venv` and installing `requirements.txt`, stop any manual server and run:

```sh
sudo bash install-service.sh
```

This installs and starts a systemd service, enables startup after reboot, and keeps the existing database. See [service instructions](DEPLOY.md#install-as-a-systemd-service) for logs and configuration.

## Docker

```sh
docker compose up -d --build
```

The supplied Compose file binds to localhost:8070 for a reverse proxy and persists SQLite in the `oxygen-data` Docker volume. Recreating the container preserves history; deleting the volume removes it. Docker was not available in the development environment, so this deployment path has not been runtime-tested.

## Configuration

| Environment variable | Default | Purpose |
|---|---|---|
| `OXYGEN_PIN` | `6882` | Shared access PIN |
| `OXYGEN_HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8070` | Server port |
| `OXYGEN_DB` | `data/oxygen.sqlite3` beside server.py | Persistent SQLite database path |
| `OXYGEN_ALLOWED_ORIGIN` | empty | Optional exact GitHub Pages origin for split hosting |

No configuration is required when the server hosts the whole app. The public `config.js` keeps `apiBase` empty. If you later choose a GitHub Pages frontend, set `apiBase` to your HTTPS backend origin and `OXYGEN_ALLOWED_ORIGIN` on the server to the exact Pages origin, e.g. `https://sek0002.github.io`. Publish only the frontend HTML, CSS, JavaScript, manifest and icon files; never publish the database or backups. A Pages workflow is intentionally not enabled because you selected manual server deployment.

## Using the tracker

1. Choose **Set up cylinder** on each side. Enter its starting gauge pressure manually. Both cylinders are assumed to be nominal 50 L G cylinders; there are no capacity or rated-pressure inputs.
2. Choose **Add reading** after each session. The app records the date/time and shows the change in bar and estimated litres while typing, after saving, on the cylinder card, and in history. Negative deltas mean gas used; setup and replacement entries are marked as new baselines.
3. Pressure below **100 bar** is a warning; pressure below **50 bar** is critical. Exactly 100 bar is normal; exactly 50 bar is warning.
4. Use **Replace cylinder** when changing a cylinder. Enter the new starting pressure, cylinder ID, and optional operator/notes. Previous history is retained; a replacement creates a new baseline and is not recorded as consumption.
5. **Export text file** downloads all history for both cylinders, even when the on-screen history is filtered. Export timestamps use UTC; the screen uses the viewer's local time zone.

Estimated litres used = pressure drop × 50 L/bar. Remaining litres = current pressure × 50 L/bar. This assumes a nominal 50 L water-volume G cylinder. The visual scale uses the manually entered starting pressure with a minimum of 125 bar so the dotted 100 bar warning and 50 bar critical markers always remain visible. Gas fill has a straight upper edge. Historical events retain their original stored estimates; new readings use the fixed G-cylinder assumption. These are approximate pressure-based estimates, not temperature/compressibility-corrected measurements. Gauge readings and cylinder specifications remain the source of truth. The overview total sums the cylinders that have been set up.

The app refreshes shared data every 15 seconds while visible. Saves are atomic and include a concurrency check: if another device updated a cylinder, the app reloads it and asks the user to review before saving. Repeated delivery of a save uses the same request ID to avoid duplicating the event. Readings are append-only. An increased pressure requires a cylinder replacement; there is no silent history editing.

## Database and backups

The server requires a writable persistent data directory. The static-file allowlist prevents downloading database files or server source. Session tokens are stored as hashes in SQLite; the browser holds its token only for the current tab session. The configured PIN is checked on the server and is not included in frontend JavaScript.

Back up the database using SQLite's backup API, which also works while the server is running:

```sh
python3 - <<'PY'
import sqlite3
with sqlite3.connect('data/oxygen.sqlite3') as source:
    with sqlite3.connect('oxygen-backup.sqlite3') as destination:
        source.backup(destination)
PY
```

To restore, stop the app, preserve the current database and any WAL/SHM files elsewhere, and place the backup at the configured database path before restarting. Text exports are human-readable archives; they are not database restore files.

## Checks

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s . -p 'test_*.py' -v
node --test model.test.js  # optional, requires Node for frontend model tests
```

Validated with server tests and a Chrome browser integration run covering wrong PIN, independent cylinders, litre calculations, threshold states, replacement records, persistence after reload, complete text export, a second browser session, lock, private-file protection, and a 390px mobile layout.

## Install on devices

Deploy on an HTTPS domain (localhost also works during development). Plain HTTP at a server IP or LAN address is not sufficient for PWA installation.

- **Chrome / Edge / Android:** select **Install app** or use the browser’s installation menu.
- **iPhone / iPad:** in Safari, use **Share → Add to Home Screen**, enable **Open as Web App** when offered, then **Add**.
- **Mac Safari:** **File → Add to Dock**.

The installed app opens in its own window with an O₂ icon. The service worker caches only the public interface. Login and shared readings always require a connection; API responses and cylinder records are never cached or queued offline. The browser controls whether and when an installation prompt is offered.

PWA validation covered Chrome’s installability checks, manifest and PNG icons, service-worker registration, offline shell loading and uncached API requests. Physical iOS/Android installation has not been tested.

## Appearance

Use the moon/sun button on the sign-in screen or in the header to switch light/dark mode. The initial theme follows the device preference; an explicit selection is saved on that device and shared between browser tabs.

The colours follow MUUC’s active [Underwater website theme](https://muuc.org.au/static/css/theme.css): navy `#030a1f`, blue `#1424cc`, cyan `#16b8d9`, and dark surfaces `#20223f`. Light mode uses its light neutrals with matching blue/cyan accents.
