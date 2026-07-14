from pydantic import BaseModel


class GoogleLogin(BaseModel):
    token: str  # Google ID token from the app
