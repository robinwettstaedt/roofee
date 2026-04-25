from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import HTTPException

from app.models.roof import (
    RegistrationQualityMetrics,
    RoofRegistrationRequest,
    RoofRegistrationResponse,
    SelectedRoof,
    SimilarityTransform,
)
from app.services.house_data_service import HouseDataService
from app.services.roof.building_outline_service import BuildingOutlineUnavailableError
from app.services.roof.roof_analysis_service import RoofAnalysisService, get_roof_analysis_service


class RoofRegistrationService:
    def __init__(
        self,
        roof_analysis_service: RoofAnalysisService,
        *,
        min_good_matches: int = 8,
        min_inliers: int = 6,
        max_reprojection_error_pixels: float = 8.0,
        min_scale: float = 0.05,
        max_scale: float = 20.0,
    ) -> None:
        self.roof_analysis_service = roof_analysis_service
        self.min_good_matches = min_good_matches
        self.min_inliers = min_inliers
        self.max_reprojection_error_pixels = max_reprojection_error_pixels
        self.min_scale = min_scale
        self.max_scale = max_scale

    def register_roof(
        self,
        request: RoofRegistrationRequest,
        top_down_render_png: bytes,
        house_data_service: HouseDataService,
    ) -> RoofRegistrationResponse:
        selection = self.roof_analysis_service.select_roof(request, house_data_service)
        asset_id = self.roof_analysis_service.asset_id_from_overhead_url(request.satellite_image_url)
        if asset_id is None:
            raise HTTPException(status_code=400, detail="Invalid satellite image URL.")

        satellite_image = self._load_color_image(house_data_service.overhead_image_path(asset_id))
        top_down_render = self._decode_uploaded_png(top_down_render_png)
        self._validate_render_dimensions(top_down_render, request)

        attempts = [
            self._estimate_similarity_transform(satellite_image, top_down_render, "orb"),
        ]
        if not attempts[0].has_enough_matches or not attempts[0].accepted:
            attempts.append(self._estimate_similarity_transform(satellite_image, top_down_render, "akaze"))

        best_attempt = self._best_attempt(attempts)
        warnings = self._warnings_for_attempts(attempts)
        quality = best_attempt.quality

        if best_attempt.accepted and best_attempt.transform is not None:
            polygon = self._selected_polygon(selection.selected_roof)
            mapped_polygon = self._map_polygon(polygon, best_attempt.transform.matrix)
            return RoofRegistrationResponse(
                status="registered",
                selected_roof=selection.selected_roof,
                transform=best_attempt.transform,
                mapped_roof_polygon_pixels=mapped_polygon,
                render_metadata=request.top_down_render_metadata,
                quality=quality,
                warnings=warnings,
            )

        self._add_render_outline_diagnostics(
            top_down_render=top_down_render,
            quality=quality,
            warnings=warnings,
        )
        return RoofRegistrationResponse(
            status="failed",
            selected_roof=selection.selected_roof,
            transform=None,
            mapped_roof_polygon_pixels=[],
            render_metadata=request.top_down_render_metadata,
            quality=quality,
            warnings=warnings or ["Image registration did not find a reliable similarity transform."],
        )

    def _estimate_similarity_transform(
        self,
        satellite_image: np.ndarray,
        render_image: np.ndarray,
        algorithm: str,
    ) -> "_RegistrationAttempt":
        satellite_gray = cv2.cvtColor(satellite_image, cv2.COLOR_BGR2GRAY)
        render_gray = cv2.cvtColor(render_image, cv2.COLOR_BGR2GRAY)

        if algorithm == "orb":
            detector = cv2.ORB_create(nfeatures=3000)
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        elif algorithm == "akaze":
            detector = cv2.AKAZE_create()
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        else:
            raise ValueError(f"Unsupported registration algorithm: {algorithm}")

        satellite_keypoints, satellite_descriptors = detector.detectAndCompute(satellite_gray, None)
        render_keypoints, render_descriptors = detector.detectAndCompute(render_gray, None)
        quality = RegistrationQualityMetrics(
            algorithm=algorithm,
            satellite_keypoints=len(satellite_keypoints),
            render_keypoints=len(render_keypoints),
        )

        if satellite_descriptors is None or render_descriptors is None:
            return _RegistrationAttempt(
                algorithm=algorithm,
                accepted=False,
                has_enough_matches=False,
                transform=None,
                quality=quality,
                rejection_reason=f"{algorithm.upper()} did not find descriptors in both images.",
            )

        raw_matches = matcher.knnMatch(satellite_descriptors, render_descriptors, k=2)
        good_matches = self._ratio_test_matches(raw_matches)
        quality.good_matches = len(good_matches)
        if len(good_matches) < self.min_good_matches:
            return _RegistrationAttempt(
                algorithm=algorithm,
                accepted=False,
                has_enough_matches=False,
                transform=None,
                quality=quality,
                rejection_reason=(
                    f"{algorithm.upper()} found too few feature matches "
                    f"({len(good_matches)}; need at least {self.min_good_matches})."
                ),
            )

        satellite_points = np.float32(
            [satellite_keypoints[match.queryIdx].pt for match in good_matches]
        ).reshape(-1, 1, 2)
        render_points = np.float32(
            [render_keypoints[match.trainIdx].pt for match in good_matches]
        ).reshape(-1, 1, 2)
        matrix, inlier_mask = cv2.estimateAffinePartial2D(
            satellite_points,
            render_points,
            method=cv2.RANSAC,
            ransacReprojThreshold=4.0,
            maxIters=3000,
            confidence=0.99,
            refineIters=10,
        )
        if matrix is None or inlier_mask is None:
            return _RegistrationAttempt(
                algorithm=algorithm,
                accepted=False,
                has_enough_matches=True,
                transform=None,
                quality=quality,
                rejection_reason=f"{algorithm.upper()} could not estimate a similarity transform.",
            )

        inlier_mask_flat = inlier_mask.ravel().astype(bool)
        quality.inliers = int(inlier_mask_flat.sum())
        quality.inlier_ratio = round(quality.inliers / max(len(good_matches), 1), 4)
        reprojection_error = self._mean_reprojection_error(
            matrix,
            satellite_points.reshape(-1, 2),
            render_points.reshape(-1, 2),
            inlier_mask_flat,
        )
        quality.mean_reprojection_error_pixels = round(reprojection_error, 3)
        quality.confidence = self._confidence(quality, reprojection_error)

        scale = math.hypot(float(matrix[0, 0]), float(matrix[1, 0]))
        if quality.inliers < self.min_inliers:
            return self._rejected_attempt(
                algorithm,
                quality,
                f"{algorithm.upper()} had too few RANSAC inliers "
                f"({quality.inliers}; need at least {self.min_inliers}).",
            )
        if not self.min_scale <= scale <= self.max_scale:
            return self._rejected_attempt(
                algorithm,
                quality,
                f"{algorithm.upper()} estimated an implausible scale ({scale:.3f}).",
            )
        if reprojection_error > self.max_reprojection_error_pixels:
            return self._rejected_attempt(
                algorithm,
                quality,
                (
                    f"{algorithm.upper()} reprojection error was too high "
                    f"({reprojection_error:.2f}px)."
                ),
            )

        transform = self._transform_from_matrix(matrix, algorithm)
        return _RegistrationAttempt(
            algorithm=algorithm,
            accepted=True,
            has_enough_matches=True,
            transform=transform,
            quality=quality,
            rejection_reason=None,
        )

    def _rejected_attempt(
        self,
        algorithm: str,
        quality: RegistrationQualityMetrics,
        reason: str,
    ) -> "_RegistrationAttempt":
        return _RegistrationAttempt(
            algorithm=algorithm,
            accepted=False,
            has_enough_matches=True,
            transform=None,
            quality=quality,
            rejection_reason=reason,
        )

    def _ratio_test_matches(self, raw_matches: list[Any]) -> list[Any]:
        good_matches: list[Any] = []
        for pair in raw_matches:
            if len(pair) < 2:
                continue
            best, second_best = pair
            if best.distance < 0.75 * second_best.distance:
                good_matches.append(best)
        return sorted(good_matches, key=lambda match: match.distance)

    def _transform_from_matrix(self, matrix: np.ndarray, algorithm: str) -> SimilarityTransform:
        scale = math.hypot(float(matrix[0, 0]), float(matrix[1, 0]))
        rotation_degrees = math.degrees(math.atan2(float(matrix[1, 0]), float(matrix[0, 0])))
        return SimilarityTransform(
            matrix=[
                [round(float(matrix[0, 0]), 8), round(float(matrix[0, 1]), 8), round(float(matrix[0, 2]), 4)],
                [round(float(matrix[1, 0]), 8), round(float(matrix[1, 1]), 8), round(float(matrix[1, 2]), 4)],
            ],
            scale=round(scale, 6),
            rotation_degrees=round(rotation_degrees, 4),
            translation_pixels=[round(float(matrix[0, 2]), 4), round(float(matrix[1, 2]), 4)],
            algorithm=algorithm,
        )

    def _mean_reprojection_error(
        self,
        matrix: np.ndarray,
        satellite_points: np.ndarray,
        render_points: np.ndarray,
        inlier_mask: np.ndarray,
    ) -> float:
        if not bool(inlier_mask.any()):
            return float("inf")
        transformed = cv2.transform(satellite_points.reshape(-1, 1, 2), matrix).reshape(-1, 2)
        deltas = transformed[inlier_mask] - render_points[inlier_mask]
        return float(np.linalg.norm(deltas, axis=1).mean())

    def _confidence(
        self,
        quality: RegistrationQualityMetrics,
        reprojection_error: float,
    ) -> float:
        inlier_score = min(quality.inliers / 30.0, 1.0)
        ratio_score = min(quality.inlier_ratio / 0.75, 1.0)
        error_score = max(0.0, 1.0 - reprojection_error / self.max_reprojection_error_pixels)
        return round((0.45 * inlier_score) + (0.35 * ratio_score) + (0.20 * error_score), 4)

    def _best_attempt(self, attempts: list["_RegistrationAttempt"]) -> "_RegistrationAttempt":
        accepted = [attempt for attempt in attempts if attempt.accepted]
        if accepted:
            return max(accepted, key=lambda attempt: attempt.quality.confidence)
        return max(
            attempts,
            key=lambda attempt: (
                attempt.quality.inliers,
                attempt.quality.good_matches,
                attempt.quality.confidence,
            ),
        )

    def _warnings_for_attempts(self, attempts: list["_RegistrationAttempt"]) -> list[str]:
        return [
            attempt.rejection_reason
            for attempt in attempts
            if attempt.rejection_reason is not None and not attempt.accepted
        ]

    def _selected_polygon(self, selected_roof: SelectedRoof) -> list[list[int]]:
        if len(selected_roof.selected_roof_outlines) == 1:
            return selected_roof.selected_roof_outlines[0].polygon_pixels
        box = selected_roof.bounding_box_pixels
        return [[box.x_min, box.y_min], [box.x_max, box.y_min], [box.x_max, box.y_max], [box.x_min, box.y_max]]

    def _map_polygon(self, polygon: list[list[int]], matrix: list[list[float]]) -> list[list[int]]:
        matrix_np = np.asarray(matrix, dtype=np.float32)
        points = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
        mapped = cv2.transform(points, matrix_np).reshape(-1, 2)
        return [[int(round(float(x))), int(round(float(y)))] for x, y in mapped]

    def _load_color_image(self, image_path: Path) -> np.ndarray:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=422, detail="Satellite image could not be loaded.")
        return image

    def _decode_uploaded_png(self, content: bytes) -> np.ndarray:
        if not content:
            raise HTTPException(status_code=422, detail="Top-down render file is empty.")
        encoded = np.frombuffer(content, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=422, detail="Top-down render must be a valid PNG image.")
        return image

    def _validate_render_dimensions(
        self,
        top_down_render: np.ndarray,
        request: RoofRegistrationRequest,
    ) -> None:
        height, width = top_down_render.shape[:2]
        metadata = request.top_down_render_metadata
        if width != metadata.render_width or height != metadata.render_height:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Top-down render dimensions do not match metadata "
                    f"({width}x{height} image, {metadata.render_width}x{metadata.render_height} metadata)."
                ),
            )

    def _add_render_outline_diagnostics(
        self,
        *,
        top_down_render: np.ndarray,
        quality: RegistrationQualityMetrics,
        warnings: list[str],
    ) -> None:
        try:
            render_outlines = self.roof_analysis_service.building_outline_service.detect_outlines_from_image(
                top_down_render
            )
        except AttributeError:
            return
        except BuildingOutlineUnavailableError as exc:
            warnings.append(f"3D-render roof outline validation skipped: {exc}")
            return

        quality.detected_render_roof_candidates = len(render_outlines)
        if not render_outlines:
            warnings.append("3D-render roof outline validation found no roof candidates.")
            return


@dataclass(frozen=True)
class _RegistrationAttempt:
    algorithm: str
    accepted: bool
    has_enough_matches: bool
    transform: SimilarityTransform | None
    quality: RegistrationQualityMetrics
    rejection_reason: str | None


def get_roof_registration_service() -> RoofRegistrationService:
    return RoofRegistrationService(get_roof_analysis_service())
