"""First-party ONNX CLIP runtime for the two fixed NewsFlow/Qdrant models.

Keeps the existing 512-dimensional ViT-B/32 image/text model identifiers,
Hugging Face model cache layout and immutable index vectors. This is a narrow
adapter, not a general-purpose FastEmbed replacement.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

_IMAGE_MODEL = "Qdrant/clip-ViT-B-32-vision"
_TEXT_MODEL = "Qdrant/clip-ViT-B-32-text"
_MODEL_FILES = {
    _IMAGE_MODEL: ("model.onnx", "preprocessor_config.json"),
    _TEXT_MODEL: ("model.onnx", "tokenizer.json", "config.json", "tokenizer_config.json", "special_tokens_map.json"),
}


def _model_path(model_name: str, cache_dir: str | None) -> Path:
    if model_name not in _MODEL_FILES:
        raise ValueError("Unsupported NewsFlow CLIP model")
    from huggingface_hub import snapshot_download

    root = str(Path(cache_dir or (Path.home() / ".cache" / "newsflow-clip")).resolve())
    files = _MODEL_FILES[model_name]
    offline = os.environ.get("HF_HUB_OFFLINE", "").strip().lower() in {"1", "true", "yes"}
    # Prefer FastEmbed's existing HF snapshot cache without contacting the net.
    # Only an explicit index/model action may download missing model assets.
    try:
        found = Path(snapshot_download(repo_id=model_name, cache_dir=root,
                                       allow_patterns=list(files), local_files_only=True))
    except (OSError, ValueError):
        found = None
    if found is None or any(not (found / name).is_file() for name in files):
        if offline:
            raise RuntimeError(f"CLIP cache unavailable while offline: {model_name}")
        found = Path(snapshot_download(repo_id=model_name, cache_dir=root,
                                       allow_patterns=list(files), local_files_only=False))
    for name in files:
        if not (found / name).is_file():
            raise RuntimeError(f"Incomplete CLIP model cache: {model_name}/{name}")
    return found


def _session(model_dir: Path, threads: int | None):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if threads is not None:
        options.intra_op_num_threads = max(1, int(threads))
        options.inter_op_num_threads = max(1, int(threads))
    providers = ["CPUExecutionProvider"]
    if "CUDAExecutionProvider" in ort.get_available_providers():
        providers.insert(0, "CUDAExecutionProvider")
    return ort.InferenceSession(str(model_dir / "model.onnx"), sess_options=options,
                                providers=providers)


def _batch(items: Iterable, count: int):
    step = max(1, int(count))
    result = []
    for item in items:
        result.append(item)
        if len(result) == step:
            yield result
            result = []
    if result:
        yield result


class ImageEmbedding:
    """CLIP vision encoder with FastEmbed 0.8-compatible preprocessing."""

    def __init__(self, model_name: str = _IMAGE_MODEL, cache_dir: str | None = None,
                 threads: int | None = None, cuda: str = "auto"):
        if model_name != _IMAGE_MODEL:
            raise ValueError("Only NewsFlow's existing CLIP vision model is supported")
        self.dir = _model_path(model_name, cache_dir)
        self.session = _session(self.dir, threads)
        self.config = json.loads((self.dir / "preprocessor_config.json").read_text(encoding="utf-8"))
        if self.config.get("image_processor_type", "CLIPImageProcessor") != "CLIPImageProcessor":
            raise ValueError("Unsupported CLIP image processor")

    def _preprocess(self, image):
        cfg = self.config
        opened = None
        try:
            if isinstance(image, (str, Path)):
                opened = Image.open(image)
                image = opened
            rgb = image.convert("RGB")
            if cfg.get("do_resize", False):
                size = cfg.get("size", {})
                if isinstance(size, dict) and "shortest_edge" in size:
                    shortest = int(size["shortest_edge"])
                    width, height = rgb.size
                    new_w = shortest if width <= height else int(shortest * width / height)
                    new_h = shortest if height <= width else int(shortest * height / width)
                    rgb = rgb.resize((new_w, new_h), Image.Resampling(cfg.get("resample", Image.Resampling.BICUBIC)))
                else:
                    raise ValueError("Unexpected CLIP resize configuration")
            arr = np.asarray(rgb).transpose(2, 0, 1)
            if cfg.get("do_center_crop", False):
                dims = cfg["crop_size"]
                if isinstance(dims, dict):
                    height, width = int(dims["height"]), int(dims["width"])
                else:
                    height = width = int(dims)
                top = (arr.shape[1] - height) // 2
                left = (arr.shape[2] - width) // 2
                if top < 0 or left < 0:
                    padded = np.zeros((3, max(height, arr.shape[1]), max(width, arr.shape[2])), dtype=np.float32)
                    y = (padded.shape[1] - arr.shape[1]) // 2
                    x = (padded.shape[2] - arr.shape[2]) // 2
                    padded[:, y:y+arr.shape[1], x:x+arr.shape[2]] = arr
                    arr = padded
                    top = (arr.shape[1] - height) // 2
                    left = (arr.shape[2] - width) // 2
                arr = arr[:, top:top+height, left:left+width]
            arr = arr.astype(np.float32)
            if cfg.get("do_rescale", True):
                arr *= float(cfg.get("rescale_factor", 1 / 255))
            if cfg.get("do_normalize", False):
                mean = np.array(cfg["image_mean"], dtype=np.float32)[:, None, None]
                std = np.array(cfg["image_std"], dtype=np.float32)[:, None, None]
                arr = (arr - mean) / std
            return np.ascontiguousarray(arr, dtype=np.float32)
        finally:
            if opened is not None:
                opened.close()

    def embed(self, images, batch_size: int = 16):
        if isinstance(images, (str, Path, Image.Image)):
            images = [images]
        name = self.session.get_inputs()[0].name
        for group in _batch(images, batch_size):
            pixels = np.stack([self._preprocess(image) for image in group])
            output = self.session.run(None, {name: pixels})[0].reshape(len(group), -1)
            if output.shape[1] != 512:
                raise RuntimeError("CLIP vision output dimension changed; refusing to corrupt the index")
            for vector in output:
                vector = np.asarray(vector, dtype=np.float32)
                norm = np.linalg.norm(vector)
                yield vector / norm if norm else vector


class TextEmbedding:
    """CLIP text encoder; retains the query_embed API consumed by ClipIndex."""

    def __init__(self, model_name: str = _TEXT_MODEL, cache_dir: str | None = None,
                 threads: int | None = None, cuda: str = "auto"):
        if model_name != _TEXT_MODEL:
            raise ValueError("Only NewsFlow's existing CLIP text model is supported")
        from tokenizers import AddedToken, Tokenizer

        self.dir = _model_path(model_name, cache_dir)
        self.session = _session(self.dir, threads)
        self.tokenizer = Tokenizer.from_file(str(self.dir / "tokenizer.json"))
        cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        tc = json.loads((self.dir / "tokenizer_config.json").read_text(encoding="utf-8"))
        max_length = min(int(tc.get("max_length", tc.get("model_max_length", 77))),
                         int(tc.get("model_max_length", tc.get("max_length", 77))))
        self.tokenizer.enable_truncation(max_length=max_length)
        if not self.tokenizer.padding:
            self.tokenizer.enable_padding(pad_id=cfg.get("pad_token_id", 0), pad_token=tc["pad_token"])
        tokens = json.loads((self.dir / "special_tokens_map.json").read_text(encoding="utf-8"))
        for value in tokens.values():
            self.tokenizer.add_special_tokens([value if isinstance(value, str) else AddedToken(**value)])

    def query_embed(self, queries):
        if isinstance(queries, str):
            queries = [queries]
        for batch in _batch(queries, 64):
            enc = self.tokenizer.encode_batch(batch)
            ids = np.asarray([item.ids for item in enc], dtype=np.int64)
            masks = np.asarray([item.attention_mask for item in enc], dtype=np.int64)
            names = {item.name for item in self.session.get_inputs()}
            args = {"input_ids": ids, "attention_mask": masks}
            if "token_type_ids" in names:
                args["token_type_ids"] = np.zeros_like(ids)
            args = {name: arr for name, arr in args.items() if name in names}
            if not args or "input_ids" not in args:
                raise RuntimeError("CLIP text model inputs have changed")
            values = np.asarray(self.session.run(None, args)[0], dtype=np.float32)
            if values.ndim != 2 or values.shape != (len(batch), 512):
                raise RuntimeError("CLIP text output dimension changed; refusing incompatible vectors")
            yield from values
