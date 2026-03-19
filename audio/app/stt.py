from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from fastapi import HTTPException

from .compat import torch_safe_globals_ctx


@dataclass
class STTSegment:
    start: float
    end: float
    text: str


class STTService:
    def __init__(self, device: str):
        self.device = device
        self._model = None

    def preload(self) -> None:
        self._get_model()

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            model_name = os.environ.get("WHISPER_MODEL", os.environ.get("WHISPERX_MODEL", "base"))
            compute_type = os.environ.get(
                "WHISPER_COMPUTE_TYPE",
                "float16" if self.device == "cuda" else "int8",
            )
            self._model = WhisperModel(model_name, device=self.device, compute_type=compute_type)
        return self._model

    def preprocess_to_wav_16k_mono(self, input_path: str) -> str:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise HTTPException(500, "ffmpeg is required for STT preprocessing")

        tmp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out_path = tmp_out.name
        tmp_out.close()

        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-af",
            "dynaudnorm",
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise HTTPException(500, f"ffmpeg preprocessing failed: {err or 'unknown error'}")

        return out_path

    def transcribe(self, wav_path: str) -> tuple[list[STTSegment], str]:
        model = self._get_model()
        segments, info = model.transcribe(
            wav_path,
            vad_filter=bool(int(os.environ.get("WHISPER_VAD", "0"))),
        )

        out: list[STTSegment] = []
        text_parts: list[str] = []
        for seg in segments:
            t = (getattr(seg, "text", "") or "").strip()
            if not t:
                continue
            start = float(getattr(seg, "start", 0.0) or 0.0)
            end = float(getattr(seg, "end", 0.0) or 0.0)
            out.append(STTSegment(start=start, end=end, text=t))
            text_parts.append(t)

        return out, " ".join(text_parts).strip()

