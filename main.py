import os
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

# ------------------- Config & Setup -------------------
load_dotenv()

API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
SESSION_SECRET = os.getenv("SESSION_SECRET", "please-change-me")
ENV_FILE = os.path.join(os.getcwd(), ".env")

if not API_KEY or not API_SECRET:
    raise RuntimeError("KITE_API_KEY and KITE_API_SECRET must be set in .env")

REDIRECT_URI = f"{APP_BASE_URL.rstrip('/')}/callback"

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
templates = Jinja2Templates(directory="templates")


def make_kite(access_token: Optional[str] = None) -> KiteConnect:
    kite = KiteConnect(api_key=API_KEY)
    if access_token:
        kite.set_access_token(access_token)
    return kite


def get_access_token_from_env() -> Optional[str]:
    return os.getenv("KITE_ACCESS_TOKEN")


def set_access_token(token: str):
    # Save to session and .env for convenience
    set_key(ENV_FILE, "KITE_ACCESS_TOKEN", token)


def get_valid_kite(request: Request) -> KiteConnect:
    """
    Dependency: returns a KiteConnect instance with a valid access token.
    Tries session first, then .env; if invalid, raises 401.
    """
    access_token = request.session.get("access_token") or get_access_token_from_env()
    if not access_token:
        raise HTTPException(status_code=401, detail="Not logged in.")

    kite = make_kite(access_token)

    # Validate token with a light call
    try:
        kite.profile()
    except KiteException:
        # Token invalid/expired
        request.session.pop("access_token", None)
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return kite


# ------------------- Routes -------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Check if we appear logged in (best-effort: presence of token)
    access_token = request.session.get("access_token") or get_access_token_from_env()
    logged_in = access_token is not None
    return templates.TemplateResponse(
        "index.html", {"request": request, "logged_in": logged_in}
    )


@app.get("/login")
def login():
    kite = make_kite()
    login_url = kite.login_url(redirect_uri=REDIRECT_URI)
    return RedirectResponse(url=login_url)


@app.get("/callback")
def callback(request: Request, request_token: str | None = None, status: str | None = None, message: str | None = None):
    if status and status != "success":
        raise HTTPException(status_code=400, detail=message or "Login failed")
    if not request_token:
        raise HTTPException(status_code=400, detail="Missing request_token.")
    ...



@app.post("/logout")
def logout(request: Request):
    request.session.pop("access_token", None)
    # Optional: also clear from .env (comment out if you prefer keeping it)
    # set_key(ENV_FILE, "KITE_ACCESS_TOKEN", "")
    return RedirectResponse(url="/")


@app.get("/api/positions")
def api_positions(kite: KiteConnect = Depends(get_valid_kite)):
    try:
        positions = kite.positions()
        return JSONResponse(positions)
    except KiteException as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/holdings")
def api_holdings(kite: KiteConnect = Depends(get_valid_kite)):
    try:
        holdings = kite.holdings()
        return JSONResponse(holdings)
    except KiteException as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/summary")
def api_summary(kite: KiteConnect = Depends(get_valid_kite)):
    try:
        profile = kite.profile()
        positions = kite.positions()
        holdings = kite.holdings()
        return JSONResponse({"profile": profile, "positions": positions, "holdings": holdings})
    except KiteException as e:
        raise HTTPException(status_code=400, detail=str(e))
