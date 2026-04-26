# Obstruction Detection — RID U-Net

Detects roof obstructions (PV modules, dormers, windows, ladders, chimneys) in
aerial roof imagery. Drop-in module for the Roofee backend's `RoofAnalysisService`.

**Author:** Daniel (`@dannyredel`)
**Status:** trained, validated, ready to integrate.

## What this does

Given an aerial image of a residential roof, returns a list of obstruction
polygons. The pipeline is:

1. Load image (PNG / JPG / TIFF — GeoTIFF works too)
2. Resize to 512×512 (model's training resolution)
3. ResNet-34 + U-Net forward pass → 9-channel softmax mask
4. argmax → per-pixel class ID
5. `cv2.findContours` per obstruction class → polygons
6. Scale polygons back to the original image's pixel space

## Performance

| Metric | Value |
|---|---|
| Architecture | U-Net + ResNet-34 (ImageNet-pretrained encoder) |
| Training data | RID dataset, 1880 German residential roofs (Krapf et al., 2022) |
| Best val mean IoU | **0.475** on held-out fold-1 split |
| Paper baseline | 0.42–0.46 (we exceed this) |
| Per-class IoU on test (paper) | pvmodule 0.68 · dormer 0.60 · chimney 0.43 · window 0.22 · ladder 0.06 |
| Inference latency | ~1 s on RTX 4070 GPU, ~10 s on CPU |
| Weights file size | 93.7 MB |

## Function contract

```python
from inference import detect_obstructions

obstructions = detect_obstructions("path/to/aerial.png")
```

Returns a list of dicts:

```python
[
    {
        "class": "chimney",                    # one of: pvmodule, dormer, window, ladder, chimney
        "polygon_pixels": [[x, y], ...],       # vertices in original image pixel space
        "area_pixels": 247,                    # area in original image scale
        "confidence": 0.834,                   # mean softmax probability over polygon
    },
    ...
]
```

Returns `[]` when no obstructions are detected above the noise threshold (50 px²).

**Polygon coordinate system:** `polygon_pixels` are in the **original image's**
pixel coordinate frame, not the 512×512 inference grid. So if your aerial PNG
is 1024×1024, polygon vertices range over `[0, 1024)`.

## Class taxonomy

The model has **9 output channels** corresponding to:

| Pixel value | Class | Returned as obstruction? |
|---|---|---|
| 0 | pvmodule | ✅ |
| 1 | dormer | ✅ |
| 2 | window | ✅ |
| 3 | ladder | ✅ |
| 4 | chimney | ✅ |
| 5 | shadow | ❌ (not a physical obstruction per Krapf et al. §17) |
| 6 | tree | ❌ (removable; not a physical obstruction per Krapf et al. §17) |
| 7 | unknown | ❌ (label noise per Krapf et al.) |
| 8 | **background** | ❌ (LAST index, not first — important!) |

The model is trained on all 9 classes; this module filters to `pvmodule`,
`dormer`, `window`, `ladder`, `chimney` before returning. To change the filter,
edit `OBSTRUCTION_CLASSES` at the top of `inference.py`.

## Setup

### Python version

⚠️ **TensorFlow 2.10 only supports Python 3.7–3.10.** The current Roofee
backend pins Python 3.11 in `pyproject.toml`. Three options:

1. **Run this module in a separate Python 3.10 environment**, called from the
   main backend via subprocess or a small REST shim. Cleanest separation.
2. **Use a different runtime entirely** — ONNX export works, see
   "Runtime alternatives" below.
3. **Downgrade the backend's Python version** to 3.10 — likely too disruptive.

### Install (Linux / macOS / Windows with Python 3.10)

```bash
pip install -r requirements.txt
```

### Install on Windows (Python 3.10, GPU)

PyPI yanked the TF 2.10 wheels for Windows + Python 3.9/3.10. Use conda:

```bash
conda create -n obstructions python=3.10 -y
conda install -n obstructions "tensorflow=2.10=gpu_py310*" -y
conda run -n obstructions python -m pip install "numpy<2" "segmentation-models==1.0.1" opencv-python-headless
```

### Verify GPU is visible

```bash
python -c "import os; os.environ['SM_FRAMEWORK']='tf.keras'; import tensorflow as tf; print('GPU:', tf.config.list_physical_devices('GPU'))"
```

Should print at least one `PhysicalDevice(name='/physical_device:GPU:0', ...)`.
If empty, inference still works but ~10× slower.

## Smoke test

```bash
python inference.py path/to/aerial-roof.png
```

Output:

```
Detected 7 obstructions:
  dormer      conf=0.812  area=  1240px²  (38 polygon points)
  dormer      conf=0.793  area=   910px²  (24 polygon points)
  chimney     conf=0.661  area=    87px²  (12 polygon points)
  ...
```

## Integration notes

For the merge agent / human reviewer:

- **No state is required between calls.** First call lazy-loads the model
  (~3 s); subsequent calls reuse the cached singleton. Thread-safe? Yes for
  read-only inference, but the lazy-load itself is not — wrap with a lock if
  you call it concurrently from multiple threads at startup.
- **Memory footprint**: ~600 MB once loaded (TF graph + weights). Single
  process is fine; if you fork workers, each has its own copy.
- **Image format**: `cv2.imread` handles PNG, JPG, TIFF, GeoTIFF transparently.
  No need to convert beforehand.
- **Confidence interpretation**: mean softmax probability over the polygon's
  pixels. Useful for filtering low-confidence predictions (try `> 0.5` if
  you see noise) or for confidence-weighted union if combining models.
- **The `RID_WEIGHTS_PATH` env var** lets you mount the .h5 from anywhere —
  useful if you decide to host the file on S3 / GCS instead of bundling it
  in the repo.

## Runtime alternatives (if Python 3.11 is non-negotiable)

**Option A — ONNX export.** Convert the `.h5` to ONNX once, then serve via
`onnxruntime` (works on any Python). Conversion script:

```python
import os
os.environ["SM_FRAMEWORK"] = "tf.keras"
import tensorflow as tf
import segmentation_models as sm
import tf2onnx

model = sm.Unet("resnet34", classes=9, activation="softmax", encoder_weights=None)
model.load_weights("rid_unet_resnet34_best.h5")
tf2onnx.convert.from_keras(model, output_path="rid_unet_resnet34.onnx", opset=15)
```

**Option B — Microservice.** Run this module behind a small FastAPI on a
different port (e.g. `:9001`) and call it from the main backend over HTTP.
Decouples Python versions cleanly. Trade-off: extra process to manage.

## Weights file note

`rid_unet_resnet34_best.h5` is **93.7 MB**. Above GitHub's regular file size
limit (50 MB), but under the hard limit (100 MB). It will commit, but it'll
slow down clones. Recommend either:

- **Use git-lfs**: `git lfs track "*.h5"` then commit normally
- **Or host externally**: drop the .h5 in S3/Drive, replace with a download
  script in this folder, and have CI / setup pull it on first run

## Provenance

- **Architecture & dataset**: Krapf et al. (2022). [RID—Roof Information
  Dataset for Computer Vision-Based Photovoltaic Potential Assessment.
  Remote Sensing 14(10), 2299.](https://doi.org/10.3390/rs14102299)
- **Training code & dataset**: [github.com/TUMFTM/RID](https://github.com/TUMFTM/RID)
  (LGPL on code, CC BY-NC on data)
- **Trained weights**: produced fresh by us — TUMFTM didn't distribute pretrained
  weights. Training notebook: `notebooks/03_train_rid_unet.ipynb` in the
  upstream Daniel/big_hack_berlin repo. Verified to match/exceed paper's
  reported val IoU range.

## License

The code in this folder is original (write your own license header on merge).
The dataset the model was trained on is **CC BY-NC** — non-commercial use only.
This matches the broader Roofee hackathon usage; for production deployment
beyond the hackathon, the dataset license needs revisiting.
