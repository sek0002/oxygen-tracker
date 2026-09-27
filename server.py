#!/usr/bin/env python3
"""Oxygen tracker: static UI + authenticated SQLite API. Python 3.11+, no dependencies."""
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('OXYGEN_DB', ROOT / 'data' / 'oxygen.sqlite3'))
PIN = os.environ.get('OXYGEN_PIN', '6882')
ORIGIN = os.environ.get('OXYGEN_ALLOWED_ORIGIN', '')

def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    return db

def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
          side TEXT NOT NULL CHECK(side IN ('left','right')), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (ip TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
        ''')

def state(db):
    events = [json.loads(row['data']) for row in db.execute('SELECT data FROM events ORDER BY seq')]
    cylinders = {}
    for event in events:
        cylinders[event['side']] = event
    return {'events': events, 'cylinders': cylinders}

def digest(token):
    return hashlib.sha256(str(token).encode()).hexdigest()

class APIError(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)

def number(entry, key, low, high):
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise APIError(f'Enter a valid {key} between {low} and {high}.')
    return value

def api(action, body, ip):
    with connect() as db:
        # Serialize the read/check/append transaction: concurrent devices cannot overwrite history.
        db.execute('BEGIN IMMEDIATE')
        now = time.time()
        db.execute('DELETE FROM sessions WHERE expires < ?', (now,))
        if action == 'oxygen_login':
            db.execute('DELETE FROM attempts WHERE started < ?', (now - 900,))
            attempt = db.execute('SELECT * FROM attempts WHERE ip=?', (ip,)).fetchone()
            if attempt and attempt['count'] >= 10:
                return {'error': 'Too many PIN attempts. Try again in 15 minutes.'}, 429
            db.execute('INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(ip) DO UPDATE SET count=count+1', (ip, now))
            if not hmac.compare_digest(str(body.get('p_pin', '')).encode(), PIN.encode()):
                return {'error': 'Incorrect PIN. Please try again.'}, 401
            db.execute('DELETE FROM attempts WHERE ip=?', (ip,))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES (?,?)', (digest(token), now+43200))
            return {'token': token}, 200
        token = body.get('p_token', '')
        if not token or not db.execute('SELECT 1 FROM sessions WHERE hash=? AND expires>?', (digest(token), now)).fetchone():
            raise APIError('Your session has expired. Lock the tracker and sign in again.', 401)
        if action == 'oxygen_logout':
            db.execute('DELETE FROM sessions WHERE hash=?', (digest(token),))
            return {'ok': True}, 200
        if action == 'oxygen_state':
            return state(db), 200
        if action != 'oxygen_record':
            raise APIError('Unknown action.', 404)
        entry = body.get('p_entry')
        if not isinstance(entry, dict):
            raise APIError('A reading is required.')
        request_id = body.get('p_request_id')
        if not isinstance(request_id, str) or not 16 <= len(request_id) <= 100:
            raise APIError('A valid request ID is required.')
        if db.execute('SELECT 1 FROM events WHERE id=?', (request_id,)).fetchone():
            return state(db), 200
        side, kind = entry.get('side'), entry.get('kind')
        if side not in ('left', 'right') or kind not in ('initial', 'reading', 'replacement'):
            raise APIError('Invalid cylinder or activity.')
        row = db.execute('SELECT data FROM events WHERE side=? ORDER BY seq DESC LIMIT 1', (side,)).fetchone()
        current = json.loads(row['data']) if row else None
        if body.get('p_expected') != (current['id'] if current else None):
            raise APIError('This cylinder changed on another device. The latest reading has been loaded; review and try again.', 409)
        if (kind == 'initial' and current) or (kind != 'initial' and not current):
            raise APIError('Refresh the page and check the cylinder setup.')
        pressure = number(entry, 'pressure', 0, 400)
        rating = current if kind == 'reading' else entry
        # Nominal G cylinder: 50 L water volume, approximately 50 L gas per bar.
        rated_pressure, capacity = 200, 10000
        if kind == 'reading' and pressure > current['pressure']:
            raise APIError('Pressure has increased. Use Replace cylinder for a new cylinder.')
        for key, limit in [('notes', 1000), ('operator', 100), ('serial', 100)]:
            if not isinstance(entry.get(key, ''), str) or len(entry.get(key, '')) > limit:
                raise APIError(f'{key} must be text no longer than {limit} characters.')
        stamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        event = {
            'id': request_id, 'at': stamp, 'side': side, 'kind': kind,
            'pressure': pressure, 'previousPressure': current['pressure'] if current else None,
            'used': math.floor((current['pressure'] - pressure)*capacity/rated_pressure+.5) if kind == 'reading' else None,
            'ratedPressure': rated_pressure, 'capacity': capacity,
            'serial': rating.get('serial', '').strip(),
            'operator': entry.get('operator', '').strip(), 'notes': entry.get('notes', '').strip(),
            'installedAt': current['installedAt'] if kind == 'reading' else stamp,
            'startingPressure': current['startingPressure'] if kind == 'reading' else pressure,
        }
        db.execute('INSERT INTO events(id,side,data) VALUES (?,?,?)', (request_id, side, json.dumps(event)))
        return state(db), 200

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".webmanifest": "application/manifest+json"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # Request bodies, PINs, and session tokens are never logged.
        super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; connect-src 'self' " + (ORIGIN or '') + "; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if ORIGIN and self.headers.get('Origin') == ORIGIN:
            self.send_header('Access-Control-Allow-Origin', ORIGIN)
            self.send_header('Vary', 'Origin')
        super().end_headers()

    def send_json(self, data, status=200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith('/api/'):
            return self.send_json({'error': 'Not found.'}, 404)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise APIError('Request body is too large or empty.', 413)
            if self.headers.get_content_type() != 'application/json':
                raise APIError('Use application/json.', 415)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise APIError('Invalid request.')
            # Do not trust arbitrary forwarded headers. The proxy's IP is a shared rate-limit bucket.
            result, code = api(self.path.removeprefix('/api/'), body, self.client_address[0])
            self.send_json(result, code)
        except (ValueError, json.JSONDecodeError):
            self.send_json({'error': 'Invalid request.'}, 400)
        except APIError as error:
            self.send_json({'error': str(error)}, error.status)
        except Exception:
            self.send_json({'error': 'Database unavailable. No change was confirmed; refresh before retrying.'}, 500)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/health':
            with connect() as db:
                db.execute('SELECT 1')
            return self.send_json({'ok': True})
        # Explicit allowlist prevents downloading the database, backups, source, or environment files.
        if path not in ('/', '/index.html', '/styles.css', '/app.js', '/model.js', '/store.js', '/config.js', '/favicon.svg', '/manifest.webmanifest', '/sw.js', '/pwa.js', '/theme.js', '/icon-180.png', '/icon-192.png', '/icon-512.png'):
            return self.send_json({'error': 'Not found.'}, 404)
        super().do_GET()

    def do_HEAD(self):
        if self.path.split('?')[0] not in ('/', '/index.html', '/styles.css', '/app.js', '/model.js', '/store.js', '/config.js', '/favicon.svg', '/manifest.webmanifest', '/sw.js', '/pwa.js', '/theme.js', '/icon-180.png', '/icon-192.png', '/icon-512.png'):
            return self.send_json({'error': 'Not found.'}, 404)
        super().do_HEAD()

if __name__ == '__main__':
    initialize()
    address = (os.environ.get('OXYGEN_HOST', '127.0.0.1'), int(os.environ.get('PORT', '8080')))
    print(f'Oxygen tracker listening on http://{address[0]}:{address[1]}', flush=True)
    ThreadingHTTPServer(address, Handler).serve_forever()
