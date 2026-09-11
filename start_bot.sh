#!/bin/bash
set -e

PROJECT_DIR="/home/$USER/ChguScheduleBot"
VENV_DIR="$PROJECT_DIR/.venv"
ENV_FILE="$PROJECT_DIR/.env"

cd "$PROJECT_DIR"

if [ -f "$VENV_DIR/bin/activate" ]; then
  source "$VENV_DIR/bin/activate"
fi

if [ -f "$ENV_FILE" ]; then
  # Надежная загрузка .env без "source", чтобы значения с ';' не ломали bash.
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|\#*) continue ;;
    esac

    key="${line%%=*}"
    value="${line#*=}"

    # Убираем пробелы вокруг ключа.
    key="$(echo "$key" | sed 's/[[:space:]]//g')"
    if [ -z "$key" ]; then
      continue
    fi

    # Снимаем обрамляющие кавычки, если есть.
    if [ "${value#\"}" != "$value" ] && [ "${value%\"}" != "$value" ]; then
      value="${value#\"}"
      value="${value%\"}"
    elif [ "${value#\'}" != "$value" ] && [ "${value%\'}" != "$value" ]; then
      value="${value#\'}"
      value="${value%\'}"
    fi

    export "$key=$value"
  done < "$ENV_FILE"
fi

export PYTHONIOENCODING="utf-8"

python CHSUBOT.py
