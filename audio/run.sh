#!/bin/bash
# Запуск единого аудио-сервера (STT + TTS). Один venv, один PyTorch.
# PRELOAD_ALL, CUDA_VISIBLE_DEVICES и др. — в audio/.env

cd "$(dirname "$0")"
if [ ! -d venv ]; then
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
else
  source venv/bin/activate
fi
exec python server.py
