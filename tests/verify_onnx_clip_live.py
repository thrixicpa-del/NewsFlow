"""Opt-in compatibility witness: actual legacy FastEmbed vs NewsFlow ONNX CLIP.

Use only disposable synthetic pixels/text. The temporary legacy environment has
Pillow 12 solely to measure exact pre-upgrade behavior; no legacy dependency is
included in the released application. The reference model artifacts are shared.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

IMAGE_MODEL = "Qdrant/clip-ViT-B-32-vision"
TEXT_MODEL = "Qdrant/clip-ViT-B-32-text"
TEXTS = [
    "a crowd gathering in a city square",
    "a freight train crossing a river bridge",
    "government ministers speaking at a press conference",
    "митинг в центре города и журналисты",
]


def _images(root: Path) -> list[str]:
    from PIL import Image

    folder = root / "synthetic-images"
    folder.mkdir(parents=True, exist_ok=True)
    output = []
    for index, (w, h) in enumerate(((320, 240), (240, 320), (512, 320))):
        rng = np.random.default_rng(123456 + index)
        pixels = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
        pixels[h // 4:h // 2, w // 5:w // 2, :] = [200, 45, 20]
        path = folder / f"fixture-{index}.png"
        Image.fromarray(pixels, mode="RGB").save(path)
        output.append(str(path))
    return output


def _embed(root: Path, mode: str) -> None:
    if mode == "legacy":
        from fastembed import ImageEmbedding, TextEmbedding
    elif mode == "new":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from scriptor.onnx_clip import ImageEmbedding, TextEmbedding
    else:
        raise ValueError(mode)

    model_cache = str(root / "model-cache")
    images = _images(root)
    image = ImageEmbedding(IMAGE_MODEL, cache_dir=model_cache, threads=2, cuda=False)
    text = TextEmbedding(TEXT_MODEL, cache_dir=model_cache, threads=2, cuda=False)
    image_vectors = [np.asarray(v, dtype=np.float32) for v in image.embed(images, batch_size=2)]
    text_vectors = [np.asarray(v, dtype=np.float32) for v in text.query_embed(TEXTS)]
    for label, vectors, count in [("image", image_vectors, len(images)), ("text", text_vectors, len(TEXTS))]:
        if len(vectors) != count or any(v.shape != (512,) or not np.isfinite(v).all() for v in vectors):
            raise AssertionError(f"{mode} {label}: invalid 512-D vectors")
    receipt = {
        "kind": mode,
        "model": [IMAGE_MODEL, TEXT_MODEL],
        "images": [v.tolist() for v in image_vectors],
        "texts": [v.tolist() for v in text_vectors],
    }
    (root / f"{mode}.json").write_text(json.dumps(receipt), encoding="utf-8")
    print(f"CLIP_REAL_ENCODERS_{mode.upper()}=PASS images={len(images)} texts={len(TEXTS)}")


def _compare(root: Path) -> None:
    old = json.loads((root / "legacy.json").read_text(encoding="utf-8"))
    new = json.loads((root / "new.json").read_text(encoding="utf-8"))
    if old["model"] != new["model"]:
        raise AssertionError("Model identifiers changed")
    for key in ("images", "texts"):
        left = np.asarray(old[key], dtype=np.float32)
        right = np.asarray(new[key], dtype=np.float32)
        if left.shape != right.shape:
            raise AssertionError(f"{key} shape differs: {left.shape} != {right.shape}")
        max_difference = float(np.max(np.abs(left - right)))
        a = left / np.maximum(np.linalg.norm(left, axis=1, keepdims=True), 1e-15)
        b = right / np.maximum(np.linalg.norm(right, axis=1, keepdims=True), 1e-15)
        cosines = np.sum(a * b, axis=1)
        if not bool(np.all(cosines >= 0.99998)) or max_difference > 0.002:
            raise AssertionError(
                f"Actual {key} embedding regression: min_cos={cosines.min():.9f}, "
                f"max_abs={max_difference:.8f}"
            )
        print(f"CLIP_REAL_PARITY_{key.upper()}=PASS min_cos={cosines.min():.9f} max_abs={max_difference:.8f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["legacy", "new", "compare"], required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.mode == "compare":
        _compare(root)
    else:
        _embed(root, args.mode)
