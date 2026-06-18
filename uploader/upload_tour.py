#!/usr/bin/env python3
"""
Street View 360 Photo Tour Uploader

Uploads equirectangular 360 JPEGs (RICOH THETA, Insta360, GoPro MAX, etc.) to the
Street View Publish API, links them to a place, and auto-builds navigation
connections between photos.

Usage:
  # EXIF GPS + auto-connect in file order (simple linear route)
  python upload_tour.py --folder ./photos

  # With a CSV manifest (gardens / branching routes -- recommended)
  python upload_tour.py --folder ./photos --manifest ./photos/tour.csv

  # Link to a Google place
  python upload_tour.py --folder ./photos --manifest ./photos/tour.csv --place-id ChIJxxxxxxxx

  # Dry run (no upload)
  python upload_tour.py --folder ./photos --manifest ./photos/tour.csv --dry-run
"""

import os
import sys
import json
import csv
import time
import math
import argparse
import threading
import webbrowser
import requests
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build as build_service
    import piexif
except ImportError:
    print("Missing dependencies. Install them first:")
    print("   pip install -r requirements.txt")
    sys.exit(1)

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
SCOPES = ['https://www.googleapis.com/auth/streetviewpublish']
BASE_URL = 'https://streetviewpublish.googleapis.com/v1'
TOKEN_FILE = Path(__file__).parent / 'token.json'
CREDENTIALS_FILE = Path(__file__).parent / 'client_secrets.json'

# ──────────────────────────────────────────────
# OAuth 2.0
# ──────────────────────────────────────────────
def get_credentials():
    """OAuth 2.0 auth (custom loopback flow that avoids Windows IPv4/IPv6 issues)."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print("client_secrets.json not found")
                print(f"   Save it as {CREDENTIALS_FILE}")
                sys.exit(1)

            PORT = 8085
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            flow.redirect_uri = f'http://127.0.0.1:{PORT}/'
            auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

            received = {}

            class _Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    params = parse_qs(urlparse(self.path).query)
                    received['code'] = params.get('code', [None])[0]
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write('Authentication complete. You can close this tab.'.encode())
                def log_message(self, *args):
                    pass

            # Dual-stack IPv4/IPv6 (works around Windows localhost -> ::1 issue)
            import socket as _socket
            class _DualStackServer(HTTPServer):
                address_family = _socket.AF_INET6
                def server_bind(self):
                    self.socket.setsockopt(_socket.IPPROTO_IPV6, _socket.IPV6_V6ONLY, 0)
                    super().server_bind()

            try:
                server = _DualStackServer(('::', PORT), _Handler)
            except OSError:
                # Fall back to IPv4 where IPv6 is disabled
                server = HTTPServer(('0.0.0.0', PORT), _Handler)
                flow.redirect_uri = f'http://127.0.0.1:{PORT}/'
                auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
            t = threading.Thread(target=server.handle_request)
            t.daemon = True
            t.start()

            print(f'\nOpening your browser...')
            webbrowser.open(auth_url)
            print('Sign in with your Google account (within 120 seconds)...')
            t.join(timeout=120)
            server.server_close()

            if not received.get('code'):
                print('\nAuth timed out. Please run again.')
                sys.exit(1)

            flow.fetch_token(code=received['code'])
            creds = flow.credentials

        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())

    return creds

# ──────────────────────────────────────────────
# EXIF GPS
# ──────────────────────────────────────────────
def get_exif_gps(filepath):
    """Return GPS lat/lng/altitude/heading from a JPEG's EXIF."""
    try:
        exif = piexif.load(str(filepath))
        gps = exif.get('GPS', {})
        if not gps:
            return None, None, None, None

        def dms_to_decimal(dms, ref):
            d = dms[0][0] / dms[0][1]
            m = dms[1][0] / dms[1][1]
            s = dms[2][0] / dms[2][1]
            val = d + m / 60 + s / 3600
            if ref in [b'S', b'W', 'S', 'W']:
                val = -val
            return val

        lat_key = piexif.GPSIFD.GPSLatitude
        lat_ref_key = piexif.GPSIFD.GPSLatitudeRef
        lng_key = piexif.GPSIFD.GPSLongitude
        lng_ref_key = piexif.GPSIFD.GPSLongitudeRef

        if lat_key not in gps or lng_key not in gps:
            return None, None, None, None

        lat = dms_to_decimal(gps[lat_key], gps.get(lat_ref_key, b'N'))
        lng = dms_to_decimal(gps[lng_key], gps.get(lng_ref_key, b'E'))

        alt = None
        alt_key = piexif.GPSIFD.GPSAltitude
        if alt_key in gps:
            a = gps[alt_key]
            alt = a[0] / a[1] if a[1] != 0 else 0.0

        heading = None
        hdg_key = piexif.GPSIFD.GPSImgDirection
        if hdg_key in gps:
            h = gps[hdg_key]
            heading = h[0] / h[1] if h[1] != 0 else None

        return lat, lng, alt, heading

    except Exception as e:
        return None, None, None, None

# ──────────────────────────────────────────────
# API calls
# ──────────────────────────────────────────────
def start_upload(session):
    r = session.post(f'{BASE_URL}/photo:startUpload', json={})
    if not r.ok:
        raise requests.HTTPError(
            f'[START UPLOAD] {r.status_code}: {r.text[:400]}', response=r
        )
    return r.json()['uploadUrl']

def push_bytes(session, upload_url, filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    r = session.post(
        upload_url,
        data=data,
        headers={
            'Content-Type': 'image/jpeg',
            'X-Goog-Upload-Protocol': 'raw',
            'X-Goog-Upload-Content-Length': str(len(data)),
        }
    )
    if not r.ok:
        raise requests.HTTPError(
            f'[UPLOAD BYTES] {r.status_code}: {r.text[:400]}', response=r
        )
    r.raise_for_status()

def create_photo(session, upload_url, lat, lng, alt=None, heading=None, place_id=None):
    pose = {'latLngPair': {'latitude': lat, 'longitude': lng}}
    if alt is not None:
        pose['altitude'] = alt
    if heading is not None:
        pose['heading'] = heading

    body = {
        'uploadReference': {'uploadUrl': upload_url},
        'pose': pose,
    }
    if place_id:
        body['places'] = [{'placeId': place_id}]

    r = session.post(f'{BASE_URL}/photo', json=body)
    if not r.ok:
        raise requests.HTTPError(
            f'[CREATE PHOTO] {r.status_code}: {r.text[:400]}', response=r
        )
    r.raise_for_status()
    return r.json().get('photoId', {}).get('id')

def _patch_connections(sv_service, pid, connections):
    """Set connections on a single photo (using the official client)."""
    try:
        sv_service.photo().update(
            id=pid,
            updateMask='connections',
            body={'connections': connections}
        ).execute()
        return True
    except Exception as e:
        print(f"    error: {e}")
        return False


def connect_photos(creds, photo_ids):
    """Connect each photo to its neighbors in order (simple linear route)."""
    sv_service = build_service('streetviewpublish', 'v1', credentials=creds)
    print(f"\nBuilding connections... ({len(photo_ids)} photos)")
    for i, pid in enumerate(photo_ids):
        connections = []
        if i > 0:
            connections.append({'target': {'id': photo_ids[i - 1]}})
        if i < len(photo_ids) - 1:
            connections.append({'target': {'id': photo_ids[i + 1]}})
        if not connections:
            continue
        ok = _patch_connections(sv_service, pid, connections)
        status = 'OK' if ok else 'NG'
        print(f"  [{status}] [{i+1}/{len(photo_ids)}] {pid[:24]}...")
        time.sleep(0.3)


def wait_until_ready(session, photo_ids, timeout=600, interval=15):
    """Wait until all photos go PROCESSING -> READY/PUBLISHED."""
    print(f"\nWaiting for Google to process (up to {timeout//60} min)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = session.get(
            f'{BASE_URL}/photos',
            params={'photoIds': ','.join(photo_ids), 'view': 'BASIC'}
        )
        if not r.ok:
            time.sleep(interval)
            continue
        photos = r.json().get('photos', [])
        statuses = {p.get('photoId', {}).get('id'): p.get('mapsPublishStatus', '?') for p in photos}
        pending = [pid for pid, st in statuses.items() if st != 'PUBLISHED']
        if not pending:
            print("  All photos are published")
            return True
        ready_count = len(photo_ids) - len(pending)
        print(f"  Processing... {ready_count}/{len(photo_ids)} done", end='\r')
        time.sleep(interval)
    print(f"\n  Timed out. Some photos are still processing. Re-run with --connect-only later.")
    return False


def connect_photos_from_manifest(creds, name_to_id, manifest_rows, wait=False):
    """Connect photos based on the connects_to column in the CSV manifest (branching routes)."""
    sv_service = build_service('streetviewpublish', 'v1', credentials=creds)

    print(f"\nBuilding connections (from manifest)...")
    for row in manifest_rows:
        filename = row['filename']
        connects_str = row.get('connects_to', '').strip()
        if not connects_str:
            continue

        pid = name_to_id.get(filename)
        if not pid:
            print(f"  {filename}: no uploaded ID found -> skip")
            continue

        target_names = [n.strip() for n in connects_str.split(';') if n.strip()]
        connections = []
        for tname in target_names:
            tid = name_to_id.get(tname)
            if tid:
                connections.append({'target': {'id': tid}})
            else:
                print(f"  target '{tname}' has no ID -> skip")

        if not connections:
            continue

        ok = _patch_connections(sv_service, pid, connections)
        status = 'OK' if ok else 'NG'
        labels = ', '.join(target_names)
        print(f"  [{status}] {filename} -> [{labels}]")
        time.sleep(0.3)


def sync_photo_ids(session, name_to_id):
    """Correct stored photoIds to the actual published photoIds.
    The ID returned by the create API can have extra trailing characters."""
    r = session.get(f'{BASE_URL}/photos?pageSize=50&view=BASIC')
    if not r.ok:
        print(f"  Could not fetch published IDs ({r.status_code}); using stored IDs")
        return name_to_id
    published_ids = [p['photoId']['id'] for p in r.json().get('photos', [])]

    corrected = {}
    for name, stored_id in name_to_id.items():
        # The published ID is a prefix of the stored ID
        match = next((pid for pid in published_ids if stored_id.startswith(pid)), None)
        if match:
            corrected[name] = match
        else:
            corrected[name] = stored_id
            print(f"  {name}: no matching published ID found")
    return corrected


def load_manifest(manifest_path):
    """Load tour.csv."""
    rows = []
    with open(manifest_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='Street View 360 photo tour uploader')
    parser.add_argument('--folder',       required=True, help='Folder containing the JPEGs')
    parser.add_argument('--manifest',     default=None,  help='tour.csv path (manual lat/lng/heading/connections)')
    parser.add_argument('--place-id',     default=None,  help='Google Place ID to link the tour to')
    parser.add_argument('--dry-run',      action='store_true', help='Validate only, do not upload')
    parser.add_argument('--connect-only', action='store_true', help='Re-run only the connection step from upload_result.json')
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Folder not found: {folder}")
        sys.exit(1)

    # Auto-read place_id from tour-meta.json (--place-id takes precedence)
    if not args.place_id:
        meta_path = folder / 'tour-meta.json'
        if meta_path.exists():
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)
            if meta.get('place_id'):
                args.place_id = meta['place_id']
                print(f"place_id: {args.place_id}  ({meta.get('note', '')})")

    # ── Re-run connections only ───────────────────
    if args.connect_only:
        result_file = folder / 'upload_result.json'
        if not result_file.exists():
            print(f"{result_file} not found. Run the upload first.")
            sys.exit(1)
        with open(result_file, encoding='utf-8') as f:
            result = json.load(f)
        photo_ids = result.get('photo_ids', [])
        name_to_id = result.get('name_to_id', {})
        if not photo_ids:
            print("No uploaded photoIds found.")
            sys.exit(1)
        print(f"Building connections for {len(photo_ids)} photos...")
        creds = get_credentials()
        session = requests.Session()
        session.headers.update({'Authorization': f'Bearer {creds.token}'})
        name_to_id = sync_photo_ids(session, name_to_id)
        photo_ids = list(name_to_id.values())
        manifest_rows = load_manifest(args.manifest) if args.manifest else None
        if manifest_rows:
            connect_photos_from_manifest(creds, name_to_id, manifest_rows)
        else:
            connect_photos(creds, photo_ids)
        print("Connections done")
        return

    # ──────────────────────────────────────────
    # Manifest or auto-scan
    # ──────────────────────────────────────────
    manifest_rows = None
    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.exists():
            print(f"Manifest not found: {manifest_path}")
            sys.exit(1)
        manifest_rows = load_manifest(manifest_path)
        print(f"Manifest: {manifest_path}  ({len(manifest_rows)} rows)")

        valid = []
        for row in manifest_rows:
            filename = row['filename'].strip()
            path = folder / filename
            if not path.exists():
                print(f"  {filename}: file not found -> skip")
                continue

            # lat/lng: CSV first, then EXIF
            lat_raw = row.get('lat', '').strip()
            lng_raw = row.get('lng', '').strip()
            heading_raw = row.get('heading', '').strip()

            if lat_raw and lng_raw:
                lat, lng = float(lat_raw), float(lng_raw)
                alt = None
            else:
                lat, lng, alt, _ = get_exif_gps(path)
                if lat is None:
                    print(f"  {filename}: no lat/lng in CSV or EXIF -> skip")
                    continue

            heading = float(heading_raw) if heading_raw else None

            valid.append({
                'path': path,
                'filename': filename,
                'lat': lat, 'lng': lng, 'alt': alt,
                'heading': heading,
            })
            print(f"  {filename:40s} ({lat:.6f}, {lng:.6f})"
                  + (f"  heading={heading:.0f}" if heading is not None else ""))

    else:
        # Auto-scan (EXIF GPS + file order)
        photos = sorted([p for p in folder.iterdir() if p.suffix.upper() == '.JPG'])
        if not photos:
            print(f"No JPG files found: {folder}")
            sys.exit(1)

        print(f"Folder: {folder}")
        print(f"Found {len(photos)} photos\n")

        valid = []
        for p in photos:
            lat, lng, alt, heading = get_exif_gps(p)
            if lat is not None:
                valid.append({'path': p, 'filename': p.name,
                              'lat': lat, 'lng': lng, 'alt': alt, 'heading': heading})
                print(f"  {p.name:40s} ({lat:.6f}, {lng:.6f})"
                      + (f"  heading={heading:.1f}" if heading else ""))
            else:
                print(f"  {p.name:40s} no GPS -> skip")

    print(f"\nTo upload: {len(valid)} photos")

    if not valid:
        print("No valid photos.")
        sys.exit(1)

    if args.dry_run:
        print("\n[dry-run] Stopping here. Remove --dry-run to actually upload.")
        return

    print("\nGoogle auth...")
    creds = get_credentials()
    session = requests.Session()
    session.headers.update({'Authorization': f'Bearer {creds.token}'})

    print(f"\nUploading...")
    name_to_id = {}   # filename -> photoId (used for connections)
    uploaded_ids = []

    for i, pd in enumerate(valid, 1):
        print(f"\n[{i}/{len(valid)}] {pd['filename']}")
        try:
            upload_url = start_upload(session)
            push_bytes(session, upload_url, pd['path'])
            photo_id = create_photo(
                session,
                upload_url,
                pd['lat'], pd['lng'], pd['alt'], pd['heading'],
                args.place_id,
            )
            if photo_id:
                uploaded_ids.append(photo_id)
                name_to_id[pd['filename']] = photo_id
                print(f"  photoId: {photo_id}")
            else:
                print(f"  could not get photoId")
            time.sleep(1.0)

        except requests.HTTPError as e:
            print(f"  HTTP error: {e}")
        except Exception as e:
            print(f"  error: {e}")

    # Build connections
    if len(uploaded_ids) > 1:
        if manifest_rows:
            connect_photos_from_manifest(creds, name_to_id, manifest_rows)
        else:
            connect_photos(creds, uploaded_ids)

    # Save result
    result_file = folder / 'upload_result.json'
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(
            {
                'uploaded': len(uploaded_ids),
                'place_id': args.place_id,
                'manifest': str(args.manifest) if args.manifest else None,
                'name_to_id': name_to_id,
                'photo_ids': uploaded_ids,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\nDone! Uploaded {len(uploaded_ids)} photos")
    if len(uploaded_ids) > 1:
        print(f"You can re-run connections in a few minutes with:")
        print(f"   python upload_tour.py --folder {args.folder} --connect-only")
    print(f"Result: {result_file}")
    print(f"Check: https://www.google.com/maps/contrib/")
    if args.place_id:
        print(f"Linked to Place ID: {args.place_id}")


if __name__ == '__main__':
    main()
