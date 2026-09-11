# Deploy на PythonAnywhere

Ниже готовый сценарий для твоего VK-бота расписания.

## 1) Загрузка проекта

В `Bash console` на PythonAnywhere:

```bash
cd ~
git clone <ссылка_на_репозиторий> ChguScheduleBot
cd ChguScheduleBot
```

Если без git, просто загрузи архив проекта через `Files`.

## 2) Виртуальное окружение

```bash
cd ~/ChguScheduleBot
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r pythonanywhere/requirements-pythonanywhere.txt
```

## 3) Настройка переменных окружения

Скопируй шаблон:

```bash
cp pythonanywhere/.env.pythonanywhere.example .env
```

Открой `.env` и заполни:

- `VK_BOT_TOKEN`
- `VK_GROUP_ID`
- `CHSU_GROUP_NAME`
- `CHSU_CREDENTIALS` (если используешь API)

Пример формата `CHSU_CREDENTIALS`:

```text
CHSU_CREDENTIALS="login1:password1;login2:password2"
```

## 4) Локальное расписание (рекомендуется)

Т.к. сайт/API ЧГУ бывает нестабильным, положи актуальный `manual_schedule.json` в корень проекта.

Если есть `Расписание.txt`, можно собрать автоматически:

```bash
python import_schedule_txt.py
```

## 5) Пробный запуск

```bash
bash pythonanywhere/start_bot.sh
```

Если всё ок, увидишь `Bot started for group ...`.

## 6) Постоянная работа (Always-on task)

1. Открой вкладку `Tasks`
2. `Always-on tasks` -> `Add a new always-on task`
3. Команда:

```bash
bash /home/<твой_логин>/ChguScheduleBot/pythonanywhere/start_bot.sh
```

## 7) Логи и перезапуск

- Логи задачи: во вкладке `Tasks` у always-on процесса.
- После правок в коде: `Stop` -> `Start`.

## Полезно

- Если бот не отвечает, первым делом проверь переменные в `.env`.
- Для обновления расписания из `Расписание.txt` перезапусти:
  - `python import_schedule_txt.py`
  - затем рестарт always-on task.
