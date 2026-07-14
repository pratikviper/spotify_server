import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from middleware.auth_middleware import auth_middleware
from models.favorite import Favorite
from models.song import Song
from pydantic_schemas.favorite_song import FavoriteSong
from sqlalchemy.orm import joinedload
import storage

router = APIRouter()


@router.get('/stream/{video_id}')
def stream_song(video_id: str):
    """Resolve a fresh YouTube audio URL and redirect the player to it.

    Songs seeded from YouTube store their song_url as this endpoint, so the app
    plays it like any other URL; we resolve on demand (URLs are temporary).
    No auth: the audio player fetches this URL directly without headers.
    """
    import youtube
    try:
        url = youtube.resolve_stream_url(video_id)
    except Exception as e:
        raise HTTPException(502, f'Could not resolve stream: {e}')
    return RedirectResponse(url)

@router.post('/upload', status_code=201)
def upload_song(request: Request,
                song: UploadFile = File(...),
                thumbnail: UploadFile = File(...),
                artist: str = Form(...),
                song_name: str = Form(...),
                hex_code: str = Form(...),
                db: Session = Depends(get_db),
                auth_dict = Depends(auth_middleware)):
    song_id = str(uuid.uuid4())
    base_url = str(request.base_url)

    song_ext = storage.guess_ext(song.filename, '.mp3')
    thumb_ext = storage.guess_ext(thumbnail.filename, '.jpg')

    # Store audio + thumbnail via the configured backend (local disk or S3).
    song_url = storage.save(
        song.file,
        f'songs/{song_id}/song{song_ext}',
        request_base_url=base_url,
        content_type=song.content_type,
        resource_type='auto',
    )
    thumbnail_url = storage.save(
        thumbnail.file,
        f'songs/{song_id}/thumbnail{thumb_ext}',
        request_base_url=base_url,
        content_type=thumbnail.content_type,
        resource_type='image',
    )

    new_song = Song(
        id=song_id,
        song_name=song_name,
        artist=artist,
        hex_code=hex_code,
        song_url=song_url,
        thumbnail_url=thumbnail_url,
    )

    db.add(new_song)
    db.commit()
    db.refresh(new_song)
    return new_song

@router.get('/list')
def list_songs(db: Session=Depends(get_db), 
               auth_details=Depends(auth_middleware)):
    songs = db.query(Song).all()
    return songs

@router.post('/favorite')
def favorite_song(song: FavoriteSong, 
                  db: Session=Depends(get_db), 
                  auth_details=Depends(auth_middleware)):
    # song is already favorited by the user
    user_id = auth_details['uid']

    fav_song = db.query(Favorite).filter(Favorite.song_id == song.song_id, Favorite.user_id == user_id).first()

    if fav_song:
        db.delete(fav_song)
        db.commit()
        return {'message': False}
    else:
        new_fav = Favorite(id=str(uuid.uuid4()), song_id=song.song_id, user_id=user_id)
        db.add(new_fav)
        db.commit()
        return {'message': True}
    
@router.get('/list/favorites')
def list_fav_songs(db: Session=Depends(get_db), 
               auth_details=Depends(auth_middleware)):
    user_id = auth_details['uid']
    fav_songs = db.query(Favorite).filter(Favorite.user_id == user_id).options(
        joinedload(Favorite.song),
    ).all()
    
    return fav_songs