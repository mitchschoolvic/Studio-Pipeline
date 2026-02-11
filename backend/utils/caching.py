import hashlib
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from typing import Any, Iterable

def make_signature(*parts: Iterable[Any]) -> str:
    """Generate an ETag signature from multiple parts."""
    m = hashlib.sha256()
    for p in parts:
        m.update(str(p).encode("utf-8"))
        m.update(b"|")
    return f'W/"{m.hexdigest()[:32]}"'

def maybe_304(request: Request, etag: str) -> Response | None:
    """Return a 304 Not Modified response if the ETag matches."""
    inm = request.headers.get("if-none-match")
    if inm and inm == etag:
        return Response(status_code=304, headers={
            "ETag": etag,
            "Cache-Control": "public, max-age=60, stale-while-revalidate=120"
        })
    return None

def cache_headers(etag: str) -> dict[str, str]:
    """Return standard cache headers with ETag."""
    return {
        "ETag": etag,
        "Cache-Control": "public, max-age=60, stale-while-revalidate=120"
    }
