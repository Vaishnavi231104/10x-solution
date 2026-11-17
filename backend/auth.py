import logging
import os
import secrets
import bcrypt
from dotenv import load_dotenv

load_dotenv()  # make sure .env is read before SECRET_KEY is looked up
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
import models

def _load_secret_key() -> str:
    """The JWT signing secret comes from the environment only. There is no hard-coded default."""
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError("SECRET_KEY must be set when ENVIRONMENT=production")
    # Development convenience: a random per-process key. Logins reset on every restart.
    logging.getLogger("auraflow.auth").warning(
        "SECRET_KEY is not set; using a temporary random key. Set SECRET_KEY in .env to keep sessions across restarts."
    )
    return secrets.token_urlsafe(32)


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# --- NEW MODERN BCRYPT FUNCTIONS ---

def hash_password(password: str) -> str:
    """Hashes a plain text password using modern native bcrypt."""
    # Convert password string to bytes
    password_bytes = password.encode('utf-8')
    # Generate a salt and hash it
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    # Convert back to string to store cleanly in SQLite
    return hashed_bytes.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against a stored string hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

# --- KEEP THE REST OF YOUR JWT FUNCTIONS THE SAME BELOW ---

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    return user