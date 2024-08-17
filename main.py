from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict
import random
import string

app = FastAPI()

# In-memory database to store URLs
url_db: Dict[str, str] = {}

class URLRequest(BaseModel):
    url: str

def generate_short_code(length: int = 6) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.post("/shorten")
def shorten_url(request: URLRequest):
    short_code = generate_short_code()
    while short_code in url_db:
        short_code = generate_short_code()
    url_db[short_code] = request.url
    return {"short_url": f"https://yourdomain.com/{short_code}"}

@app.get("/{short_code}")
def redirect_url(short_code: str):
    if short_code not in url_db:
        raise HTTPException(status_code=404, detail="URL not found")
    return {"url": url_db[short_code]}
