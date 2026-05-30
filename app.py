"""
Auguspay -- FastAPI entrypoint.
Run:  uvicorn app:app --reload
"""

import os
from contextlib import asynccontextmanager

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import merchant_toolkit


@asynccontextmanager
async def lifespan(_app: FastAPI):
    merchant_toolkit.init_db()
    yield


app = FastAPI(title="Auguspay Merchant Toolkit", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY")
    or os.environ.get("FLASK_SECRET_KEY", "dev-change-me"),
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(merchant_toolkit.router)



@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/merchant/")


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        reload=os.environ.get("RELOAD", "1") == "1",
    )

