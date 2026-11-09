from datetime import date, datetime
import os
import secrets
import time
from pathlib import Path
from typing import List, Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_session, validate_database_connection
from app.models import ActivityType, FeedbackType, LibraryEntry, LibraryStatus, Media, MediaLog, MediaTag, MediaType, Tag, UserFeedback

app = FastAPI(title="Personal Media Diary and Recommendation App", docs_url=None, redoc_url=None, openapi_url=None)

SESSION_COOKIE = "media_session"
CSRF_COOKIE = "media_csrf"
SESSION_MAX_AGE = 60 * 60 * 12
password_hasher = PasswordHasher()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW = 60

def _auth_config():
    username = os.getenv("AUTH_USERNAME")
    password_hash = os.getenv("AUTH_PASSWORD_HASH")
    secret = os.getenv("AUTH_SECRET_KEY")
    if not username or not password_hash or not secret:
        return None
    if len(secret) < 32:
        raise RuntimeError("AUTH_SECRET_KEY must contain at least 32 characters")
    return username, password_hash, URLSafeTimedSerializer(secret, salt="media-session")

@app.on_event("startup")
async def validate_production_auth():
    if os.getenv("ENVIRONMENT", "development").lower() in {"production", "staging"} and not _auth_config():
        raise RuntimeError("AUTH_USERNAME, AUTH_PASSWORD_HASH, and AUTH_SECRET_KEY are required in production/staging")
    if os.getenv("ENVIRONMENT", "development").lower() in {"production", "staging"}:
        try:
            validate_database_connection()
        except Exception as exc:
            raise RuntimeError("DATABASE_URL is configured but the database connection failed") from exc

def _cookie_secure():
    return os.getenv("ENVIRONMENT", "development").lower() in {"production", "staging"}

def _session_user(request: Request):
    config = _auth_config()
    if not config: return None
    try:
        data = config[2].loads(request.cookies.get(SESSION_COOKIE, ""), max_age=SESSION_MAX_AGE)
        return data.get("sub") if data.get("sub") == config[0] else None
    except (BadSignature, SignatureExpired):
        return None

@app.middleware("http")
async def require_authentication(request: Request, call_next):
    path = request.url.path
    public = path in {"/health", "/login", "/login.css"}
    if not public and not _session_user(request):
        if path.startswith("/app") and request.method == "GET":
            return RedirectResponse("/login", status_code=307)
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and path != "/login":
        csrf = request.headers.get("X-CSRF-Token")
        if not csrf or not secrets.compare_digest(csrf, request.cookies.get(CSRF_COOKIE, "")):
            return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
    response = await call_next(request)
    return response

class LoginIn(BaseModel):
    username: str
    password: str

@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")

@app.get("/login.css", include_in_schema=False)
def login_styles():
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")

@app.post("/login", include_in_schema=False)
def login(credentials: LoginIn, request: Request):
    now = time.monotonic()
    client_key = (request.client.host if request.client else "unknown") + ":" + credentials.username
    attempts = [stamp for stamp in login_attempts.get(client_key, []) if now - stamp < LOGIN_WINDOW]
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(429, "Too many login attempts; try again later")
    config = _auth_config()
    if not config:
        raise HTTPException(503, "Authentication is not configured")
    try:
        valid = config[0] == credentials.username and password_hasher.verify(config[1], credentials.password)
    except (VerifyMismatchError, VerificationError):
        valid = False
    if not valid:
        attempts.append(now)
        login_attempts[client_key] = attempts
        raise HTTPException(401, "Invalid credentials")
    login_attempts.pop(client_key, None)
    csrf = secrets.token_urlsafe(32)
    response = JSONResponse({"ok": True})
    response.set_cookie(SESSION_COOKIE, config[2].dumps({"sub": config[0]}), max_age=SESSION_MAX_AGE,
                       httponly=True, secure=_cookie_secure(), samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=SESSION_MAX_AGE, secure=_cookie_secure(), samesite="lax", path="/")
    return response

@app.post("/logout", include_in_schema=False)
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response
class MediaIn(BaseModel):
    title: str = Field(min_length=1, max_length=255); creator: Optional[str] = Field(None, max_length=255); media_type: MediaType
    release_year: Optional[int] = Field(None, ge=1000, le=9999); description: Optional[str] = None
class MediaOut(MediaIn):
    model_config = ConfigDict(from_attributes=True); id: int
class LibraryIn(BaseModel):
    status: LibraryStatus = LibraryStatus.WANT_TO_TRY; priority: Optional[int] = Field(None, ge=0)
class TagIn(BaseModel):
    normalized_name: str = Field(min_length=1, max_length=100); category: Optional[str] = None
    @field_validator("normalized_name")
    @classmethod
    def normalized(cls, value):
        normalized = " ".join(value.split()).lower()
        if value != normalized: raise ValueError("normalized_name must be lowercase with single spaces")
        return normalized
class LogIn(BaseModel):
    activity_type: ActivityType; start_date: Optional[date] = None; finish_date: Optional[date] = None; logged_at: Optional[datetime] = None
    rating: Optional[int] = Field(None, ge=1, le=5); review: Optional[str] = None; private_notes: Optional[str] = None
    @model_validator(mode="after")
    def ordered(self):
        if self.start_date and self.finish_date and self.finish_date < self.start_date: raise ValueError("finish_date cannot be before start_date")
        return self
class LogOut(LogIn):
    model_config = ConfigDict(from_attributes=True); id: int; created_at: datetime; updated_at: datetime
class FeedbackIn(BaseModel): feedback_type: FeedbackType; notes: Optional[str] = None
class FeedbackOut(FeedbackIn):
    model_config = ConfigDict(from_attributes=True); id: int; created_at: datetime; updated_at: datetime
def media_or_404(s, mid):
    x=s.get(Media,mid)
    if not x: raise HTTPException(404,"Media not found")
    return x
def save(s):
    try: s.commit()
    except IntegrityError as e: s.rollback(); raise HTTPException(409,"Resource violates a database constraint") from e
@app.get("/health")
def health(): return {"status":"ok"}
@app.post("/media",response_model=MediaOut,status_code=201)
def create_media(d:MediaIn,s:Session=Depends(get_session)):
    duplicate=s.scalar(select(Media).where(
        Media.title==d.title.strip(),
        Media.creator==d.creator,
        Media.media_type==d.media_type,
        Media.release_year==d.release_year,
        Media.description==d.description,
    ))
    if duplicate:
        raise HTTPException(409,"An identical media record already exists")
    x=Media(**d.model_dump());s.add(x);save(s);s.refresh(x);return x
@app.get("/media",response_model=List[MediaOut])
def list_media(search:Optional[str]=None,media_type:Optional[MediaType]=None,release_year:Optional[int]=None,s:Session=Depends(get_session)):
    q=select(Media).order_by(Media.title)
    if search:q=q.where(or_(Media.title.ilike(f"%{search}%"),Media.creator.ilike(f"%{search}%"),Media.description.ilike(f"%{search}%")))
    if media_type:q=q.where(Media.media_type==media_type)
    if release_year:q=q.where(Media.release_year==release_year)
    return s.scalars(q).all()
@app.get("/library",response_model=List[MediaOut])
def list_library(search:Optional[str]=None,media_type:Optional[MediaType]=None,release_year:Optional[int]=None,status:Optional[LibraryStatus]=None,s:Session=Depends(get_session)):
    """Return only works with a library entry for the current personal library."""
    q=select(Media).join(LibraryEntry,LibraryEntry.media_id==Media.id).order_by(Media.title)
    if search:q=q.where(or_(Media.title.ilike(f"%{search}%"),Media.creator.ilike(f"%{search}%"),Media.description.ilike(f"%{search}%")))
    if media_type:q=q.where(Media.media_type==media_type)
    if release_year:q=q.where(Media.release_year==release_year)
    if status:q=q.where(LibraryEntry.status==status)
    return s.scalars(q).all()
@app.get("/media/{mid}",response_model=MediaOut)
def get_media(mid:int,s:Session=Depends(get_session)):return media_or_404(s,mid)
@app.get("/media/{mid}/deletion-summary")
def deletion_summary(mid:int,s:Session=Depends(get_session)):
    media_or_404(s,mid)
    return {"library_entries":s.scalar(select(func.count()).select_from(LibraryEntry).where(LibraryEntry.media_id==mid)),"diary_entries":s.scalar(select(func.count()).select_from(MediaLog).where(MediaLog.media_id==mid)),"tags":s.scalar(select(func.count()).select_from(MediaTag).where(MediaTag.media_id==mid)),"feedback":s.scalar(select(func.count()).select_from(UserFeedback).where(UserFeedback.media_id==mid))}
@app.patch("/media/{mid}",response_model=MediaOut)
def edit_media(mid:int,d:MediaIn,s:Session=Depends(get_session)):
    x=media_or_404(s,mid)
    for k,v in d.model_dump().items():setattr(x,k,v)
    save(s);s.refresh(x);return x
@app.delete("/media/{mid}",status_code=204)
def delete_media(mid:int,purge_related:bool=False,s:Session=Depends(get_session)):
    media_or_404(s,mid)
    summary=deletion_summary(mid,s)
    related=sum(summary.values())
    if related and not purge_related:
        raise HTTPException(409,"Media has associated records; confirm purge_related to delete the catalog record and those records")
    if purge_related:
        s.execute(delete(MediaTag).where(MediaTag.media_id==mid));s.execute(delete(UserFeedback).where(UserFeedback.media_id==mid));s.execute(delete(LibraryEntry).where(LibraryEntry.media_id==mid));s.execute(delete(MediaLog).where(MediaLog.media_id==mid))
    s.execute(delete(Media).where(Media.id==mid));s.commit()
@app.post("/media/{mid}/library",status_code=201)
def add_library(mid:int,d:LibraryIn,s:Session=Depends(get_session)):
    media_or_404(s,mid)
    # Give clients a deterministic conflict even when they are connected to a
    # database created before the unique constraint was added.
    if s.scalar(select(LibraryEntry).where(LibraryEntry.media_id==mid)):
        raise HTTPException(409,"Media is already in the library")
    x=LibraryEntry(media_id=mid,**d.model_dump());s.add(x);save(s);s.refresh(x);return x
@app.patch("/media/{mid}/library")
def edit_library(mid:int,d:LibraryIn,s:Session=Depends(get_session)):
    media_or_404(s,mid);x=s.scalar(select(LibraryEntry).where(LibraryEntry.media_id==mid))
    if not x:raise HTTPException(404,"Library entry not found")
    for k,v in d.model_dump().items():setattr(x,k,v)
    save(s);return x
@app.delete("/media/{mid}/library",status_code=204)
def remove_library(mid:int,s:Session=Depends(get_session)):
    media_or_404(s,mid);x=s.scalar(select(LibraryEntry).where(LibraryEntry.media_id==mid))
    if not x:raise HTTPException(404,"Library entry not found")
    s.delete(x);s.commit()
@app.get("/media/{mid}/library")
def get_library(mid:int,s:Session=Depends(get_session)):
    media_or_404(s,mid);x=s.scalar(select(LibraryEntry).where(LibraryEntry.media_id==mid))
    if not x:raise HTTPException(404,"Library entry not found")
    return x
@app.post("/media/{mid}/logs",response_model=LogOut,status_code=201)
def add_log(mid:int,d:LogIn,s:Session=Depends(get_session)):
    media_or_404(s,mid);x=MediaLog(media_id=mid,**d.model_dump(exclude_none=True));s.add(x);save(s);s.refresh(x);return x
@app.get("/media/{mid}/logs",response_model=List[LogOut])
def list_logs(mid:int,s:Session=Depends(get_session)):
    media_or_404(s,mid);return s.scalars(select(MediaLog).where(MediaLog.media_id==mid).order_by(MediaLog.logged_at.desc())).all()
@app.get("/media/{mid}/logs/{lid}",response_model=LogOut)
def get_log(mid:int,lid:int,s:Session=Depends(get_session)):
    media_or_404(s,mid);x=s.scalar(select(MediaLog).where(MediaLog.id==lid,MediaLog.media_id==mid))
    if not x:raise HTTPException(404,"Diary entry not found")
    return x
@app.patch("/media/{mid}/logs/{lid}",response_model=LogOut)
def edit_log(mid:int,lid:int,d:LogIn,s:Session=Depends(get_session)):
    x=get_log(mid,lid,s)
    for k,v in d.model_dump(exclude_none=True).items():setattr(x,k,v)
    save(s);s.refresh(x);return x
@app.delete("/media/{mid}/logs/{lid}",status_code=204)
def delete_log(mid:int,lid:int,s:Session=Depends(get_session)):
    x=get_log(mid,lid,s);s.delete(x);s.commit()
@app.post("/tags",status_code=201)
def create_tag(d:TagIn,s:Session=Depends(get_session)):
    x=Tag(**d.model_dump());s.add(x);save(s);s.refresh(x);return x
@app.post("/media/{mid}/tags/{tid}",status_code=201)
def attach_tag(mid:int,tid:int,strength:Optional[int]=Query(None,ge=1,le=5),s:Session=Depends(get_session)):
    media_or_404(s,mid)
    if not s.get(Tag,tid):raise HTTPException(404,"Tag not found")
    x=MediaTag(media_id=mid,tag_id=tid,strength=strength);s.add(x);save(s);return x
@app.delete("/media/{mid}/tags/{tid}",status_code=204)
def remove_tag(mid:int,tid:int,s:Session=Depends(get_session)):
    x=s.get(MediaTag,(mid,tid))
    if not x:raise HTTPException(404,"Tag attachment not found")
    s.delete(x);s.commit()
@app.post("/media/{mid}/feedback",response_model=FeedbackOut,status_code=201)
def add_feedback(mid:int,d:FeedbackIn,s:Session=Depends(get_session)):
    media_or_404(s,mid);x=UserFeedback(media_id=mid,**d.model_dump());s.add(x);save(s);s.refresh(x);return x
@app.get("/media/{mid}/feedback",response_model=List[FeedbackOut])
def list_feedback(mid:int,s:Session=Depends(get_session)):
    media_or_404(s,mid);return s.scalars(select(UserFeedback).where(UserFeedback.media_id==mid).order_by(UserFeedback.created_at.desc())).all()

# The frontend is intentionally static: the API remains the source of truth.
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
