# Deploy the O₂ tracker

The server hosts the entire app and its SQLite database. GitHub stores the source; GitHub Pages is not needed. Use one of the methods below. The default PIN is **6882**.

## 1. Download from GitHub

Repository: https://github.com/sek0002/oxygen-tracker

This repository is private. Authenticate with a GitHub account that has access, or configure a read-only SSH deploy key for the server. Do not put access tokens in clone URLs.

With GitHub CLI and Git installed:

```sh
gh auth login
gh repo clone sek0002/oxygen-tracker
cd oxygen-tracker
```

Or with an authorized SSH key:

```sh
git clone git@github.com:sek0002/oxygen-tracker.git
cd oxygen-tracker
```

You can also download the release ZIP while signed in, extract it, and skip cloning. ZIP installs are updated by replacing the application files; preserve your `.env` and database.

## 2. Recommended: Docker with automatic HTTPS

Requires Docker Engine with the Compose plugin. Install using the [official Docker instructions](https://docs.docker.com/engine/install/).

1. Point a domain or subdomain (for example, `oxygen.yourdomain.com`) to the server's public IP with a DNS A record (and an AAAA record only if IPv6 reaches this server).
2. Allow inbound TCP ports **80 and 443** through the server firewall/router. UDP 443 is optional for HTTP/3. These ports must be free; if an existing reverse proxy owns them, use the next section instead.
3. Copy the configuration and edit it:

```sh
cp .env.example .env
nano .env
```

Set `OXYGEN_DOMAIN` to your hostname, **without** `https://` or a path. `OXYGEN_PIN` defaults to `6882`; set another value if desired.

4. Start:

```sh
docker compose -f compose.https.yaml up -d --build
```

5. Check:

```sh
docker compose -f compose.https.yaml ps
docker compose -f compose.https.yaml logs --tail=50
```

Open `https://YOUR_HOSTNAME`, enter the PIN, and set up each cylinder with its current gauge pressure. Caddy obtains and renews the TLS certificate automatically. It can take a minute after startup; DNS and ports must already be reachable.

The app is exposed only through Caddy. SQLite is stored in the persistent `oxygen-data` volume, and certificate state is stored in separate persistent Caddy volumes. The Compose project name is derived from the checkout directory: keep the directory name consistent during updates so Compose continues to use the same volumes.

## Existing reverse proxy

If nginx, Caddy, Nginx Proxy Manager, or another proxy already manages HTTPS, use:

```sh
cp .env.example .env
# Optionally edit OXYGEN_PIN; OXYGEN_DOMAIN is unused for this method.
docker compose up -d --build
```

The app listens on **127.0.0.1:8070** on the Docker host. Forward your HTTPS hostname to `http://127.0.0.1:8070`. The supplied `Caddyfile.example` shows a host-based Caddy configuration. For a proxy running inside another container, localhost refers to that proxy container: attach the services to a shared Docker network and use `oxygen:8070` instead.

Do not run both Compose methods simultaneously. To switch methods, stop the first without deleting volumes, then start the other in the same project directory.

## Python without Docker

Requires Python **3.11+**. Install FastAPI and Uvicorn in a virtual environment; no frontend build is needed.

For a server installation (after cloning, or `git pull --ff-only`):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn server:app --host 0.0.0.0 --port 8070 --no-proxy-headers
```

Open `http://YOUR_SERVER_IP:8070` (allow port 8070 for LAN access).

### Install as a systemd service

On a Linux server with systemd, stop the manually running server with Ctrl+C, then run from the checkout:

```sh
sudo bash install-service.sh
```

The installer uses your normal account (`SUDO_USER`) and the checkout's `.venv`. It enables automatic startup on reboot and restart after a failure. It preserves the existing `data/oxygen.sqlite3`; no database migration is required. Existing `/etc/oxygen-tracker.env` settings are retained on reinstall. If running from a root shell, choose a non-root service account explicitly:

```sh
sudo OXYGEN_SERVICE_USER=yourusername bash install-service.sh
```

Existing services retain their configuration when pulling updates. To change an already installed service from port 8080 to 8070:

```sh
sudo sed -i 's/^PORT=.*/PORT=8070/' /etc/oxygen-tracker.env
sudo systemctl restart oxygen-tracker
```

Update any reverse proxy upstream or firewall rule to match port 8070.

Service controls:

```sh
sudo systemctl status oxygen-tracker
sudo journalctl -u oxygen-tracker -f
sudo systemctl restart oxygen-tracker
sudo systemctl stop oxygen-tracker
```

Configuration:

```sh
sudo nano /etc/oxygen-tracker.env
sudo systemctl restart oxygen-tracker
```

Defaults: `OXYGEN_HOST=0.0.0.0`, `PORT=8070`, and `OXYGEN_PIN=6882`. If your existing installation uses a custom `OXYGEN_DB`, add that absolute path to `/etc/oxygen-tracker.env` **before** running the installer. For a reverse proxy on the same host, use `OXYGEN_HOST=127.0.0.1` and configure HTTPS using `Caddyfile.example`.

Keep the checkout and virtual environment at their installed paths. Run the installer again after moving them. The service account must be able to read the app and write its database directory. The installer backs up any existing service unit before replacing it. It does not stop unrelated processes occupying port 8070.

To uninstall the service while keeping the app and database:

```sh
sudo systemctl disable --now oxygen-tracker
sudo rm /etc/systemd/system/oxygen-tracker.service
sudo systemctl daemon-reload
```

The installer must run on your Linux server; it cannot install systemd services on macOS or Windows.

## Update

From the same checkout directory, first make a backup, then:

```sh
git pull --ff-only
docker compose -f compose.https.yaml up -d --build
```

For the existing-proxy method omit `-f compose.https.yaml`. For the Python service, run `.venv/bin/python -m pip install -r requirements.txt` and then `sudo systemctl restart oxygen-tracker` after pulling. Refresh or reopen the installed app to get updated assets.

Do **not** run `docker compose down -v`: it deletes persistent volumes. Rebuilding or restarting containers preserves the database.

## Back up SQLite

For Docker with automatic HTTPS, run this from the checkout directory. It uses SQLite's online backup API:

```sh
mkdir -p backups
docker compose -f compose.https.yaml exec -T oxygen python -c "import sqlite3; source=sqlite3.connect('/data/oxygen.sqlite3'); target=sqlite3.connect('/data/oxygen-backup.sqlite3'); source.backup(target); target.close(); source.close()"
docker compose -f compose.https.yaml cp oxygen:/data/oxygen-backup.sqlite3 "backups/oxygen-$(date +%Y%m%d-%H%M%S).sqlite3"
```

Omit `-f compose.https.yaml` for the existing-proxy method. Copy backups off the server. Text exports are readable history records, not a substitute for a database backup. See README.md for the plain Python backup method.

To restore a Docker backup (replace `backups/oxygen-YYYYMMDD-HHMMSS.sqlite3` with your chosen file):

```sh
docker compose -f compose.https.yaml stop oxygen
docker compose -f compose.https.yaml run --rm --no-deps -v "$PWD/backups:/backup:ro" oxygen python -c "import sqlite3; source=sqlite3.connect('/backup/oxygen-YYYYMMDD-HHMMSS.sqlite3'); target=sqlite3.connect('/data/oxygen.sqlite3'); source.backup(target); target.close(); source.close()"
docker compose -f compose.https.yaml up -d
```

Back up the current database before restoring: a restore replaces the current records. Keep the app stopped during restore.

## Install on phones / desktops

Use the HTTPS address, not a plain HTTP server IP.

- **Android / Chrome / Edge:** tap the install icon, or select Install app from the browser menu.
- **iPhone / iPad:** Safari → Share → Add to Home Screen → Add (enable Open as Web App if offered).
- **Mac Safari:** File → Add to Dock.

The interface can open offline, but signing in and saving readings require a server connection.

## Troubleshooting

- **Certificate fails:** confirm DNS resolves to this server and ports 80/443 reach Caddy; inspect Caddy logs.
- **502 / app unhealthy:** inspect `docker compose -f compose.https.yaml logs oxygen`; confirm the data volume is writable.
- **PIN rejected:** check `OXYGEN_PIN` in `.env`, then rerun `up -d`. Ten failed attempts cause a 15-minute cooldown shared by users behind the same proxy.
- **Install unavailable:** use HTTPS and a supported browser outside private browsing mode.
- **History appears empty after a move:** check the Compose project/directory name and database volume before entering new data.

The four-digit PIN is a simple shared access gate. Keep HTTPS enabled. Docker and Caddy configurations are supplied but were not runtime-tested on this development machine; Docker was unavailable. The Python server, browser workflows, data persistence, concurrency checks, and PWA installability were tested.
