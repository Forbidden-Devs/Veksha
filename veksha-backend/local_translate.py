"""
local_translate.py — local translator via transformers + OPUS-MT.

First call: downloads the model (~300 MB) and converts .bin → .safetensors.
Subsequent calls: served from memory, ~50-150 ms on GPU.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from threading import Lock

log = logging.getLogger(__name__)

MAX_CHARS = 1000

_MODELS_DIR = Path(__file__).parent / "local_models"
_LOAD_LOCK = Lock()

_PAIR_TO_MODEL: dict[tuple[str, str], str] = {
    ("en", "ru"): "Helsinki-NLP/opus-mt-en-ru",
    ("ru", "en"): "Helsinki-NLP/opus-mt-ru-en",
}


class UnsupportedPairError(ValueError):
    pass


def is_pair_supported(src: str, tgt: str) -> bool:
    return (src, tgt) in _PAIR_TO_MODEL


def _detect_lang(text: str) -> str:
    cyrillic = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    return "ru" if cyrillic / max(len(text), 1) > 0.15 else "en"


def _ensure_safetensors(model_dir: Path) -> None:
    """
    Convert pytorch_model.bin → model.safetensors if needed.
    torch.load with weights_only=True is safe even on torch 2.5.
    After conversion transformers loads safetensors without torch-version constraints.
    """
    sft = model_dir / "model.safetensors"
    bin_ = model_dir / "pytorch_model.bin"
    if sft.exists() or not bin_.exists():
        return

    log.info("[local_translate] Converting .bin → .safetensors ...")
    import torch
    from safetensors.torch import save_file

    state_dict = torch.load(str(bin_), weights_only=True, map_location="cpu")
    # MarianMT shares embed_tokens between encoder/decoder/shared —
    # clone to avoid safetensors shared-memory complaint
    state_dict = {k: v.clone() for k, v in state_dict.items()}
    save_file(state_dict, str(sft))
    log.info("[local_translate] Conversion done: %s", sft)


@lru_cache(maxsize=8)
def _load_cached(src: str, tgt: str) -> tuple:
    """Download, convert, and load one model pair."""
    import torch
    from huggingface_hub import snapshot_download
    from transformers import MarianMTModel, MarianTokenizer

    model_id = _PAIR_TO_MODEL[(src, tgt)]
    model_dir = _MODELS_DIR / model_id.replace("/", "_")

    if not model_dir.exists():
        log.info("[local_translate] Downloading %s ...", model_id)
        snapshot_download(
            model_id,
            local_dir=str(model_dir),
            ignore_patterns=["flax_*", "tf_*", "rust_*", "*.msgpack"],
        )

    _ensure_safetensors(model_dir)

    log.info("[local_translate] Loading model %s ...", model_id)
    tokenizer = MarianTokenizer.from_pretrained(str(model_dir))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    model = MarianMTModel.from_pretrained(
        str(model_dir),
        torch_dtype=dtype,
        low_cpu_mem_usage=False,
    ).to(device)
    model.eval()

    log.info("[local_translate] Ready: %s on %s", model_id, device)
    return tokenizer, model, device


def _load(src: str, tgt: str) -> tuple:
    """
    Return a process-wide cached model.

    functools.lru_cache may execute the wrapped function more than once when
    concurrent requests miss the cache together, so serialize cache misses.
    """
    with _LOAD_LOCK:
        return _load_cached(src, tgt)


def warmup(src: str = "en", tgt: str = "ru") -> None:
    """Load the default local translator once during backend startup."""
    if is_pair_supported(src, tgt):
        _load(src, tgt)


def translate(text: str, source_lang: str, target_lang: str) -> dict:
    """
    Translate locally. Raises UnsupportedPairError if the language pair is not supported,
    ValueError if the text exceeds MAX_CHARS.
    """
    if len(text) > MAX_CHARS:
        raise ValueError(f"Text too long: {len(text)} chars (max {MAX_CHARS})")

    detected = _detect_lang(text) if source_lang == "auto" else source_lang

    if not is_pair_supported(detected, target_lang):
        raise UnsupportedPairError(f"Unsupported language pair: {detected}→{target_lang}")

    import torch
    tokenizer, model, device = _load(detected, target_lang)

    inputs = tokenizer([text.strip()], return_tensors="pt", padding=True).to(device)
    with torch.inference_mode():
        output_ids = model.generate(**inputs, num_beams=1)
    translation = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]

    is_single = len(text.strip().split()) <= 4
    return {
        "translation": translation,
        "single": is_single,
        "normalized_text": text.lower().strip() if is_single else "",
        "detected_source_lang": detected,
    }
