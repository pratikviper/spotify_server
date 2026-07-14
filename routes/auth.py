import uuid
import bcrypt
from fastapi import Depends, HTTPException, Header
from database import get_db
from middleware.auth_middleware import auth_middleware
from models.user import User
from pydantic_schemas.user_create import UserCreate
from fastapi import APIRouter
from sqlalchemy.orm import Session
from pydantic_schemas.user_login import UserLogin
from pydantic_schemas.google_login import GoogleLogin
import jwt
from config import JWT_SECRET, GOOGLE_CLIENT_IDS
from sqlalchemy.orm import joinedload
router = APIRouter()


def _verify_google_token(token: str) -> dict:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests

    # Verifies signature + expiry + issuer. Audience is checked manually below so
    # we can accept tokens from the web / android / ios client IDs.
    info = google_id_token.verify_oauth2_token(token, google_requests.Request())
    if info.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        raise ValueError('Wrong issuer')
    if GOOGLE_CLIENT_IDS and info.get('aud') not in GOOGLE_CLIENT_IDS:
        raise ValueError('Token audience is not an allowed client id')
    return info

@router.post('/signup', status_code=201)
def signup_user(user: UserCreate, db: Session=Depends(get_db)):
    # check if the user already exists in db
    user_db = db.query(User).filter(User.email == user.email).first()

    if user_db:
        raise HTTPException(400, 'User with the same email already exists!')
    
    hashed_pw = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())
    user_db = User(id=str(uuid.uuid4()), email=user.email, password=hashed_pw, name=user.name)
    
    # add the user to the db
    db.add(user_db)
    db.commit()
    db.refresh(user_db)

    return user_db

@router.post('/login')
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    # check if a user with same email already exist
    user_db = db.query(User).filter(User.email == user.email).first()

    if not user_db:
        raise HTTPException(400, 'User with this email does not exist!')
    
    # password matching or not
    is_match = bcrypt.checkpw(user.password.encode(), user_db.password)
    
    if not is_match:
        raise HTTPException(400, 'Incorrect password!')
    

    token = jwt.encode({'id': user_db.id}, JWT_SECRET)

    return {'token': token, 'user': user_db}

@router.post('/google')
def google_login(body: GoogleLogin, db: Session = Depends(get_db)):
    # Verify the Google ID token.
    try:
        info = _verify_google_token(body.token)
    except Exception as e:
        raise HTTPException(401, f'Invalid Google token: {e}')

    email = info.get('email')
    if not email:
        raise HTTPException(400, 'Google account has no email')
    name = info.get('name') or email.split('@')[0]

    # Find or create the user (Google users have no password).
    user_db = db.query(User).filter(User.email == email).first()
    if not user_db:
        user_db = User(id=str(uuid.uuid4()), email=email, name=name, password=None)
        db.add(user_db)
        db.commit()
        db.refresh(user_db)

    token = jwt.encode({'id': user_db.id}, JWT_SECRET)
    return {'token': token, 'user': user_db}

@router.get('/')
def current_user_data(db: Session=Depends(get_db), 
                      user_dict = Depends(auth_middleware)):
    user = db.query(User).filter(User.id == user_dict['uid']).options(
        joinedload(User.favorites)
    ).first()

    if not user:
        raise HTTPException(404, 'User not found!')
    
    return user