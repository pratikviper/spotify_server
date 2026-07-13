from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from models.base import Base
from routes import auth, song
from database import engine
import storage

app = FastAPI()

# Open CORS — the mobile app (and any web tester) can call the API from anywhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Simple health check (also handy to wake a sleeping free instance).
@app.get('/')
def health():
    return {'status': 'ok'}

app.include_router(auth.router, prefix='/auth')
app.include_router(song.router, prefix='/song')

# Serve locally-stored media (audio/thumbnails). StaticFiles supports HTTP Range
# requests, so audio seeking works. Skipped when using the S3 backend.
if storage.STORAGE_BACKEND == 'local':
    storage.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    app.mount('/media', StaticFiles(directory=str(storage.MEDIA_ROOT)), name='media')

Base.metadata.create_all(engine)
