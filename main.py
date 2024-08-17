from fastapi import FastAPI, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from databases import Database
from jose import JWTError, jwt
from fastapi.responses import RedirectResponse
from user_agents import parse
import os
import string
import random
import requests


# FastAPI app initialization
app = FastAPI()

# Database connection
render_url = os.getenv("RENDER_URL")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@host:port/dbname")
database = Database(DATABASE_URL)

# Supabase JWT secret key
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "your-supabase-jwt-secret")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN", "your_ipinfo_token")


# Pydantic models
class URLRequest(BaseModel):
    url: str


# Helper function to generate short codes
def generate_short_code(length: int = 6) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


# JWT token verification
async def verify_token(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"verify_aud": False})
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid user credentials")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.on_event("startup")
async def startup():
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


@app.post("/url/shorten")
async def shorten_url(request: URLRequest, user_id: str = Depends(verify_token)):   
    print("Short URL")
    short_code = generate_short_code()

    query = "INSERT INTO urls (short_code, url, user_id) VALUES (:short_code, :url, :user_id)"
    await database.execute(query, {"short_code": short_code, "url": request.url, "user_id": user_id})

    print("Shortened URL is inserted")

    # Redirect to the shortened URL immediately
    return {"short_url": f"{render_url}/{short_code}"}



async def fetch_ipinfo(ip_address: str):
    # Request geolocation data from ipinfo
    response = requests.get(f"https://ipinfo.io/{ip_address}/json?token={IPINFO_TOKEN}")
    if response.status_code == 200:
        data = response.json()
        return {
            "ip": data.get("ip"),
            "city": data.get("city"),
            "region": data.get("region"),
            "country": data.get("country"),
            "loc": data.get("loc"),
            "org": data.get("org"),
            "postal": data.get("postal"),
            "timezone": data.get("timezone")
        }
    return {}



@app.get("/{short_code}")
async def redirect_url(short_code: str, request: Request):
    # Fetch the original URL from the database
    query = "SELECT id, url, click_count FROM urls WHERE short_code = :short_code"
    result = await database.fetch_one(query, {"short_code": short_code})
    
    if result is None:
        raise HTTPException(status_code=404, detail="URL not found")

    # Extract information for analytics
    url_id = result['id']
    original_url = result['url']
    click_count = result['click_count'] + 1
    ip_address = request.client.host

    # Fetch IP info
    ip_info = await fetch_ipinfo(ip_address)

    # Parse user-agent to get browser and device info
    user_agent_string = request.headers.get("user-agent")
    user_agent = parse(user_agent_string)

    browser = user_agent.browser.family
    browser_version = user_agent.browser.version_string
    os = user_agent.os.family
    os_version = user_agent.os.version_string
    device = user_agent.device.family

    # Increment click count and update last accessed timestamp
    update_query = """
    UPDATE urls 
    SET click_count = :click_count, last_accessed = NOW() 
    WHERE id = :url_id
    """
    await database.execute(update_query, {"click_count": click_count, "url_id": url_id})

    # Log the access to the url_analytics table
    analytics_query = """
    INSERT INTO url_analytics (
        url_id, ip_address, city, region, country, org, loc, postal, timezone,
        browser, browser_version, os, os_version, device
    ) 
    VALUES (
        :url_id, :ip_address, :city, :region, :country, :org, :loc, :postal, :timezone,
        :browser, :browser_version, :os, :os_version, :device
    )
    """
    await database.execute(analytics_query, {
        "url_id": url_id,
        "ip_address": ip_info.get("ip"),
        "city": ip_info.get("city"),
        "region": ip_info.get("region"),
        "country": ip_info.get("country"),
        "org": ip_info.get("org"),
        "loc": ip_info.get("loc"),
        "postal": ip_info.get("postal"),
        "timezone": ip_info.get("timezone"),
        "browser": browser,
        "browser_version": browser_version,
        "os": os,
        "os_version": os_version,
        "device": device
    })

    # Redirect to the original URL
    return RedirectResponse(url=original_url)