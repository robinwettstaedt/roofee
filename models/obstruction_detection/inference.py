"""
RID U-Net inference — roof obstruction detection.

Detects PV modules, dormers, windows, ladders, and chimneys in aerial roof
images. Trained on TUM Munich's Roof Information Dataset (Krapf et al., 2022,
DOI: 10.3390/rs14102299) on a U-Net + ResNet-34 architecture using the Keras
`segmentation_models` library.

Best held-out val IoU: 0.475 (paper reports 0.42-0.46 across configurations).

USAGE:
    from inference import detect_obstructions
    obstructions = detect_obstructions("path/to/aerial.png")
    # → list of {class, polygon_pixels, area_pixels, confidence} dicts
"""
from __future__ import annotations  # PEP 563 — `str | Path` works on Python 3.9

import os

# segmentation_models reads this env var at import to know which Keras to bind
# to. MUST be set before `import segmentation_models` runs.
os.environ.setdefault("SM_FRAMEWORK", "tf.keras")

from pathlib import Path
import numpy as np
import cv2

import tensorflow as tf  # noqa: F401 (required so segmentation_models can find tf.keras)
import segmentation_models as sm


# ─────────────────────────────────────────────────────────────────────────────
# Class taxonomy — VERIFIED against RID's mask_generation.py. DO NOT REORDER.
# Note: background is the LAST index (8), not the first. Inverse of common
# segmentation conventions.
# ─────────────────────────────────────────────────────────────────────────────
CLASSES = [
    "pvmodule", "dormer", "window", "ladder",
    "chimney", "shadow", "tree", "unknown", "background",
]
N_CLASSES = len(CLASSES)
BG_INDEX = CLASSES.index("background")  # = 8

# Classes returned to the caller as obstructions for module placement.
# Per Krapf et al. (2022) §17: shadow + tree should NOT be treated as
# obstructions even though the model was trained on them.
OBSTRUCTION_CLASSES = ["pvmodule", "dormer", "window", "ladder", "chimney"]

# Architecture (matches what the .h5 was trained against)
BACKBONE = "resnet34"
TRAIN_INPUT_SIZE = 512  # model was trained at 512x512

# Filter contours below this many pixels — suppresses noise blobs
MIN_POLYGON_AREA_PX = 50

# Default weights file location (sibling of this script). Override with
# RID_WEIGHTS_PATH env var if you store the .h5 elsewhere (e.g. in a
# dedicated weights/ folder, mounted volume, S3 cache, etc.).
DEFAULT_WEIGHTS_PATH = Path(__file__).parent / "rid_unet_resnet34_best.h5"
WEIGHTS_PATH = Path(os.environ.get("RID_WEIGHTS_PATH", str(DEFAULT_WEIGHTS_PATH)))


# ─────────────────────────────────────────────────────────────────────────────
# Lazy-loaded model (one Unet + preprocessing pair per process)
# ─────────────────────────────────────────────────────────────────────────────
_model = None
_preprocess_input = None


def _load_model():
    """Build the architecture once, load weights, return (model, preprocess_input)."""
    global _model, _preprocess_input
    if _model is not None:
        return _model, _preprocess_input

    if not WEIGHTS_PATH.exists():
        raise FileNotFoundError(
            f"RID weights not found at {WEIGHTS_PATH}. "
            f"Set the RID_WEIGHTS_PATH env var or place "
            f"rid_unet_resnet34_best.h5 next to inference.py."
        )

    # encoder_weights=None: we don't want to download ImageNet just to overwrite
    # immediately with our trained weights below.
    model = sm.Unet(
        BACKBONE,
        classes=N_CLASSES,
        activation="softmax",
        encoder_weights=None,
    )
    model.load_weights(str(WEIGHTS_PATH))

    _model = model
    _preprocess_input = sm.get_preprocessing(BACKBONE)
    return _model, _preprocess_input


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def detect_obstructions(image_path: str | Path) -> list[dict]:
    """
    Detect roof obstructions in an aerial image.

    Args:
        image_path: path to an aerial image. PNG / JPG / TIFF (incl. GeoTIFF)
                    all work — cv2.imread reads the raster, geo-metadata is
                    ignored.

    Returns:
        List of obstruction dicts. Polygon vertices are in the ORIGINAL
        image's pixel space (NOT the resized 512x512 inference input):

            [
                {
                    "class": "chimney",            # one of OBSTRUCTION_CLASSES
                    "polygon_pixels": [[x, y], ...],
                    "area_pixels": int,            # in original image scale
                    "confidence": float,           # mean softmax over polygon
                },
                ...
            ]

        Order is by class then arbitrary contour order. Returns [] if the
        model finds no obstructions above MIN_POLYGON_AREA_PX.
    """
    model, preprocess_input = _load_model()

    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    orig_h, orig_w = img_rgb.shape[:2]

    # Resize to the model's training resolution
    img_resized = cv2.resize(
        img_rgb, (TRAIN_INPUT_SIZE, TRAIN_INPUT_SIZE),
        interpolation=cv2.INTER_AREA,
    )
    x = preprocess_input(img_resized.astype(np.float32))
    x = np.expand_dims(x, axis=0)

    # Predict — output is (1, H, W, N_CLASSES) softmax probabilities
    probs = model.predict(x, verbose=0)[0]              # (H, W, N_CLASSES)
    pred_mask = probs.argmax(axis=-1).astype(np.uint8)  # (H, W) class IDs

    # Scale factor from inference grid back to original image
    scale_x = orig_w / TRAIN_INPUT_SIZE
    scale_y = orig_h / TRAIN_INPUT_SIZE

    obstructions: list[dict] = []
    for class_name in OBSTRUCTION_CLASSES:
        class_idx = CLASSES.index(class_name)
        binary_mask = (pred_mask == class_idx).astype(np.uint8) * 255

        contours, _ = cv2.findContours(
            binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        for contour in contours:
            area_inference = cv2.contourArea(contour)
            if area_inference < MIN_POLYGON_AREA_PX:
                continue

            polygon_inference = contour.squeeze(axis=1)
            polygon_orig = [
                [int(round(p[0] * scale_x)), int(round(p[1] * scale_y))]
                for p in polygon_inference
            ]

            cmask = np.zeros_like(binary_mask)
            cv2.drawContours(cmask, [contour], -1, 1, thickness=cv2.FILLED)
            confidence = float(probs[..., class_idx][cmask.astype(bool)].mean())

            obstructions.append({
                "class": class_name,
                "polygon_pixels": polygon_orig,
                "area_pixels": int(area_inference * scale_x * scale_y),
                "confidence": round(confidence, 3),
            })

    return obstructions


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke test:  python inference.py path/to/image.png
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python inference.py <path/to/aerial-image>")
        sys.exit(1)

    results = detect_obstructions(sys.argv[1])
    print(f"Detected {len(results)} obstructions:")
    for obs in results:
        n_pts = len(obs["polygon_pixels"])
        print(
            f"  {obs['class']:<10s}  "
            f"conf={obs['confidence']:.3f}  "
            f"area={obs['area_pixels']:>6d}px²  "
            f"({n_pts} polygon points)"
        )
