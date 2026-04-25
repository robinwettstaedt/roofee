import json
import struct
from typing import Any

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from app.models.recommendation import (
    EstimatedInput,
    ModelFileValidation,
    RecommendationRequest,
    RecommendationValidationResponse,
    ShadingLevel,
)


MAX_GLB_UPLOAD_BYTES = 50 * 1024 * 1024
GLB_HEADER_SIZE = 12


class ProjectInputService:
    def validate_recommendation_input(
        self,
        request_json: str,
        model_file: UploadFile | None,
    ) -> RecommendationValidationResponse:
        raw_request = self._parse_request_json(request_json)
        recommendation_request = self._validate_request(raw_request)
        model_file_validation = self._validate_model_file(model_file)

        return RecommendationValidationResponse(
            status="validated",
            input=recommendation_request,
            present_inputs=sorted(raw_request.keys()),
            missing_required_inputs=[],
            estimated_inputs=self._estimated_inputs(raw_request, recommendation_request),
            warnings=self._warnings(recommendation_request),
            model_file=model_file_validation,
        )

    def _parse_request_json(self, request_json: str) -> dict[str, Any]:
        try:
            parsed = json.loads(request_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON in request field.") from exc

        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="The request field must contain a JSON object.")
        return parsed

    def _validate_request(self, raw_request: dict[str, Any]) -> RecommendationRequest:
        try:
            return RecommendationRequest.model_validate(raw_request)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

    def _validate_model_file(self, model_file: UploadFile | None) -> ModelFileValidation:
        if model_file is None:
            return ModelFileValidation(provided=False)

        filename = model_file.filename or ""
        if not filename.casefold().endswith(".glb"):
            raise HTTPException(status_code=400, detail="Model upload must be a .glb file.")

        content = self._read_upload(model_file)
        size_bytes = len(content)
        if size_bytes > MAX_GLB_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="Model upload must be 50 MB or smaller.")
        if size_bytes < GLB_HEADER_SIZE:
            raise HTTPException(status_code=400, detail="Invalid GLB file: header is too short.")

        magic, version, declared_length = struct.unpack("<4sII", content[:GLB_HEADER_SIZE])
        if magic != b"glTF":
            raise HTTPException(status_code=400, detail="Invalid GLB file: missing glTF magic header.")
        if version != 2:
            raise HTTPException(status_code=400, detail="Invalid GLB file: only version 2 is supported.")
        if declared_length != size_bytes:
            raise HTTPException(
                status_code=400,
                detail="Invalid GLB file: declared length does not match upload size.",
            )

        return ModelFileValidation(
            provided=True,
            filename=filename,
            size_bytes=size_bytes,
            format="glb",
            version=version,
        )

    def _read_upload(self, model_file: UploadFile) -> bytes:
        try:
            model_file.file.seek(0)
            content = model_file.file.read(MAX_GLB_UPLOAD_BYTES + 1)
            model_file.file.seek(0)
        except OSError as exc:
            raise HTTPException(status_code=400, detail="Could not read model upload.") from exc

        if not isinstance(content, bytes):
            raise HTTPException(status_code=400, detail="Could not read model upload.")
        return content

    def _estimated_inputs(
        self,
        raw_request: dict[str, Any],
        recommendation_request: RecommendationRequest,
    ) -> list[EstimatedInput]:
        estimated_inputs: list[EstimatedInput] = []
        if "load_profile" not in raw_request:
            estimated_inputs.append(
                EstimatedInput(field="load_profile", value=recommendation_request.load_profile, reason="defaulted")
            )
        if "shading_level" not in raw_request:
            estimated_inputs.append(
                EstimatedInput(field="shading_level", value=ShadingLevel.UNKNOWN, reason="not_provided")
            )
        return estimated_inputs

    def _warnings(self, recommendation_request: RecommendationRequest) -> list[str]:
        warnings: list[str] = []
        if recommendation_request.heating_existing_type.casefold() == "unknown":
            warnings.append("heating_existing_type_unknown")
        return warnings


def get_project_input_service() -> ProjectInputService:
    return ProjectInputService()
