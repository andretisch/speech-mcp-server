from __future__ import annotations

import io
import os
import re
from math import gcd

import torch
from fastapi import HTTPException

from .compat import torch_safe_globals_ctx

_tts_cache = {}

ENGLISH_PHONETIC = {
    "A": "ay",
    "B": "bee",
    "C": "see",
    "D": "dee",
    "E": "ee",
    "F": "ef",
    "G": "gee",
    "H": "aitch",
    "I": "eye",
    "J": "jay",
    "K": "kay",
    "L": "el",
    "M": "em",
    "N": "en",
    "O": "oh",
    "P": "pee",
    "Q": "queue",
    "R": "ar",
    "S": "es",
    "T": "tee",
    "U": "you",
    "V": "vee",
    "W": "double you",
    "X": "ex",
    "Y": "why",
    "Z": "zee",
}

_re_latin = re.compile(r"[A-Za-z]")
_re_ws = re.compile(r"\s+")
_re_ru_keep = re.compile(r"[^0-9A-Za-zА-Яа-яЁё\s\.\,\!\?\:\;\-\(\)\"'«»]+")
_re_en_keep = re.compile(r"[^0-9A-Za-z\s\.\,\!\?\:\;\-\(\)\"']+")
_re_has_cyr = re.compile(r"[А-Яа-яЁё]")
_re_has_lat = re.compile(r"[A-Za-z]")


def _normalize_text(text: str) -> str:
    t = text or ""
    t = t.replace("…", "...")
    t = t.replace("\\", " ")
    t = t.replace("–", "-")
    t = t.replace("—", "-")
    t = _re_ws.sub(" ", t).strip()
    # ensure spacing after punctuation
    t = re.sub(r"[,.!?;:][\s]*", lambda m: m.group(0).strip() + " ", t)
    return _re_ws.sub(" ", t).strip()


def _process_special_text(text: str) -> str:
    t = text
    t = re.sub(r"http[s]?://[^\s]+", "ссылка", t)
    t = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "электронная почта", t)
    return t


def _process_abbreviations(text: str) -> str:
    def repl(match):
        abbr = match.group(1)
        if all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in abbr):
            return " ".join(ENGLISH_PHONETIC.get(c, c) for c in abbr)
        return " ".join(list(abbr))

    return re.sub(r"([А-ЯA-Z]{2,})", repl, text)


def _process_numbers(text: str) -> str:
    try:
        from num2words import num2words  # type: ignore
    except Exception:
        return text

    def convert_number_to_words(number_str: str) -> str:
        try:
            s = number_str.replace(" ", "").replace(",", ".")
            if "." in s:
                integer_part, decimal_part = s.split(".")
                words = num2words(int(integer_part), lang="ru")
                words += f" целых {num2words(int(decimal_part), lang='ru')} сотых"
                return words
            return num2words(int(s), lang="ru")
        except Exception:
            return number_str

    def num_to_text(match):
        num = match.group(0)
        # time like 12:30
        if re.match(r"^\d{1,2}:\d{2}$", num):
            try:
                h, m = num.split(":")
                return f"{num2words(int(h), lang='ru')} часов {num2words(int(m), lang='ru')} минут"
            except Exception:
                return num
        return convert_number_to_words(num)

    return re.sub(r"\d+(?:[.,]\d+)?(?::\d{2})?", num_to_text, text)


def _add_pauses(text: str) -> str:
    t = text
    t = t.replace(".", "... ")
    t = t.replace("!", "! ... ")
    t = t.replace("?", "? ... ")
    t = t.replace(",", ", ")
    return _re_ws.sub(" ", t).strip()


def preprocess_text(text: str) -> str:
    """
    Optional TTS text preprocessing inspired by silero_tts project.
    Toggle features via env:
      TTS_PREPROCESS=1, TTS_NUMBERS=1, TTS_ABBR=1, TTS_SPECIAL=1, TTS_PAUSES=1
    """
    if os.environ.get("TTS_PREPROCESS", "1").lower() in ("0", "false", "off"):
        return text
    t = _normalize_text(text)
    if os.environ.get("TTS_NUMBERS", "1").lower() not in ("0", "false", "off"):
        t = _process_numbers(t)
    if os.environ.get("TTS_ABBR", "1").lower() not in ("0", "false", "off"):
        t = _process_abbreviations(t)
    if os.environ.get("TTS_SPECIAL", "1").lower() not in ("0", "false", "off"):
        t = _process_special_text(t)
    if os.environ.get("TTS_PAUSES", "1").lower() not in ("0", "false", "off"):
        t = _add_pauses(t)
    return t


def _sanitize_tts_text(text: str, lang: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = (
        t.replace("“", '"')
        .replace("”", '"')
        .replace("„", '"')
        .replace("’", "'")
        .replace("‘", "'")
        .replace("—", "-")
        .replace("–", "-")
        .replace("…", "...")
    )
    if lang == "en":
        t = _re_en_keep.sub(" ", t)
        t = _re_ws.sub(" ", t).strip()
        if not _re_has_lat.search(t) and not re.search(r"\d", t):
            return ""
        return t
    t = _re_ru_keep.sub(" ", t)
    t = _re_ws.sub(" ", t).strip()
    if not _re_has_cyr.search(t) and not re.search(r"\d", t):
        return ""
    return t


def _torch_hub_load_silero(language: str, hub_speaker: str, device: str):
    key = (language, hub_speaker, device)
    if key in _tts_cache:
        return _tts_cache[key]

    dev = torch.device(device)
    with torch_safe_globals_ctx():
        ret = torch.hub.load(
            repo_or_dir="snakers4/silero-models",
            model="silero_tts",
            language=language,
            speaker=hub_speaker,
            trust_repo=True,
        )

    model = None
    symbols = None
    native_sr = None
    apply_tts = None
    if isinstance(ret, tuple):
        if len(ret) >= 1:
            model = ret[0]
        if len(ret) >= 2:
            symbols = ret[1]
        if len(ret) >= 3:
            native_sr = ret[2]
        if len(ret) >= 5:
            apply_tts = ret[4]
    else:
        model = ret

    if model is None:
        raise RuntimeError("Failed to load Silero TTS model")

    model.to(dev)
    if native_sr is None:
        native_sr = int(os.environ.get("SILERO_SAMPLE_RATE", "48000"))

    bundle = {
        "model": model,
        "symbols": symbols,
        "apply_tts": apply_tts,
        "native_sample_rate": int(native_sr),
        "device": dev,
    }
    _tts_cache[key] = bundle
    return bundle


def _silero_apply(bundle, text: str, voice: str | None):
    model = bundle["model"]
    sr = bundle["native_sample_rate"]

    if hasattr(model, "apply_tts"):
        kwargs = {
            "text": text,
            "sample_rate": sr,
            "put_accent": True,
            "put_yo": True,
        }
        if voice is not None:
            kwargs["speaker"] = voice
        return model.apply_tts(**kwargs)

    apply_tts = bundle.get("apply_tts")
    symbols = bundle.get("symbols")
    device = bundle.get("device")
    if not callable(apply_tts):
        raise RuntimeError("Silero apply_tts is not available for this model")

    return apply_tts(
        texts=[text],
        model=model,
        sample_rate=sr,
        symbols=symbols,
        device=device,
    )[0]


def _resample_np(x, src_sr: int, dst_sr: int):
    if src_sr == dst_sr:
        return x
    if x.size == 0:
        return x
    import numpy as np
    from scipy.signal import resample_poly

    g = gcd(int(src_sr), int(dst_sr))
    up = int(dst_sr) // g
    down = int(src_sr) // g
    y = resample_poly(x.astype(np.float32, copy=False), up, down)
    return y.astype(np.float32, copy=False)


def split_text_auto(text: str):
    def split_sentences(s: str):
        out = []
        buf = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            buf.append(ch)
            if ch in ".!?":
                j = i + 1
                while j < n and s[j].isspace():
                    buf.append(s[j])
                    j += 1
                if j < n and (s[j].isalnum()):
                    seg = "".join(buf)
                    if seg.strip():
                        out.append(seg)
                    buf = []
                    i = j
                    continue
            i += 1
        tail = "".join(buf)
        if tail.strip():
            out.append(tail)
        return out

    if not text:
        return []

    if _re_has_lat.search(text) and not _re_has_cyr.search(text):
        return [("en", s) for s in split_sentences(text)]
    if _re_has_cyr.search(text) and not _re_has_lat.search(text):
        return [("ru", s) for s in split_sentences(text)]

    parts = []
    cur_lang = None
    cur = []
    for ch in text:
        if _re_latin.match(ch):
            lang = "en"
        elif _re_has_cyr.match(ch):
            lang = "ru"
        else:
            lang = cur_lang or "ru"
        if cur_lang is None:
            cur_lang = lang
        if lang != cur_lang:
            parts.append((cur_lang, "".join(cur)))
            cur = [ch]
            cur_lang = lang
        else:
            cur.append(ch)
    if cur:
        parts.append((cur_lang, "".join(cur)))

    out = []
    for lang, seg in parts:
        for s in split_sentences(seg):
            out.append((lang, s))
    return [(lang, s) for (lang, s) in out if s]


class TTSService:
    def __init__(self, device: str):
        self.device = device

    def preload_ru(self) -> None:
        _torch_hub_load_silero(
            os.environ.get("SILERO_LANG", "ru"),
            os.environ.get("SILERO_MODEL", "v5_ru"),
            self.device,
        )

    def synth_wav_bytes(self, text: str, mode: str = "auto") -> bytes:
        if not text or not text.strip():
            raise HTTPException(400, "Empty text")

        text = preprocess_text(text.strip())
        max_chars = int(os.environ.get("SILERO_MAX_CHARS", "5000"))
        if len(text) > max_chars:
            text = text[:max_chars] + "…"

        import numpy as np
        import soundfile as sf

        ru_lang = os.environ.get("SILERO_LANG", "ru")
        ru_hub_speaker = os.environ.get("SILERO_MODEL", "v5_ru")
        ru_voice = os.environ.get("SILERO_SPEAKER", "xenia")

        en_lang = os.environ.get("SILERO_EN_LANG", "en")
        en_hub_speaker = os.environ.get("SILERO_EN_MODEL", "lj_16khz")
        en_voice = os.environ.get("SILERO_EN_SPEAKER", "") or None

        mode = (mode or "auto").strip().lower()
        if mode not in ("auto", "ru", "en"):
            raise HTTPException(400, "mode must be one of: auto, ru, en")

        if mode == "ru":
            segs = [("ru", text)]
        elif mode == "en":
            segs = [("en", text)]
        else:
            segs = split_text_auto(text)

        bundles = {}
        if any(lang == "ru" and seg.strip() for lang, seg in segs):
            bundles["ru"] = _torch_hub_load_silero(ru_lang, ru_hub_speaker, self.device)
        if any(lang == "en" and seg.strip() for lang, seg in segs):
            bundles["en"] = _torch_hub_load_silero(en_lang, en_hub_speaker, self.device)

        target_sr = int(os.environ.get("SILERO_SAMPLE_RATE", "48000"))
        silence = np.zeros(int(target_sr * 0.12), dtype=np.float32)

        pieces = []
        for lang, seg in segs:
            seg = _sanitize_tts_text(seg, lang)
            if not seg:
                continue
            b = bundles.get(lang)
            if b is None:
                continue
            voice = ru_voice if lang == "ru" else en_voice
            try:
                audio = _silero_apply(b, seg, voice)
            except ValueError:
                continue
            arr = np.array(audio, dtype=np.float32)
            arr = _resample_np(arr, int(b["native_sample_rate"]), target_sr)
            pieces.append(arr)
            pieces.append(silence)

        if not pieces:
            raise HTTPException(400, "No speakable text")

        wav = np.concatenate(pieces)
        buf = io.BytesIO()
        sf.write(buf, wav, target_sr, format="WAV", subtype="PCM_16")
        buf.seek(0)
        return buf.read()

