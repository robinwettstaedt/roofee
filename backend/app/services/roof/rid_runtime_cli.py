from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RID U-Net obstruction inference.")
    parser.add_argument("image_path", help="Path to the cropped roof image.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[4]
    inference_dir = repo_root / "models" / "obstruction_detection"
    sys.path.insert(0, str(inference_dir))

    from inference import detect_obstructions

    obstructions = detect_obstructions(args.image_path)
    print(json.dumps({"obstructions": obstructions}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
