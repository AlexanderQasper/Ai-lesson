import os
import secrets
import hashlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from authlib.integrations.starlette_client import OAuth
from redis import Redis
import psycopg
from psycopg.rows import dict_row

BASE_URL = os.environ.get("APP_URL", "https://projector-school.info").rstrip("/")
COOKIE = "__Host-lesson_session"
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
def db():
    return psycopg.connect(host="postgres", dbname="lessonai", user="lessonai", password=os.environ["POSTGRES_PASSWORD"], connect_timeout=3, row_factory=dict_row)
def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()
def configured():
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))

@asynccontextmanager
async def lifespan(app):
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY, google_sub TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL, name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            csrf TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at)")
    from app.uploads import initialize
    initialize()
    from app.trimming import initialize as initialize_trimming
    initialize_trimming()
    from app.teacher import initialize as initialize_teacher
    initialize_teacher()
    yield

app = FastAPI(title="Lesson AI", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET"], session_cookie="__Host-lesson_oauth", https_only=True, same_site="lax", max_age=600)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["projector-school.info", "127.0.0.1", "localhost", "testserver"])
oauth = OAuth()
oauth.register(name="google", client_id=os.environ.get("GOOGLE_CLIENT_ID", ""), client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""), server_metadata_url="https://accounts.google.com/.well-known/openid-configuration", client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"})

@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response

def current_user(request):
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 256: return None
    with db() as conn:
        return conn.execute("SELECT u.id,u.email,u.name,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>now()", (digest(token),)).fetchone()

def page(request, view, **values):
    return templates.TemplateResponse(request=request, name="site.html", context={"view":view, "user":values.pop("user",None), "ready":configured(), **values})

@app.get("/healthz")
def health():
    try:
        Redis.from_url(os.environ["REDIS_URL"], socket_timeout=3).ping()
        with db() as conn: conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="Dependency unavailable")
    return {"status":"ok", "analysis":"not configured"}

@app.get("/")
def index(request: Request):
    return page(request,"home",user=current_user(request))

@app.get("/login")
def login(request: Request):
    if current_user(request): return RedirectResponse("/account",303)
    return page(request,"login",error=request.query_params.get("error"))

@app.get("/auth/google")
async def google_login(request: Request):
    if not configured(): return RedirectResponse("/login?error=setup",303)
    request.session.clear()
    try:
        return await oauth.google.authorize_redirect(request, BASE_URL+"/auth/google/callback", prompt="select_account")
    except Exception:
        logger.warning("Google authorization initiation failed")
        return RedirectResponse("/login?error=oauth",303)

@app.get("/auth/google/callback")
async def google_callback(request: Request):
    if not configured(): return RedirectResponse("/login?error=setup",303)
    try:
        token = await oauth.google.authorize_access_token(request)
        info = token.get("userinfo")
        if not info or not info.get("sub") or not info.get("email") or info.get("email_verified") is not True:
            raise ValueError("Unverified identity")
    except Exception:
        request.session.clear()
        logger.warning("Google identity validation failed")
        return RedirectResponse("/login?error=oauth",303)
    request.session.clear()
    session = secrets.token_urlsafe(32)
    with db() as conn:
        user = conn.execute("INSERT INTO users(google_sub,email,name) VALUES(%s,%s,%s) ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email,name=excluded.name RETURNING id", (info["sub"],info["email"],info.get("name") or info["email"])).fetchone()
        old = request.cookies.get(COOKIE)
        if old: conn.execute("DELETE FROM sessions WHERE token_hash=%s",(digest(old),))
        conn.execute("DELETE FROM sessions WHERE expires_at<=now()")
        conn.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(%s,%s,%s,now()+interval '7 days')",(digest(session),user["id"],secrets.token_urlsafe(32)))
    response=RedirectResponse("/account",303)
    response.set_cookie(COOKIE,session,max_age=604800,secure=True,httponly=True,samesite="lax",path="/")
    return response

@app.get("/account")
def account(request: Request):
    user=current_user(request)
    if not user: return RedirectResponse("/login",303)
    from app.uploads import account_page
    return account_page(request,user)

@app.post("/logout")
def logout(request: Request, csrf: str = Form(...)):
    user=current_user(request)
    if not user or not secrets.compare_digest(user["csrf"],csrf):
        raise HTTPException(403,"Invalid request")
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=%s",(digest(request.cookies[COOKIE]),))
    request.session.clear()
    response=RedirectResponse("/",303)
    response.delete_cookie(COOKIE,path="/",secure=True,httponly=True,samesite="lax")
    return response

from app.uploads import install
install(app)

from app.trimming import install as install_trimming
install_trimming(app)

from fastapi.staticfiles import StaticFiles
app.mount("/assets/editor",StaticFiles(directory=str(Path(__file__).parent / "assets")),name="editor-assets")

from fastapi.staticfiles import StaticFiles

from app.assistant import install as install_assistant
install_assistant(app)
from app.teacher import install as install_teacher
install_teacher(app)

