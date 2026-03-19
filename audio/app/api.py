from __future__ import annotations

import base64
import glob
import os
import tempfile
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastmcp import FastMCP
from pydantic import BaseModel

from . import config
from .compat import patch_huggingface_hub_compat, patch_torchaudio_compat
from .device import select_device
from .diarize import diarize, reset_cache as diarize_reset_cache
from .stt import STTService
from .tts import TTSService
from .ui import debug_html


class TranscribeSegment(BaseModel):
    start: float
    end: float
    speaker: str | None = None
    text: str


class TranscribeResponse(BaseModel):
    text: str
    segments: list[TranscribeSegment] | None = None


class TTSRequest(BaseModel):
    text: str
    mode: str | None = None


class TranscribeByUploadRequest(BaseModel):
    upload_id: str


UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "audio_stt_uploads")


def create_app() -> FastAPI:
    config.load_env()
    patch_torchaudio_compat()
    patch_huggingface_hub_compat()
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    device = select_device()
    stt = STTService(device=device)
    tts = TTSService(device=device)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        preload_all = config.env_bool("PRELOAD_ALL", "0")
        if preload_all or config.env_bool("WHISPER_PRELOAD", os.environ.get("WHISPERX_PRELOAD", "0")):
            stt.preload()
        if preload_all or config.env_bool("SILERO_PRELOAD", "0"):
            tts.preload_ru()
        # diarization caches live in diarize.py; reset on shutdown
        yield
        diarize_reset_cache()

    # MCP сервер (Cursor: http://<host>:8000/mcp)
    mcp = FastMCP("Audio STT+TTS")

    @mcp.tool()
    def health_check() -> dict:
        """Проверка доступности аудио-сервера."""
        return {"status": "ok", "device": device}

    @mcp.tool()
    def transcribe_large_file_workflow() -> dict:
        """Инструкция для транскрипции БОЛЬШОГО аудиофайла. MCP не передаёт большие base64, поэтому: 1) выполни curl и загрузи файл, 2) получи upload_id, 3) вызови transcribe(upload_id=\"...\")."""
        base = os.environ.get("AUDIO_PUBLIC_URL", "http://localhost:8000")
        return {
            "workflow": [
                "1. Загрузи файл: curl -F 'file=@ПУТЬ_К_ФАЙЛУ.wav' {base}/upload",
                "2. Из ответа JSON возьми upload_id",
                "3. Вызови transcribe(upload_id=\"<upload_id>\")",
            ],
            "upload_url": f"{base}/upload",
            "upload_command": f"curl -F 'file=@FILE_PATH' {base}/upload",
            "note": "После шага 1 передай upload_id в инструмент transcribe. Файл хранится на сервере до транскрипции.",
        }

    def _run_transcribe(tmp_path: str, paths_to_clean: list[str]) -> dict:
        wav_path = stt.preprocess_to_wav_16k_mono(tmp_path)
        paths_to_clean.append(wav_path)
        fw_segments, full_text = stt.transcribe(wav_path)
        seg_models = [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in fw_segments
        ]
        if os.environ.get("DIARIZATION", "1").lower() not in ("0", "false", "off") and seg_models:
            turns = diarize(wav_path, device=device)

            def overlap(a0, a1, b0, b1):
                return max(0.0, min(a1, b1) - max(a0, b0))

            for s in seg_models:
                best_spk, best_ov = None, 0.0
                for t0, t1, spk in turns:
                    ov = overlap(s["start"], s["end"], t0, t1)
                    if ov > best_ov:
                        best_ov, best_spk = ov, spk
                s["speaker"] = best_spk
        return {"text": full_text or "(пусто)", "segments": seg_models}

    @mcp.tool()
    def transcribe(
        upload_id: str | None = None,
        file_path: str | None = None,
        audio_base64: str | None = None,
        filename: str = "audio.wav",
    ) -> dict:
        """Распознать речь. upload_id — после curl-загрузки (см. transcribe_large_file_workflow). file_path — путь на диске сервера. audio_base64 — для мелких файлов (<500KB)."""
        if upload_id:
            candidates = glob.glob(os.path.join(UPLOAD_DIR, upload_id + "*"))
            if not candidates:
                raise ValueError(f"Файл с upload_id '{upload_id}' не найден. Сначала загрузи: curl -F file=@audio.wav http://host:8000/upload")
            tmp_path = candidates[0]
            paths_to_clean = [tmp_path]
        elif file_path and os.path.isfile(file_path):
            tmp_path = file_path
            paths_to_clean = []
        elif audio_base64:
            data = base64.b64decode(audio_base64)
            suffix = os.path.splitext(filename)[1] or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(data)
                tmp_path = f.name
            paths_to_clean = [tmp_path]
        else:
            raise ValueError("Укажи upload_id, file_path или audio_base64")
        try:
            return _run_transcribe(tmp_path, paths_to_clean)
        finally:
            for p in paths_to_clean:
                try:
                    os.unlink(p)
                except OSError:
                    pass

    @mcp.tool()
    def synthesize_speech(text: str, mode: str = "auto") -> dict:
        """Синтез речи. mode: auto | ru | en."""
        wav = tts.synth_wav_bytes(text, mode=mode)
        return {
            "ok": True,
            "bytes": len(wav),
            "audio_base64": base64.b64encode(wav).decode("ascii"),
        }

    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def combined_lifespan(app: FastAPI):
        async with lifespan(app):
            async with mcp_app.lifespan(app):
                yield

    app = FastAPI(title="Audio STT+TTS", lifespan=combined_lifespan)

    @app.get("/", response_class=HTMLResponse)
    def root():
        return HTMLResponse(debug_html())

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)):
        """Загрузить аудио для transcribe. Вернёт upload_id — передай его в MCP transcribe(upload_id=\"...\")."""
        if not file.filename:
            raise HTTPException(400, "No filename")
        ext = os.path.splitext(file.filename)[1] or ".wav"
        upload_id = uuid.uuid4().hex
        path = os.path.join(UPLOAD_DIR, upload_id + ext)
        try:
            content = await file.read()
            with open(path, "wb") as f:
                f.write(content)
            return {"upload_id": upload_id}
        except Exception as e:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise HTTPException(500, str(e))

    @app.post("/transcribe/by-upload", response_model=TranscribeResponse)
    async def transcribe_by_upload(req: TranscribeByUploadRequest):
        """Транскрипция по upload_id (после POST /upload)."""
        candidates = glob.glob(os.path.join(UPLOAD_DIR, req.upload_id + "*"))
        if not candidates:
            raise HTTPException(404, f"upload_id '{req.upload_id}' не найден")
        path = candidates[0]
        paths_to_clean = [path]
        try:
            data = _run_transcribe(path, paths_to_clean)
            return TranscribeResponse(
                text=data["text"],
                segments=[TranscribeSegment(**s) for s in data["segments"]],
            )
        finally:
            for p in paths_to_clean:
                try:
                    os.unlink(p)
                except OSError:
                    pass

    @app.post("/transcribe", response_model=TranscribeResponse)
    async def transcribe_rest(file: UploadFile = File(...)):
        if not file.filename and not file.content_type:
            raise HTTPException(400, "No file provided")

        in_suffix = os.path.splitext(file.filename or "")[1] or ".input"
        with tempfile.NamedTemporaryFile(suffix=in_suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_in_path = tmp.name

        wav_path = None
        try:
            wav_path = stt.preprocess_to_wav_16k_mono(tmp_in_path)
            fw_segments, full_text = stt.transcribe(wav_path)

            seg_models = [
                TranscribeSegment(start=s.start, end=s.end, text=s.text) for s in fw_segments
            ]

            if os.environ.get("DIARIZATION", "1").lower() not in ("0", "false", "off") and seg_models:
                turns = diarize(wav_path, device=device)

                def overlap(a0, a1, b0, b1):
                    return max(0.0, min(a1, b1) - max(a0, b0))

                for s in seg_models:
                    best_spk = None
                    best_ov = 0.0
                    for t0, t1, spk in turns:
                        ov = overlap(s.start, s.end, t0, t1)
                        if ov > best_ov:
                            best_ov = ov
                            best_spk = spk
                    s.speaker = best_spk

            return TranscribeResponse(text=full_text or "(пусто)", segments=seg_models)
        except HTTPException:
            raise
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            msg = str(e).strip()
            raise HTTPException(500, msg or tb)
        finally:
            try:
                os.unlink(tmp_in_path)
            except OSError:
                pass
            if wav_path:
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass

    @app.post("/api/tts")
    async def tts_endpoint(req: TTSRequest):
        try:
            wav = tts.synth_wav_bytes(req.text, mode=req.mode or "auto")
            return Response(content=wav, media_type="audio/wav")
        except HTTPException:
            raise
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            msg = str(e).strip()
            raise HTTPException(500, msg or tb)

    @app.get("/health")
    def health():
        return {"status": "ok", "device": device}

    app.mount("/mcp", mcp_app)
    return app

