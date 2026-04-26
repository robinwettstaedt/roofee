from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


RID_CLASSES = [
    "pvmodule",
    "dormer",
    "window",
    "ladder",
    "chimney",
    "shadow",
    "tree",
    "unknown",
    "background",
]
RID_OBSTRUCTION_CLASSES = {"pvmodule", "dormer", "window", "ladder", "chimney"}
RID_OBSTRUCTION_MODEL_ID = "rid_unet_resnet34_best"
RID_OBSTRUCTION_SOURCE = "rid_unet"
RID_BACKBONE = "resnet34"


class RoofObstructionRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawObstructionDetection:
    class_name: str
    polygon_pixels: list[list[int]]
    area_pixels: float | None
    confidence: float | None


class RoofObstructionDetector(Protocol):
    def detect(self, image_path: Path) -> list[RawObstructionDetection]:
        pass


class RidInProcessDetector:
    def __init__(
        self,
        *,
        checkpoint_path: Path,
        inference_image_size: int = 512,
        device: str | None = None,
        min_polygon_area_pixels: float = 50.0,
    ) -> None:
        self.checkpoint_path = checkpoint_path
        self.inference_image_size = inference_image_size
        self.device = device
        self.min_polygon_area_pixels = min_polygon_area_pixels
        self._model = None
        self._preprocess_input = None
        self._tensorflow = None
        self._load_lock = threading.Lock()

    def detect(self, image_path: Path) -> list[RawObstructionDetection]:
        model, preprocess_input = self._load_model()

        img_bgr = cv2.imread(str(image_path))
        if img_bgr is None:
            raise RoofObstructionRuntimeError(f"Could not read selected roof image: {image_path}.")

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        orig_h, orig_w = img_rgb.shape[:2]
        img_resized = cv2.resize(
            img_rgb,
            (self.inference_image_size, self.inference_image_size),
            interpolation=cv2.INTER_AREA,
        )
        x = preprocess_input(img_resized.astype(np.float32))
        x = np.expand_dims(x, axis=0)

        try:
            probs = self._predict(model, x)[0]
        except Exception as exc:  # pragma: no cover - depends on the ML runtime.
            raise RoofObstructionRuntimeError("RID obstruction inference failed.") from exc

        return detections_from_probabilities(
            probs,
            original_width=orig_w,
            original_height=orig_h,
            min_polygon_area_pixels=self.min_polygon_area_pixels,
        )

    def _load_model(self):  # noqa: ANN202 - third-party model/preprocessor objects are untyped.
        if self._model is not None:
            return self._model, self._preprocess_input

        with self._load_lock:
            if self._model is not None:
                return self._model, self._preprocess_input

            if not self.checkpoint_path.exists():
                raise RoofObstructionRuntimeError(
                    f"RID model checkpoint was not found at {self.checkpoint_path}."
                )

            os.environ.setdefault("SM_FRAMEWORK", "tf.keras")
            try:
                import segmentation_models as sm
                import tensorflow as tf
            except ImportError as exc:
                raise RoofObstructionRuntimeError(
                    "RID obstruction detection dependencies are not installed. "
                    "Install TensorFlow and segmentation-models in the backend environment."
                ) from exc

            self._configure_tensorflow_device(tf)

            try:
                model = sm.Unet(
                    RID_BACKBONE,
                    classes=len(RID_CLASSES),
                    activation="softmax",
                    encoder_weights=None,
                )
                model.load_weights(str(self.checkpoint_path))
            except Exception as exc:  # pragma: no cover - depends on the ML runtime.
                raise RoofObstructionRuntimeError(
                    f"RID model checkpoint could not be loaded from {self.checkpoint_path}."
                ) from exc

            self._model = model
            self._preprocess_input = sm.get_preprocessing(RID_BACKBONE)
            self._tensorflow = tf
            return self._model, self._preprocess_input

    def _configure_tensorflow_device(self, tf) -> None:  # noqa: ANN001
        if not self.device:
            return

        normalized = self.device.strip().lower()
        if normalized in {"", "auto"}:
            return
        if normalized == "cpu":
            try:
                tf.config.set_visible_devices([], "GPU")
            except RuntimeError:
                pass

    def _predict(self, model, x: np.ndarray) -> np.ndarray:  # noqa: ANN001
        normalized_device = self.device.strip().lower() if self.device else ""
        if self._tensorflow is not None and normalized_device not in {"", "auto", "cpu"}:
            with self._tensorflow.device(self.device):
                return model.predict(x, verbose=0)
        return model.predict(x, verbose=0)


def detections_from_probabilities(
    probs: np.ndarray,
    *,
    original_width: int,
    original_height: int,
    min_polygon_area_pixels: float,
) -> list[RawObstructionDetection]:
    if probs.ndim != 3 or probs.shape[-1] != len(RID_CLASSES):
        raise RoofObstructionRuntimeError("RID obstruction detection returned malformed output.")

    inference_height, inference_width = probs.shape[:2]
    pred_mask = probs.argmax(axis=-1).astype(np.uint8)
    scale_x = original_width / inference_width
    scale_y = original_height / inference_height

    detections: list[RawObstructionDetection] = []
    for class_name in RID_CLASSES:
        if class_name not in RID_OBSTRUCTION_CLASSES:
            continue

        class_idx = RID_CLASSES.index(class_name)
        binary_mask = (pred_mask == class_idx).astype(np.uint8) * 255
        contours, _ = cv2.findContours(
            binary_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        for contour in contours:
            area_inference = cv2.contourArea(contour)
            if area_inference < min_polygon_area_pixels:
                continue

            polygon_inference = contour.squeeze(axis=1)
            if polygon_inference.ndim != 2:
                continue

            polygon_orig = [
                [int(round(point[0] * scale_x)), int(round(point[1] * scale_y))]
                for point in polygon_inference
            ]
            cmask = np.zeros_like(binary_mask)
            cv2.drawContours(cmask, [contour], -1, 1, thickness=cv2.FILLED)
            confidence = float(probs[..., class_idx][cmask.astype(bool)].mean())

            detections.append(
                RawObstructionDetection(
                    class_name=class_name,
                    polygon_pixels=polygon_orig,
                    area_pixels=int(area_inference * scale_x * scale_y),
                    confidence=round(confidence, 3),
                )
            )

    return detections
