"""
Auguspay(TM) -- FastAPI entrypoint.
Run:  uvicorn app:app --reload

(c) 2026 Kuldeep Chotiya. All Rights Reserved.
Proprietary software -- see LICENSE. Unauthorized resale, sublicensing,
or commercial deployment is prohibited.
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
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import Scope

import merchant_toolkit


@asynccontextmanager
async def lifespan(_app: FastAPI):
    merchant_toolkit.init_db()
    yield


app = FastAPI(title="Auguspay Merchant Toolkit", version="1.0.0", lifespan=lifespan)

# --- compression: huge win on slow networks (typically ~70% for text)
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY")
    or os.environ.get("FLASK_SECRET_KEY", "dev-change-me"),
    same_site="lax",
    https_only=False,
)


class CachedStatic(StaticFiles):
    """StaticFiles with aggressive cache headers so repeat visits are instant
    even on 2G. The service worker also caches these locally, but a hard
    refresh / new browser benefits from this too."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            # cache 1 year; service worker handles invalidation via versioned cache name
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app.mount("/static", CachedStatic(directory="static"), name="static")
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
