import os
import json
import logging
from datetime import date, datetime
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

try:
    from kiteconnect import KiteConnect
except Exception as e:
    KiteConnect = None
    _kite_import_error = e
else:
    _kite_import_error = None

logging.basicConfig(level=logging.INFO)
load_dotenv()

app = FastAPI(title="Kite FastAPI Service", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(SessionMiddleware, secret_key=os.urandom(24))

def serializer(obj):
    if isinstance(obj, (date, datetime, Decimal)):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

kite_api_key = os.getenv("KITE_API_KEY", "kite_api_key")
kite_api_secret = os.getenv("KITE_API_SECRET", "kite_api_secret")

login_url = f"https://kite.zerodha.com/connect/login?api_key={kite_api_key}"
console_url = f"https://developers.kite.trade/apps/{kite_api_key}"

def get_prefix(request: Request) -> str:
    """
    Prefer proxy-provided prefix; fallback to env (optional).
    Result never ends with a trailing slash.
    """
    p = request.headers.get("x-forwarded-prefix") or os.getenv("PUBLIC_PREFIX", "")
    return p.rstrip("/")

def page_index(prefix: str) -> str:
    # base makes *relative* links resolve under /py/ automatically
    return f"""
    <head><base href="{prefix + '/' if prefix else '/'}"></head>
    <div>Make sure your app with api_key - <b>{kite_api_key}</b> has redirect to <b>{prefix}/login</b>.</div>
    <div>If not, set it from your <a href="{console_url}">Kite Connect developer console</a>.</div>
    <a href="{login_url}"><h1>Login to generate access token.</h1></a>"""

def page_login_success(access_token: str, user_data: dict, prefix: str) -> str:
    return f"""
    <head><base href="{prefix + '/' if prefix else '/'}"></head>
    <h2 style="color: green">Success</h2>
    <div>Access token: <b>{access_token}</b></div>
    <h4>User login data</h4>
    <pre>{json.dumps(user_data, indent=4, sort_keys=True, default=serializer)}</pre>
    <a target="_blank" href="holdings.json"><h4>Fetch user holdings</h4></a>
    <a target="_blank" href="orders.json"><h4>Fetch user orders</h4></a>
    <a target="_blank" href="positions.json"><h4>Fetch user positions</h4></a>
    <a target="_blank" href="https://kite.trade/docs/connect/v1/"><h4>Check Kite Connect docs</h4></a>"""

def need_kite():
    if _kite_import_error:
        raise RuntimeError(f"kiteconnect is not installed: {_kite_import_error}")
    return KiteConnect(api_key=kite_api_key)

def get_kite_client(request: Request):
    kite = need_kite()
    if "access_token" in request.session:
        kite.set_access_token(request.session["access_token"])
    return kite

@app.get("/health")
async def health():
    return {"status": "healthy", "kite_import_ok": _kite_import_error is None}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    prefix = get_prefix(request)
    return page_index(prefix)

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    prefix = get_prefix(request)
    request_token = request.query_params.get("request_token")
    if not request_token:
        # relative link so it stays under /py/
        return "<span style='color:red'>Error while generating request token.</span> <a href='./'>Try again.</a>"

    kite = get_kite_client(request)
    data = kite.generate_session(request_token, api_secret=kite_api_secret)
    request.session["access_token"] = data["access_token"]

    try:
        with open(".env", "a") as env_file:
            env_file.write(f"ACCESS_TOKEN={data['access_token']}\n")
    except Exception as e:
        logging.warning("Couldn't append ACCESS_TOKEN to .env: %s", e)

    return page_login_success(data["access_token"], data, prefix)

@app.get("/holdings.json")
async def holdings(request: Request):
    kite = get_kite_client(request)
    return JSONResponse({"holdings": kite.holdings()})

@app.get("/orders.json")
async def orders(request: Request):
    kite = get_kite_client(request)
    return JSONResponse({"orders": kite.orders()})

@app.get("/positions.json")
async def positions(request: Request):
    kite = get_kite_client(request)
    return JSONResponse({"positions": kite.positions()})
