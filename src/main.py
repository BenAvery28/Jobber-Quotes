#
#
#
#   flask application and the main webhook endpoint to kick off the workflow

import os, time, secrets
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
import httpx
from src.api.weather import check_weather
from datetime import datetime

AUTH_URL = "https://api.getjobber.com/api/oauth/authorize"
TOKEN_URL = "https://api.getjobber.com/api/oauth/token"
GQL_URL   = "https://api.getjobber.com/api/graphql"

CLIENT_ID = os.getenv("JOBBER_CLIENT_ID")
CLIENT_SECRET = os.getenv("JOBBER_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

app = FastAPI()
STATE = {"value": None}
TOKENS = {}

@app.get("/auth")
async def start_auth():
    STATE["value"] = secrets.token_urlsafe(24)
    url = httpx.URL(
        AUTH_URL,
        params={
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "state": STATE["value"],
        },
    )
    return RedirectResponse(str(url))

@app.get("/oauth/callback")
async def oauth_callback(code: str = "", state: str = ""):
    if not STATE["value"] or state != STATE["value"]:
        raise HTTPException(status_code=400, detail="Invalid state")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    TOKENS.update(r.json() | {"obtained_at": int(time.time())})
    return JSONResponse({"ok": True})

@app.get("/whoami")
async def whoami():
    access = TOKENS.get("access_token")
    if not access:
        raise HTTPException(status_code=401, detail="Not authorized")
    query = """query { viewer { account { id name } } }"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            GQL_URL,
            json={"query": query},
            headers={"Authorization": f"Bearer {access}"},
        )
    return JSONResponse(r.json())
