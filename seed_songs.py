"""Bulk-populate the songs table from a free music API.

Two sources:
  itunes  (default) - any artist by name, real art, 30-second preview audio.
                      No API key.
  jamendo           - full-length Creative-Commons tracks. Needs a free
                      client id (JAMENDO_CLIENT_ID env or --client-id).
                      Get one at https://devportal.jamendo.com (1 min).

Seed by artist so specific artists' songs show up:

    # full-length, specific artists (Jamendo):
    python seed_songs.py --source jamendo --artists "Broke For Free" "Chad Crouch"

    # any famous artist, 30s previews (iTunes):
    python seed_songs.py --source itunes --artists "the weeknd" "arijit singh"

    # general fill by search term / genre:
    python seed_songs.py --source itunes --terms "pop" "bollywood"

    python seed_songs.py --clear     # wipe existing songs (and favorites) first

Run locally with .env -> Neon and the deployed app serves the songs instantly.
"""
import argparse
import html
import json
import os
import sys
import urllib.parse
import urllib.request

import config  # loads .env
from database import SessionLocal, engine
from sqlalchemy import text
from models.base import Base
from models.song import Song

PALETTE = [
    'bb3fdd', 'fb6da9', 'ff9f7c', '42c83c', '3f7bff', '00b8d4',
    'ff5252', 'ffb300', '8e24aa', '26a69a', 'ec407a', '5c6bc0',
]


def pick_hex(seed: str) -> str:
    return PALETTE[sum(ord(c) for c in seed) % len(PALETTE)]


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={'User-Agent': 'spotify-clone-seeder'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


# --- iTunes (any artist, 30s previews, no key) ---
def itunes_fetch(term: str, limit: int) -> list:
    q = urllib.parse.urlencode(
        {'term': term, 'media': 'music', 'entity': 'song', 'limit': limit}
    )
    rows = []
    for r in _get_json(f'https://itunes.apple.com/search?{q}').get('results', []):
        preview, tid = r.get('previewUrl'), r.get('trackId')
        if not preview or not tid:
            continue
        sid = f'itunes-{tid}'
        rows.append({
            'id': sid,
            'song_name': r.get('trackName') or 'Unknown',
            'artist': r.get('artistName') or 'Unknown Artist',
            'thumbnail_url': (r.get('artworkUrl100') or '').replace('100x100', '600x600'),
            'song_url': preview,
            'hex_code': pick_hex(sid),
        })
    return rows


# --- YouTube Music (full-length, ANY song incl. Bollywood; via backend proxy) ---
def youtube_fetch(query: str, limit: int, backend_url: str) -> list:
    import youtube  # lazy import (pulls in yt-dlp / ytmusicapi only when used)
    base = backend_url.rstrip('/')
    rows = []
    for s in youtube.search_songs(query, limit):
        sid = f'yt-{s["videoId"]}'
        rows.append({
            'id': sid,
            'song_name': s['title'],
            'artist': s['artist'],
            'thumbnail_url': s['thumbnail'],
            # Resolved on demand by the backend when played.
            'song_url': f'{base}/song/stream/{s["videoId"]}',
            'hex_code': pick_hex(sid),
        })
    return rows


# --- Audius (full-length, open catalog, no key) ---
_audius_host = None


def _audius_get_host() -> str:
    global _audius_host
    if _audius_host is None:
        _audius_host = _get_json('https://api.audius.co')['data'][0]
    return _audius_host


def audius_fetch(query: str, limit: int) -> list:
    host = _audius_get_host()
    q = urllib.parse.urlencode({'query': query, 'app_name': 'spotifyclone'})
    data = _get_json(f'{host}/v1/tracks/search?{q}').get('data', [])
    rows = []
    for t in data[:limit]:
        tid = t.get('id')
        if not tid or not t.get('is_streamable', True):
            continue
        art = t.get('artwork') or {}
        sid = f'audius-{tid}'
        rows.append({
            'id': sid,
            'song_name': t.get('title') or 'Unknown',
            'artist': (t.get('user') or {}).get('name') or 'Unknown Artist',
            'thumbnail_url': art.get('480x480') or art.get('1000x1000') or art.get('150x150') or '',
            'song_url': f'{host}/v1/tracks/{tid}/stream?app_name=spotifyclone',
            'hex_code': pick_hex(sid),
        })
    return rows


# --- Jamendo (full-length, Creative Commons, free key) ---
def jamendo_fetch(client_id: str, limit: int, artist=None, tag=None) -> list:
    params = {
        'client_id': client_id, 'format': 'json', 'limit': limit,
        'audioformat': 'mp32', 'order': 'popularity_total',
    }
    if artist:
        params['artist_name'] = artist
    if tag:
        # fuzzytags matches genre names loosely (plain `tags` needs exact names).
        params['fuzzytags'] = tag
    url = 'https://api.jamendo.com/v3.0/tracks/?' + urllib.parse.urlencode(params)
    rows = []
    for r in _get_json(url).get('results', []):
        audio, tid = r.get('audio'), r.get('id')
        if not audio or not tid:
            continue
        sid = f'jamendo-{tid}'
        rows.append({
            'id': sid,
            'song_name': html.unescape(r.get('name') or 'Unknown'),
            'artist': html.unescape(r.get('artist_name') or 'Unknown Artist'),
            'thumbnail_url': r.get('image') or r.get('album_image') or '',
            'song_url': audio,
            'hex_code': pick_hex(sid),
        })
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description='Seed songs by artist or term.')
    p.add_argument('--source', choices=['itunes', 'audius', 'jamendo', 'youtube'],
                   default='itunes')
    p.add_argument('--backend-url', default=os.environ.get('PUBLIC_API_URL'),
                   help='backend base URL for youtube stream proxy (or PUBLIC_API_URL)')
    p.add_argument('--artists', nargs='+', default=[], help='seed these artists')
    p.add_argument('--terms', nargs='+', default=[], help='seed these search terms / genres')
    p.add_argument('--limit', type=int, default=25, help='max tracks per artist/term')
    p.add_argument('--client-id', default=os.environ.get('JAMENDO_CLIENT_ID'),
                   help='Jamendo client id (or set JAMENDO_CLIENT_ID)')
    p.add_argument('--clear', action='store_true', help='wipe songs (and favorites) first')
    args = p.parse_args()

    if args.source == 'jamendo' and not args.client_id:
        sys.exit('ERROR: Jamendo needs a client id. Set JAMENDO_CLIENT_ID in .env '
                 'or pass --client-id. Get one free at https://devportal.jamendo.com')

    if args.source == 'youtube' and not args.backend_url:
        sys.exit('ERROR: youtube needs the backend URL for stream proxying. '
                 'Set PUBLIC_API_URL in .env or pass --backend-url https://...')

    queries = [('artist', a) for a in args.artists] + [('term', t) for t in args.terms]
    if not queries:
        sys.exit('Nothing to seed. Pass --artists "Name" ... and/or --terms "genre" ...')

    Base.metadata.create_all(engine)
    db = SessionLocal()
    added = skipped = 0
    try:
        if args.clear:
            with engine.begin() as conn:
                conn.execute(text('DELETE FROM favorites'))
                n = conn.execute(text('DELETE FROM songs')).rowcount
            print(f'Cleared {n} existing songs.')

        existing = {row[0] for row in db.query(Song.id).all()}

        for kind, value in queries:
            label = f'{kind} "{value}"'
            print(f'Fetching {label} ...', end=' ', flush=True)
            try:
                if args.source == 'jamendo':
                    rows = jamendo_fetch(
                        args.client_id, args.limit,
                        artist=value if kind == 'artist' else None,
                        tag=value if kind == 'term' else None,
                    )
                elif args.source == 'audius':
                    rows = audius_fetch(value, args.limit)
                elif args.source == 'youtube':
                    rows = youtube_fetch(value, args.limit, args.backend_url)
                else:
                    rows = itunes_fetch(value, args.limit)
            except Exception as e:
                print(f'failed: {e}')
                continue

            n = 0
            for row in rows:
                if row['id'] in existing:
                    skipped += 1
                    continue
                db.add(Song(**row))
                existing.add(row['id'])
                added += 1
                n += 1
            db.commit()
            print(f'+{n}')

        total = db.query(Song).count()
        print(f'\nDone. Added {added}, skipped {skipped} duplicates. Total in DB: {total}.')
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())
