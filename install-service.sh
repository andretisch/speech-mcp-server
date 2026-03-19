#!/bin/bash
# Установка аудио-сервера как systemd-службы на Ubuntu.
# Запуск: sudo ./install-service.sh
# Сервис: audio-stt-tts.service

set -e

INSTALL_ROOT="$(cd "$(dirname "$0")" && pwd)"
AUDIO_DIR="$INSTALL_ROOT/audio"
SERVICE_NAME="audio-stt-tts"

if [ "$(id -u)" -ne 0 ]; then
  echo "Запусти с sudo: sudo $0"
  exit 1
fi

echo "=== Установка $SERVICE_NAME ==="
echo "Каталог: $AUDIO_DIR"

# Проверка ffmpeg и curl
if ! command -v ffmpeg &>/dev/null; then
  echo "ffmpeg не найден. Установи: sudo apt install ffmpeg"
  exit 1
fi
if ! command -v curl &>/dev/null; then
  echo "curl не найден. Установи: sudo apt install curl"
  exit 1
fi

# Пользователь для запуска (владелец каталога)
RUN_USER=$(stat -c '%U' "$INSTALL_ROOT")
RUN_GROUP=$(stat -c '%G' "$INSTALL_ROOT")

# 1. Python venv и зависимости
echo ""
echo "1. Создание venv и установка зависимостей..."
cd "$AUDIO_DIR"
if [ ! -d venv ]; then
  python3 -m venv venv
fi
"$AUDIO_DIR/venv/bin/pip" install -q -r requirements.txt

# 2. .env
if [ ! -f "$AUDIO_DIR/.env" ]; then
  echo "2. Создание .env из .env.example..."
  cp "$AUDIO_DIR/.env.example" "$AUDIO_DIR/.env"
  echo "   Отредактируй $AUDIO_DIR/.env при необходимости."
else
  echo "2. .env уже есть."
fi

# 3. Права доступа (чтобы служба под $RUN_USER могла читать venv и .env)
chown -R "$RUN_USER:$RUN_GROUP" "$AUDIO_DIR/venv" 2>/dev/null || true
[ -f "$AUDIO_DIR/.env" ] && chown "$RUN_USER:$RUN_GROUP" "$AUDIO_DIR/.env"

# 4. systemd unit
echo ""
echo "4. Создание systemd-службы (запуск от $RUN_USER)..."
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
cat > "$UNIT_FILE" << EOF
[Unit]
Description=Audio STT+TTS (faster-whisper, Silero, MCP)
After=network.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$AUDIO_DIR
EnvironmentFile=$AUDIO_DIR/.env
ExecStart=$AUDIO_DIR/venv/bin/python server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "   $UNIT_FILE"

# 5. systemctl
echo ""
echo "5. Активация службы..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

echo ""
echo "=== Готово ==="
echo "Статус:  systemctl status $SERVICE_NAME"
echo "Логи:    journalctl -u $SERVICE_NAME -f"
echo "Стоп:    systemctl stop $SERVICE_NAME"
echo ""
