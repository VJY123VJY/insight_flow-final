from fastapi import FastAPI, HTTPException, status
from app.auth import create_access_token
from app.core.config import settings
from app.api import enforce
import logging

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app = FastAPI(
    title=settings.APP_NAME,
    description="Sovereign Enforcement Agent - Wired into BHIV Stack",
    version="1.0.0"
)

# Dummy user (replace with DB later)
fake_user = {
    "username": "admin",
    "password": "admin123",
    "role": "admin"
}

# Routes
app.include_router(enforce.router, tags=["Enforcement"])


@app.post("/login")
def login(username: str, password: str):
    if (
        username != fake_user["username"]
        or password != fake_user["password"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token = create_access_token({
        "sub": username,
        "role": fake_user["role"]
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
