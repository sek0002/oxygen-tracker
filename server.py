#!/usr/bin/env python3
"""Oxygen tracker: static UI + authenticated SQLite API. FastAPI + Uvicorn, Python 3.11+."""
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
from contextlib import asynccontextmanager
import mimetypes

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
import uvicorn

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

PUBLIC_FILES = {
    'index.html', 'styles.css', 'app.js', 'model.js', 'store.js', 'config.js',
    'favicon.svg', 'manifest.webmanifest', 'sw.js', 'pwa.js', 'theme.js',
    'icon-180.png', 'icon-192.png', 'icon-512.png',
}


@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(initialize)
    yield


app = FastAPI(title='MUUC Oxygen Tracker', lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
if ORIGIN:
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN],
                       allow_methods=['POST'], allow_headers=['Content-Type'])


@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; connect-src 'self' " + ORIGIN +
        "; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


@app.post('/api/{action}')
async def handle_api(action: str, request: Request):
    try:
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            raise APIError('Use application/json.', 415)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 16384:
                raise APIError('Request body is too large.', 413)
        if not raw:
            raise APIError('Request body is empty.', 400)
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise APIError('Invalid request.')
        # SQLite work runs in a thread so other requests do not block the event loop.
        ip = request.client.host if request.client else 'unknown'
        result, code = await run_in_threadpool(api, action, body, ip)
        return JSONResponse(result, status_code=code)
    except (ValueError, UnicodeError):
        return JSONResponse({'error': 'Invalid request.'}, status_code=400)
    except APIError as error:
        return JSONResponse({'error': str(error)}, status_code=error.status)
    except Exception:
        return JSONResponse({'error': 'Database unavailable. No change was confirmed; refresh before retrying.'}, status_code=500)


@app.get('/health')
def health():
    try:
        with connect() as db:
            db.execute('SELECT 1')
        return {'ok': True}
    except sqlite3.Error:
        return JSONResponse({'error': 'Database unavailable.'}, status_code=503)


@app.api_route('/{path:path}', methods=['GET', 'HEAD'])
def static_file(path: str):
    name = path or 'index.html'
    # Never mount the project directory: it contains the database and configuration.
    if name not in PUBLIC_FILES:
        return JSONResponse({'error': 'Not found.'}, status_code=404)
    mime = 'application/manifest+json' if name.endswith('.webmanifest') else mimetypes.guess_type(name)[0]
    return FileResponse(ROOT / name, media_type=mime)


if __name__ == '__main__':
    uvicorn.run(app, host=os.environ.get('OXYGEN_HOST', '127.0.0.1'),
                port=int(os.environ.get('PORT', '8080')), proxy_headers=False)
