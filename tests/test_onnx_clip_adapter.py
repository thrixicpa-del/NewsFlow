"""Deterministic zero-network tests for the bounded NewsFlow CLIP adapter."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from scriptor import onnx_clip


class _Input:
    def __init__(self, name):
        self.name = name


class _Vision:
    def __init__(self):
        self.inputs = []

    def get_inputs(self):
        return [_Input("pixel_values")]

    def run(self, _outputs, inputs):
        self.inputs.append(inputs)
        assert inputs["pixel_values"].dtype == np.float32
        assert inputs["pixel_values"].shape[1:] == (3, 4, 4)
        return [np.ones((len(inputs["pixel_values"]), 512), dtype=np.float32)]


class _Text:
    def __init__(self):
        self.inputs = []

    def get_inputs(self):
        return [_Input("input_ids"), _Input("attention_mask")]

    def run(self, _outputs, inputs):
        self.inputs.append(inputs)
        return [np.tile(np.arange(512, dtype=np.float32), (len(inputs["input_ids"]), 1))]


class _Tokenizer:
    def __init__(self):
        self.padding = None
        self.maximum = None
        self.special = []

    @staticmethod
    def from_file(_):
        return _Tokenizer()

    def enable_truncation(self, max_length):
        self.maximum = max_length

    def enable_padding(self, **kwargs):
        self.padding = kwargs

    def add_special_tokens(self, values):
        self.special.extend(values)

    def encode_batch(self, values):
        def make(value):
            assert isinstance(value, str)
            return types.SimpleNamespace(ids=[1, 2], attention_mask=[1, 1])
        return [make(value) for value in values]


class ClipAdapterTests(unittest.TestCase):
    def test_same_model_ids_cannot_be_accidentally_reassigned(self):
        with self.assertRaises(ValueError):
            onnx_clip.ImageEmbedding("other/model")
        with self.assertRaises(ValueError):
            onnx_clip.TextEmbedding("other/model")

    def test_image_batch_and_normalized_vectors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cfg = {"image_processor_type": "CLIPImageProcessor", "do_resize": True,
                   "size": {"shortest_edge": 4}, "do_center_crop": True, "crop_size": 4,
                   "do_rescale": True, "rescale_factor": 1/255, "do_normalize": True,
                   "image_mean": [0, 0, 0], "image_std": [1, 1, 1]}
            (root / "preprocessor_config.json").write_text(json.dumps(cfg))
            engine = _Vision()
            with patch.object(onnx_clip, "_model_path", return_value=root), \
                    patch.object(onnx_clip, "_session", return_value=engine):
                model = onnx_clip.ImageEmbedding()
                frame = Image.new("RGB", (8, 4), (128, 32, 16))
                output = list(model.embed([frame, frame], batch_size=2))
            self.assertEqual(len(output), 2)
            self.assertTrue(np.allclose(output[0], 1 / np.sqrt(512)))
            pixels = engine.inputs[0]["pixel_values"]
            self.assertAlmostEqual(float(pixels[0, 0].mean()), 128 / 255, places=5)
            self.assertTrue(np.array_equal(pixels[0], pixels[1]))

    def test_text_inputs_and_512_dimension(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, value in {
                "config.json": {"pad_token_id": 0},
                "tokenizer_config.json": {"model_max_length": 77, "pad_token": "<|endoftext|>"},
                "special_tokens_map.json": {"eos_token": "<|endoftext|>"},
                "tokenizer.json": {},
            }.items():
                (root / name).write_text(json.dumps(value))
            engine = _Text()
            with patch.dict(sys.modules, {"tokenizers": types.SimpleNamespace(Tokenizer=_Tokenizer, AddedToken=object)}), \
                    patch.object(onnx_clip, "_model_path", return_value=root), \
                    patch.object(onnx_clip, "_session", return_value=engine):
                model = onnx_clip.TextEmbedding()
                self.assertEqual(model.tokenizer.maximum, 77)
                vectors = list(model.query_embed(["first", "second"]))
            self.assertEqual(len(vectors), 2)
            self.assertEqual(vectors[0].shape, (512,))
            self.assertEqual(list(engine.inputs[0]), ["input_ids", "attention_mask"])

    def test_wrong_output_dimension_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "preprocessor_config.json").write_text("{}")
            engine = _Vision()
            engine.run = lambda _n, i: [np.ones((len(i["pixel_values"]), 511), np.float32)]
            with patch.object(onnx_clip, "_model_path", return_value=root), \
                    patch.object(onnx_clip, "_session", return_value=engine):
                model = onnx_clip.ImageEmbedding()
                with self.assertRaisesRegex(RuntimeError, "dimension changed"):
                    list(model.embed(Image.new("RGB", (4, 4))))

    def test_existing_huggingface_cache_first_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in onnx_clip._MODEL_FILES[onnx_clip._IMAGE_MODEL]:
                (root / name).write_bytes(b"x")
            calls = []

            def load(**kwargs):
                calls.append(kwargs)
                return str(root)
            with patch.dict(sys.modules, {"huggingface_hub": types.SimpleNamespace(snapshot_download=load)}):
                self.assertEqual(onnx_clip._model_path(onnx_clip._IMAGE_MODEL, folder), root)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0]["local_files_only"])

    def test_missing_cached_asset_is_recovered_only_during_online_indexing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in onnx_clip._MODEL_FILES[onnx_clip._IMAGE_MODEL]:
                (root / name).write_bytes(b"x")
            (root / "model.onnx").unlink()
            attempts = []

            def load(**kwargs):
                attempts.append(kwargs["local_files_only"])
                if not kwargs["local_files_only"]:
                    (root / "model.onnx").write_bytes(b"repaired")
                return str(root)

            with patch.dict(sys.modules, {"huggingface_hub": types.SimpleNamespace(snapshot_download=load)}):
                self.assertEqual(onnx_clip._model_path(onnx_clip._IMAGE_MODEL, folder), root)
            self.assertEqual(attempts, [True, False])

    def test_incomplete_model_cache_is_error_not_silent_fallback(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(sys.modules, {"huggingface_hub": types.SimpleNamespace(snapshot_download=lambda **_: folder)}),
            self.assertRaisesRegex(RuntimeError, "Incomplete CLIP model cache"),
        ):
            onnx_clip._model_path(onnx_clip._IMAGE_MODEL, folder)


if __name__ == "__main__":
    unittest.main()
