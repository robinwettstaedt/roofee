from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.services.location.coordinates import (
    IDENTITY_MATRIX4,
    Matrix4,
    Vector3,
    bounding_sphere,
    euclidean_distance,
    lla_to_ecef,
    matmul4,
    sphere_intersects,
    to_matrix4,
)
from app.services.location.geocoding_service import DEFAULT_USER_AGENT

TILES_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class TileCandidate:
    uri: str
    geometric_error: float
    distance_m: float
    bounding_sphere_center: Vector3
    bounding_sphere_radius_m: float
    transform: Matrix4


@dataclass
class WalkContext:
    query_ecef: Vector3
    query_radius_m: float
    api_key: str
    max_depth: int
    candidates: list[TileCandidate] = field(default_factory=list)
    fetched_subtilesets: set[str] = field(default_factory=set)
    copyrights: set[str] = field(default_factory=set)


class Google3DTilesService:
    def __init__(
        self,
        api_key: str | None,
        root_url: str,
        max_radius_m: float,
        max_walk_depth: int,
        timeout_seconds: float = TILES_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._root_url = root_url
        self._max_radius_m = max_radius_m
        self._max_walk_depth = max_walk_depth
        self._timeout_seconds = timeout_seconds

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def fetch_house_glb(
        self,
        latitude: float,
        longitude: float,
        radius_m: float,
    ) -> tuple[bytes, TileCandidate, int, str | None]:
        """Return (glb_bytes, selected_tile, candidate_count, copyright)."""
        if not self._api_key:
            raise HTTPException(status_code=503, detail="Google API key is not configured.")
        if radius_m <= 0:
            raise HTTPException(status_code=422, detail="radius_m must be positive.")
        if radius_m > self._max_radius_m:
            raise HTTPException(
                status_code=422,
                detail=f"radius_m must be {self._max_radius_m:.0f} or smaller.",
            )

        context = WalkContext(
            query_ecef=lla_to_ecef(latitude, longitude),
            query_radius_m=radius_m,
            api_key=self._api_key,
            max_depth=self._max_walk_depth,
        )
        root_payload, root_session_url = self._fetch_tileset(self._with_api_key(self._root_url, context.api_key))
        copyright_text = self._extract_copyright(root_payload)
        if copyright_text:
            context.copyrights.add(copyright_text)

        root_tile = root_payload.get("root")
        if not isinstance(root_tile, dict):
            raise HTTPException(status_code=502, detail="Google 3D Tiles returned malformed data.")

        self._walk(root_tile, IDENTITY_MATRIX4, root_session_url, context, depth=0)
        if not context.candidates:
            raise HTTPException(
                status_code=404,
                detail="No 3D tiles intersected the requested radius around the anchor.",
            )

        selected_tile = self._pick_best_candidate(context.candidates)
        return (
            self._fetch_glb(selected_tile.uri),
            selected_tile,
            len(context.candidates),
            "; ".join(sorted(context.copyrights)) or None,
        )

    def _walk(
        self,
        tile: Any,
        parent_transform: Matrix4,
        base_url: str,
        context: WalkContext,
        depth: int,
    ) -> None:
        if depth > context.max_depth or not isinstance(tile, dict):
            return
        bounding_volume = tile.get("boundingVolume")
        if not isinstance(bounding_volume, dict):
            return

        local_transform = to_matrix4(tile.get("transform"))
        world_transform = matmul4(parent_transform, local_transform)
        try:
            tile_center, tile_radius = bounding_sphere(bounding_volume, world_transform)
        except ValueError:
            return

        if not sphere_intersects(
            tile_center,
            tile_radius,
            context.query_ecef,
            context.query_radius_m,
        ):
            return

        children = tile.get("children")
        if isinstance(children, list):
            for child in children:
                self._walk(child, world_transform, base_url, context, depth + 1)

        content = tile.get("content")
        if isinstance(content, dict):
            uri = content.get("uri") or content.get("url")
            if isinstance(uri, str) and uri:
                resolved = self._resolve_content_uri(base_url, uri, context.api_key)
                if self._looks_like_tileset(resolved):
                    self._descend_into_tileset(resolved, world_transform, context, depth + 1)
                else:
                    context.candidates.append(
                        TileCandidate(
                            uri=resolved,
                            geometric_error=float(tile.get("geometricError") or 0.0),
                            distance_m=euclidean_distance(context.query_ecef, tile_center),
                            bounding_sphere_center=tile_center,
                            bounding_sphere_radius_m=tile_radius,
                            transform=world_transform,
                        )
                    )

    def _descend_into_tileset(
        self,
        tileset_url: str,
        parent_transform: Matrix4,
        context: WalkContext,
        depth: int,
    ) -> None:
        if tileset_url in context.fetched_subtilesets:
            return
        context.fetched_subtilesets.add(tileset_url)

        payload, session_url = self._fetch_tileset(tileset_url)
        copyright_text = self._extract_copyright(payload)
        if copyright_text:
            context.copyrights.add(copyright_text)
        root = payload.get("root")
        if isinstance(root, dict):
            self._walk(root, parent_transform, session_url, context, depth)

    @staticmethod
    def _pick_best_candidate(candidates: list[TileCandidate]) -> TileCandidate:
        return min(
            candidates,
            key=lambda candidate: (candidate.geometric_error, candidate.distance_m, candidate.uri),
        )

    def _fetch_tileset(self, url: str) -> tuple[dict[str, Any], str]:
        response = self._http_get(url)
        try:
            payload = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Google 3D Tiles returned malformed data.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Google 3D Tiles returned malformed data.")
        return payload, str(response.url)

    def _fetch_glb(self, url: str) -> bytes:
        response = self._http_get(url)
        content = response.content
        if not content or len(content) < 12 or content[:4] != b"glTF":
            raise HTTPException(
                status_code=502,
                detail="Google 3D Tiles returned a tile that is not a valid GLB.",
            )
        return content

    def _http_get(self, url: str) -> httpx.Response:
        try:
            response = httpx.get(
                url,
                timeout=self._timeout_seconds,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail="Google 3D Tiles request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            preview = exc.response.text[:200] if exc.response.text else ""
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Google 3D Tiles returned HTTP {exc.response.status_code} for "
                    f"{_redact_key(url)}: {preview}"
                ),
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Google 3D Tiles request failed.") from exc
        return response

    def _resolve_content_uri(self, base_url: str, uri: str, api_key: str) -> str:
        absolute = urljoin(base_url, uri)
        with_session = self._inherit_session(absolute, base_url)
        return self._with_api_key(with_session, api_key)

    @staticmethod
    def _inherit_session(url: str, base_url: str) -> str:
        parsed = urlparse(url)
        existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if "session" in existing:
            return url

        base_params = dict(parse_qsl(urlparse(base_url).query, keep_blank_values=True))
        session = base_params.get("session")
        if not session:
            return url
        existing["session"] = session
        return urlunparse(parsed._replace(query=urlencode(existing)))

    @staticmethod
    def _with_api_key(url: str, api_key: str) -> str:
        parsed = urlparse(url)
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        params["key"] = api_key
        return urlunparse(parsed._replace(query=urlencode(params)))

    @staticmethod
    def _looks_like_tileset(url: str) -> bool:
        return urlparse(url).path.endswith(".json")

    @staticmethod
    def _extract_copyright(payload: dict[str, Any]) -> str | None:
        asset = payload.get("asset")
        if not isinstance(asset, dict):
            return None
        copyright_text = asset.get("copyright")
        return copyright_text if isinstance(copyright_text, str) and copyright_text else None


def get_google_3d_tiles_service() -> Google3DTilesService:
    return Google3DTilesService(
        api_key=settings.google_api_key or settings.google_maps_api_key,
        root_url=settings.google_3d_tiles_root_url,
        max_radius_m=settings.google_3d_tiles_max_radius_m,
        max_walk_depth=settings.google_3d_tiles_max_walk_depth,
        timeout_seconds=settings.google_timeout_seconds,
    )


def _redact_key(url: str) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "key" in params:
        params["key"] = "REDACTED"
    return urlunparse(parsed._replace(query=urlencode(params)))
