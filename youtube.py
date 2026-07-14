"""YouTube Music provider: search (ytmusicapi) + on-demand audio stream
resolution (yt-dlp). This is how full-length mainstream songs (incl. Hindi/
Bollywood) are played for free — the same approach ViMusic/ViTune use.

NOTE: this relies on YouTube's private endpoints. Stream URLs are temporary and
must be resolved on demand (never stored). See DEPLOY notes for the caveats.
"""
import threading
import time

import yt_dlp
from ytmusicapi import YTMusic

# --- YouTube Music search ---
_yt = None
_yt_lock = threading.Lock()


def _ytmusic() -> YTMusic:
    global _yt
    if _yt is None:
        with _yt_lock:
            if _yt is None:
                _yt = YTMusic()
    return _yt


def search_songs(query: str, limit: int = 20) -> list:
    """Search YT Music for songs. Returns [{videoId, title, artist, thumbnail}]."""
    results = _ytmusic().search(query, filter='songs', limit=limit)
    out = []
    for r in results:
        vid = r.get('videoId')
        if not vid:
            continue
        thumbs = r.get('thumbnails') or []
        out.append({
            'videoId': vid,
            'title': r.get('title') or 'Unknown',
            'artist': ', '.join(a['name'] for a in (r.get('artists') or []))
                      or 'Unknown Artist',
            'thumbnail': thumbs[-1]['url'] if thumbs else '',
            'duration': r.get('duration'),
        })
    return out


# --- Stream resolution (yt-dlp) ---
# Resolved googlevideo URLs expire (~6h) and must not be persisted; cache them
# in-memory for a while so seeking / repeated plays don't re-resolve every time.
_STREAM_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 5 * 3600  # seconds
_resolve_lock = threading.Lock()

# 'android'/'ios' clients hand back IP-agnostic URLs (playable from the user's
# device even though our server resolved them) and dodge the web bot-check.
_YDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'format': 'bestaudio/best',
    'noplaylist': True,
    'skip_download': True,
    'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
}


def resolve_stream_url(video_id: str) -> str:
    """Return a currently-playable audio URL for a YouTube video id."""
    now = time.time()
    cached = _STREAM_CACHE.get(video_id)
    if cached and cached[1] > now:
        return cached[0]

    with _resolve_lock:
        cached = _STREAM_CACHE.get(video_id)
        if cached and cached[1] > now:
            return cached[0]
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(
                f'https://music.youtube.com/watch?v={video_id}', download=False
            )
        url = info['url']
        _STREAM_CACHE[video_id] = (url, now + _CACHE_TTL)
        return url
