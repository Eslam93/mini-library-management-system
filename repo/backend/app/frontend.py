"""Serves the built single-page web app from the same origin as the API."""

from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

# Bundled assets have content hashes in their names, so they never change in place.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
# index.html names the current asset files, so browsers must revalidate it.
REVALIDATE_CACHE = "no-cache"


class ImmutableStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = IMMUTABLE_CACHE
        return response


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class SpaFallback:
    """Answers requests that match no route.

    GET and HEAD requests outside /api get a file from the build folder, or index.html so the
    client-side router can handle the path. Anything else goes to the router's usual 404.
    """

    def __init__(self, dist_dir: Path, not_found: ASGIApp) -> None:
        self.root = dist_dir.resolve()
        self.index = self.root / "index.html"
        self.not_found = not_found

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in {"GET", "HEAD"}
            or _is_api_path(scope["path"])
        ):
            await self.not_found(scope, receive, send)
            return

        response = FileResponse(self._file_for(scope["path"]))
        response.headers["Cache-Control"] = REVALIDATE_CACHE
        await response(scope, receive, send)

    def _file_for(self, path: str) -> Path:
        candidate = (self.root / path.lstrip("/")).resolve()
        if candidate.is_relative_to(self.root) and candidate.is_file():
            return candidate
        return self.index


async def _frontend_not_built() -> dict[str, str]:
    return {
        "message": "The web app is not built, so only the API is served. "
        "Build the frontend to serve it from this address.",
        "api": "/api",
    }


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serves the build in dist_dir, or a short JSON note at / when there is no build."""
    if not (dist_dir / "index.html").is_file():
        app.add_api_route("/", _frontend_not_built, include_in_schema=False)
        return

    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", ImmutableStaticFiles(directory=assets_dir), name="assets")
    app.router.default = SpaFallback(dist_dir, not_found=app.router.default)
