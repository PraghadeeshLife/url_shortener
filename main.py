from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from databases import Database
import os
import string
import random

# Initialize FastAPI app
app = FastAPI()

# Database connection string
render_url = os.getenv("RENDER_URL")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@host:port/dbname")

# Initialize the database
database = Database(DATABASE_URL)

# Pydantic models
class URLRequest(BaseModel):
    url: str

# Utility function to generate a short code
def generate_short_code(length: int = 6) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.post("/shorten")
async def shorten_url(request: URLRequest):
    short_code = generate_short_code()
    
    # Check for uniqueness
    query = "SELECT COUNT(*) FROM urls WHERE short_code = :short_code"
    while await database.fetch_val(query, {"short_code": short_code}) > 0:
        short_code = generate_short_code()
    
    # Insert into the database
    query = "INSERT INTO urls (short_code, url) VALUES (:short_code, :url)"
    await database.execute(query, {"short_code": short_code, "url": request.url})
    
    return {"short_url": f"{render_url}/{short_code}"}

@app.get("/{short_code}")
async def redirect_url(short_code: str):
    query = "SELECT url FROM urls WHERE short_code = :short_code"
    original_url = await database.fetch_val(query, {"short_code": short_code})
    
    if original_url is None:
        raise HTTPException(status_code=404, detail="URL not found")
    
    return {"url": original_url}
