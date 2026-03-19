# Единый аудио-сервер (STT + TTS)

Веб-сервер, который умеет **распознавать речь** (аудио → текст) и **синтезировать речь** (текст → аудио). Работает на одном сервере, с одним набором зависимостей — не нужно поднимать и настраивать отдельные сервисы для STT и TTS.

Используется: **faster-whisper** (распознавание), **Silero** (синтез), **SpeechBrain** (разделение по спикерам).

Доступ: REST API (любой клиент) и MCP (подключение AI-ассистентов вроде Cursor, Claude и др.).

## Требования

- Ubuntu 24.04 (или аналог)
- Python 3.10+
- ffmpeg
- curl (для загрузки больших файлов — скрипт `transcribe_file.sh`)
- (Опционально) NVIDIA GPU + CUDA

## Установка системных пакетов

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg curl
```

## Установка и запуск

Из корня репозитория:

```bash
chmod +x audio/run.sh
./audio/run.sh
```

При первом запуске создаётся `audio/venv` и ставятся зависимости. Сервер: **http://0.0.0.0:8000**. Настройки — в `audio/.env`.

## Переменные окружения

Файл `audio/.env` (скопируй из `audio/.env.example`).

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| AUDIO_HOST | 0.0.0.0 | Хост |
| AUDIO_PORT | 8000 | Порт |
| AUDIO_PUBLIC_URL | http://localhost:8000 | URL для curl-загрузки (transcribe_large_file_workflow) |
| CUDA_VISIBLE_DEVICES | — | GPU (0, 1, …). Пусто — все |
| WHISPER_MODEL | base | Модель STT: tiny, base, small, medium, large-v2, large-v3 |
| WHISPER_COMPUTE_TYPE | — | float16 / int8 (для GPU) |
| WHISPER_PRELOAD | 0 | 1 — загрузить STT при старте |
| WHISPER_VAD | 0 | 1 — включить VAD фильтр faster-whisper |
| PRELOAD_ALL | 0 | 1 — предзагрузить STT+VAD+SPK+TTS при старте (рекомендуется для службы) |
| VAD_PRELOAD | 0 | 1 — предзагрузить Silero VAD при старте |
| SPK_PRELOAD | 0 | 1 — предзагрузить speaker-encoder (ECAPA) при старте |
| DIARIZATION | 1 | 1 — diarization по умолчанию в `/transcribe`, 0 — выключить |
| VAD_THRESHOLD | 0.5 | Порог Silero VAD (выше — меньше ложных срабатываний) |
| VAD_MIN_SPEECH_MS | 250 | Минимальная длина речи (мс) |
| VAD_MIN_SILENCE_MS | 120 | Минимальная длина тишины (мс) |
| VAD_MERGE_GAP_SEC | 0.25 | Склейка VAD-кусков, если пауза меньше этого (сек) |
| SPK_EMB_MODEL | speechbrain/spkrec-ecapa-voxceleb | Модель speaker-embeddings |
| SPK_MIN_CHUNK_SEC | 1.0 | Минимальная длина куска для эмбеддинга (сек) |
| SPK_CLUSTER_THRESHOLD | 0.7 | Порог кластеризации (cosine distance); меньше — больше спикеров |
| SPK_MERGE_GAP_SEC | 0.4 | Склейка соседних turns одного спикера (сек) |
| SILERO_LANG | ru | Язык Silero |
| SILERO_MODEL | v5_3_ru | Модель (например: v5_3_ru, v5_2_ru, v5_ru, v4_ru) |
| SILERO_SPEAKER | xenia | Голос: aidar, baya, kseniya, xenia, eugene |
| SILERO_EN_LANG | en | Язык EN Silero |
| SILERO_EN_MODEL | v3_en | Английская модель/спикер для torch.hub (например: v3_en, lj_16khz) |
| SILERO_EN_SPEAKER | — | Английский голос (например `en_9`), если модель это поддерживает |
| SILERO_SAMPLE_RATE | 16000 | Частота дискретизации TTS (выход будет ресемплен под это значение) |
| SILERO_PRELOAD | 0 | 1 — загрузить TTS при старте |
| SILERO_MAX_CHARS | 5000 | Макс. длина текста для TTS |
| TTS_PREPROCESS | 1 | Включить препроцессинг текста для TTS |
| TTS_NUMBERS | 1 | Числа → слова (ru) |
| TTS_ABBR | 1 | Аббревиатуры (NASA/МВД) |
| TTS_SPECIAL | 1 | URL/email → слова |
| TTS_PAUSES | 1 | Добавлять паузы по пунктуации |

## API

- **POST /transcribe** — multipart/form-data, поле `file`. Ответ: `{ "text": "...", "segments": [...] }`
- **POST /upload** — multipart, загрузка большого файла. Ответ: `{ "upload_id": "..." }` → передай в transcribe
- **POST /transcribe/by-upload** — JSON `{ "upload_id": "..." }` — транскрипция загруженного файла
- **POST /api/tts** — JSON `{ "text": "..." }`. Ответ: audio/wav
- **GET /health** — проверка, в ответе `device` (cuda/cpu)

### Большие файлы и MCP

MCP-инструмент `transcribe` не может принять base64 для больших файлов. Варианты:

1. **file_path** — если сервер видит твой диск: `transcribe(file_path="/путь/к/audio.wav")`
2. **upload_id** — загрузи через `POST /upload`, передай id: `transcribe(upload_id="abc123")`
3. **Скрипт** — `./audio/transcribe_file.sh файл.wav` (загрузка + транскрипция). Требуется curl.

## MCP (Cursor)

Сервер — это MCP-сервер. Endpoint: `http://<host>:8000/mcp/`

Инструменты: `health_check`, `transcribe`, `synthesize_speech`, `transcribe_large_file_workflow` (инструкция для больших файлов).

**`.cursor/mcp.json`:**
```json
{
  "mcpServers": {
    "audio": {
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```

## Интеграция с ботом

В `.env` бота укажите URL аудио-сервера:

```env
AUDIO_SERVER_URL=http://localhost:8000
```

## Установка как служба (Ubuntu)

Из корня репозитория (от root или через sudo):

```bash
chmod +x install-service.sh
./install-service.sh
```

Скрипт создаёт `audio/venv`, ставит зависимости, копирует `audio/.env` из `audio/.env.example` (если нет) и регистрирует службу `audio-stt-tts`.

```bash
systemctl status audio-stt-tts   # статус
journalctl -u audio-stt-tts -f   # логи
systemctl stop audio-stt-tts     # остановка
```
