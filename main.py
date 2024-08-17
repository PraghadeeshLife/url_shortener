from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel
from databases import Database
from jose import JWTError, jwt
from fastapi.responses import RedirectResponse
import os
import string
import random

# FastAPI app initialization
app = FastAPI()

# Database connection
render_url = os.getenv("RENDER_URL")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@host:port/dbname")
database = Database(DATABASE_URL)

# Supabase JWT secret key
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "your-supabase-jwt-secret")


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


@app.post("/shorten", response_class=RedirectResponse)
async def shorten_url(request: URLRequest, user_id: str = Depends(verify_token)):
    short_code = generate_short_code()

    query = "SELECT COUNT(*) FROM urls WHERE short_code = :short_code"
    while await database.fetch_val(query, {"short_code": short_code}) > 0:
        short_code = generate_short_code()

    query = "INSERT INTO urls (short_code, url, user_id) VALUES (:short_code, :url, :user_id)"
    await database.execute(query, {"short_code": short_code, "url": request.url, "user_id": user_id})

    # Redirect to the shortened URL immediately
    return RedirectResponse(url=f"{render_url}/{short_code}")


@app.get("/{short_code}")
async def redirect_url(short_code: str):
    query = "SELECT url FROM urls WHERE short_code = :short_code"
    original_url = await database.fetch_val(query, {"short_code": short_code})
    
    if original_url is None:
        raise HTTPException(status_code=404, detail="URL not found")
    
    return {"url": original_url}
