#!/bin/bash
# Загрузить большой файл и транскрибировать (POST multipart, без лимитов).
# Использование: ./transcribe_file.sh <файл.wav> [base_url]
# base_url по умолчанию: http://localhost:8000
#
# Для MCP: добавь --upload-only чтобы только загрузить и вывести upload_id.
# Затем вызови transcribe(upload_id="...") в Cursor.

set -e
UPLOAD_ONLY=false
if [ "$1" = "--upload-only" ]; then
  UPLOAD_ONLY=true
  shift
fi
FILE="${1:?Укажи файл: ./transcribe_file.sh audio.wav}"
BASE="${2:-http://localhost:8000}"

echo "Загрузка $FILE..." >&2
UPLOAD=$(curl -sS -F "file=@$FILE" "$BASE/upload")
UPLOAD_ID=$(echo "$UPLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin)['upload_id'])" 2>/dev/null || echo "$UPLOAD" | grep -o '"upload_id":"[^"]*"' | cut -d'"' -f4)

if [ -z "$UPLOAD_ID" ]; then
  echo "Ошибка загрузки: $UPLOAD" >&2
  exit 1
fi

if [ "$UPLOAD_ONLY" = true ]; then
  echo "upload_id=$UPLOAD_ID"
  echo "Для MCP: transcribe(upload_id=\"$UPLOAD_ID\")" >&2
  exit 0
fi

echo "Транскрипция..." >&2
curl -sS -X POST -H "Content-Type: application/json" -d "{\"upload_id\": \"$UPLOAD_ID\"}" "$BASE/transcribe/by-upload" | python3 -m json.tool
