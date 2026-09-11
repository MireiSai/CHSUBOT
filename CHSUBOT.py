import html
import json
import os
import random
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import requests
import vk_api
from bs4 import BeautifulSoup
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except Exception:
    webdriver = None
    Options = None
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

from import_schedule_txt import load_lessons_from_txt

# ================== НАСТРОЙКИ ==================
TOKEN = os.getenv(
    "VK_BOT_TOKEN",
    "vk1.a.fsZfcaoBJzD7PqpqwraZdGrQlswDwqs1O-PomkRcRddIB8qxP_aJbNj8_wKTJg7S_iqUyjcWJP2t2W5Q-LVU-Qe6rNxYxhPoX9r3fwgsj2-1v_6knSurAevlHKvUbio2lqPV2oIdXvkrb_SSw902hPyuxn21eQoB8k2HdqhArDWpqJRePu8JpETFyqDW1du5VGQoDYubVOFSFNQJluPdvg",
)
GROUP_ID = int(os.getenv("VK_GROUP_ID", "237061650"))
GROUP_NAME = os.getenv("CHSU_GROUP_NAME", "2ПДОб-13-1оп-24")
CHSU_GROUP_URL = "https://www.chsu.ru/schedule/groups?search={group}"

user_states = {}
welcomed_users = set()
_driver = None


def send_message(vk, peer_id, message, keyboard=None):
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        keyboard=keyboard,
        random_id=random.randint(1, 2_000_000_000),
    )


def get_driver():
    global _driver
    if _driver is not None:
        return _driver
    if webdriver is None or Options is None:
        raise RuntimeError("Selenium не установлен в окружении.")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,2000")
    options.add_argument("--lang=ru-RU")
    _driver = webdriver.Chrome(options=options)
    return _driver


def parse_date_input(raw_text):
    text = raw_text.strip().replace(" ", "")
    if not text:
        raise ValueError("empty")

    parts = text.split(".")
    if len(parts) == 2:
        text = f"{text}.{datetime.now().year}"
    return datetime.strptime(text, "%d.%m.%Y").date()


def extract_events_from_snapshot(snapshot):
    if "serverMemo" in snapshot:
        data = snapshot.get("serverMemo", {}).get("data", {})
    else:
        data = snapshot.get("data", {})
    return data.get("events", {})


def load_lessons_from_api():
    credentials_raw = os.getenv("CHSU_CREDENTIALS", "").strip()
    credentials = []

    if credentials_raw:
        # Формат:
        # CHSU_CREDENTIALS=login1:pass1;login2:pass2;login3:pass3
        normalized = credentials_raw.replace("\n", ";").replace(",", ";")
        for pair in normalized.split(";"):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            login, password = pair.split(":", 1)
            if login and password:
                credentials.append((login.strip(), password.strip()))

    single_login = os.getenv("CHSU_LOGIN")
    single_password = os.getenv("CHSU_PASSWORD")
    if single_login and single_password:
        credentials.append((single_login, single_password))

    if not credentials:
        return []

    token = None
    for login, password in credentials:
        try:
            auth_resp = requests.post(
                "http://api.chsu.ru/api/auth/signin",
                json={"username": login, "password": password},
                timeout=20,
            )
            if auth_resp.status_code != 200:
                continue
            auth_data = auth_resp.json()
            token = auth_data.get("data")
            if token:
                break
        except Exception:
            continue

    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
    groups_resp = requests.get("http://api.chsu.ru/api/group/v2", headers=headers, timeout=20)
    if groups_resp.status_code != 200:
        return []

    try:
        groups = groups_resp.json()
    except Exception:
        return []
    group = next((g for g in groups if g.get("title") == GROUP_NAME), None)
    if not group:
        return []

    group_id = group.get("id")
    if not group_id:
        return []

    tt_resp = requests.get(
        f"http://api.chsu.ru/api/timetable/v1/group/{group_id}",
        headers=headers,
        timeout=20,
    )
    if tt_resp.status_code != 200:
        return []

    try:
        tt_list = tt_resp.json()
    except Exception:
        return []
    normalized = []
    for item in tt_list:
        normalized.append(
            {
                "date": item.get("dateLesson") or item.get("date"),
                "startTime": item.get("timeStart") or item.get("startTime"),
                "endTime": item.get("timeEnd") or item.get("endTime"),
                "discipline": (item.get("discipline") or {}).get("title")
                if isinstance(item.get("discipline"), dict)
                else item.get("discipline"),
                "groupType": (item.get("typeLesson") or {}).get("title")
                if isinstance(item.get("typeLesson"), dict)
                else item.get("lessonType"),
                "classroom": (item.get("auditory") or {}).get("title")
                if isinstance(item.get("auditory"), dict)
                else item.get("auditorium"),
                "address": ((item.get("building") or {}).get("title") if isinstance(item.get("building"), dict) else ""),
                "teachers": (
                    {"teacher": {"fio": (item.get("teacher") or {}).get("fio")}}
                    if isinstance(item.get("teacher"), dict)
                    else {}
                ),
            }
        )
    return normalized


def load_lessons_from_page():
    group_encoded = quote_plus(GROUP_NAME)
    url = CHSU_GROUP_URL.format(group=group_encoded)
    print(f"Loading schedule page: {url}")

    driver = get_driver()
    driver.get(url)
    time.sleep(3)
    page = driver.page_source

    soup = BeautifulSoup(page, "html.parser")
    nodes = soup.find_all(attrs={"wire:snapshot": True})
    for node in nodes:
        raw = html.unescape(node.get("wire:snapshot", ""))
        if not raw:
            continue
        try:
            snapshot = json.loads(raw)
            events = extract_events_from_snapshot(snapshot)
            if events:
                return flatten_events(events)
        except json.JSONDecodeError:
            continue

    # Фолбэк для старого формата, если он вернётся на сайте.
    state_match = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*({.*?});",
        page,
        re.DOTALL,
    )
    if state_match:
        try:
            state = json.loads(state_match.group(1))
            return flatten_events(state.get("events", {}))
        except json.JSONDecodeError:
            pass

    return []


def flatten_events(events):
    lessons = []
    for _, slots in events.items():
        if not isinstance(slots, dict):
            continue
        for _, slot_items in slots.items():
            if not isinstance(slot_items, list):
                continue
            for lesson in slot_items:
                if isinstance(lesson, dict):
                    lessons.append(lesson)
    return lessons


def load_lessons_from_manual_file():
    manual_path = Path(__file__).with_name("manual_schedule.json")
    if not manual_path.exists():
        return []

    try:
        payload = json.loads(manual_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(payload, dict):
        lessons = payload.get("lessons", [])
    elif isinstance(payload, list):
        lessons = payload
    else:
        lessons = []

    normalized = []
    for lesson in lessons:
        if not isinstance(lesson, dict):
            continue
        if not lesson.get("date"):
            continue
        normalized.append(
            {
                "date": lesson.get("date"),
                "startTime": lesson.get("startTime") or "??:??",
                "endTime": lesson.get("endTime") or "??:??",
                "discipline": lesson.get("discipline") or "Без названия",
                "groupType": lesson.get("groupType") or "Занятие",
                "address": lesson.get("address") or "",
                "classroom": lesson.get("classroom") or "—",
                "teachers": lesson.get("teachers") or {},
            }
        )
    return normalized


def load_lessons_from_cache():
    candidates = [
        Path(__file__).with_name("schedule.json"),
        Path(__file__).with_name("schedule.json.txt"),
    ]

    cache_path = next((p for p in candidates if p.exists()), None)
    if not cache_path:
        return []

    try:
        raw_text = cache_path.read_text(encoding="utf-8")
        # В старом кэше иногда встречаются неэкранированные переносы строк в строковых полях.
        payload = json.loads(raw_text, strict=False)
        events = payload.get("serverMemo", {}).get("data", {}).get("events", {})
        return flatten_events(events)
    except Exception:
        # Аварийный режим: частично битый JSON разбираем регулярками.
        raw_text = cache_path.read_text(encoding="utf-8", errors="ignore")
        pattern = re.compile(
            r'"date":"(?P<date>\d{2}\.\d{2}\.\d{4})".*?'
            r'"startTime":"(?P<start>[^"]+)".*?'
            r'"endTime":"(?P<end>[^"]+)".*?'
            r'"discipline":"(?P<discipline>[^"]*)".*?'
            r'"groupType":"(?P<group_type>[^"]*)".*?'
            r'"address":"(?P<address>[^"]*)".*?'
            r'"classroom":"(?P<classroom>[^"]*)"',
            re.DOTALL,
        )
        lessons = []
        for match in pattern.finditer(raw_text):
            lessons.append(
                {
                    "date": match.group("date"),
                    "startTime": match.group("start"),
                    "endTime": match.group("end"),
                    "discipline": match.group("discipline"),
                    "groupType": match.group("group_type"),
                    "address": match.group("address"),
                    "classroom": match.group("classroom"),
                    "teachers": {},
                }
            )
        return lessons


def load_lessons():
    fail_reasons = []

    # 1) Текстовый файл расписания — основной источник после ручного обновления.
    lessons = []
    try:
        lessons = load_lessons_from_txt()
    except Exception as exc:
        fail_reasons.append(f"txt-error:{type(exc).__name__}")
    if lessons:
        print(f"Loaded {len(lessons)} lessons from Расписание.txt")
        return lessons
    fail_reasons.append("txt-empty")

    # 2) Локальный JSON, если txt ещё не пересобран.
    lessons = []
    try:
        lessons = load_lessons_from_manual_file()
    except Exception as exc:
        fail_reasons.append(f"manual-error:{type(exc).__name__}")
    if lessons:
        print(f"Loaded {len(lessons)} lessons from manual_schedule.json")
        return lessons
    fail_reasons.append("manual-empty")

    # 3) Официальный API, если заданы CHSU_LOGIN/CHSU_PASSWORD.
    lessons = []
    try:
        lessons = load_lessons_from_api()
    except Exception as exc:
        fail_reasons.append(f"api-error:{type(exc).__name__}")
    if lessons:
        return lessons
    fail_reasons.append("api-empty")

    # 4) Публичная страница расписания.
    lessons = []
    try:
        lessons = load_lessons_from_page()
    except Exception as exc:
        fail_reasons.append(f"site-error:{type(exc).__name__}")
    if lessons:
        return lessons
    fail_reasons.append("site-empty")

    # 5) Последний резерв - локальный кэш.
    lessons = []
    try:
        lessons = load_lessons_from_cache()
    except Exception as exc:
        fail_reasons.append(f"cache-error:{type(exc).__name__}")
    if lessons:
        return lessons
    fail_reasons.append("cache-empty")

    raise RuntimeError(
        "Не удалось загрузить расписание. "
        f"Проверка источников: {', '.join(fail_reasons)}. "
        "Проверь CHSU_CREDENTIALS (или CHSU_LOGIN/CHSU_PASSWORD) и доступ к сайту ЧГУ."
    )


def format_lesson(lesson):
    start_time = lesson.get("startTime", "??:??")
    end_time = lesson.get("endTime", "??:??")
    discipline = lesson.get("discipline", "Без названия")
    lesson_type = lesson.get("groupType") or lesson.get("abbr") or "Занятие"
    classroom = lesson.get("classroom") or "—"
    address = lesson.get("address") or ""
    teachers = lesson.get("teachers") or {}
    teacher_names = ", ".join(t.get("fio", "") for t in teachers.values() if t.get("fio"))
    teacher_names = teacher_names or "—"

    return (
        f"🕒 {start_time} - {end_time}\n"
        f"📚 {discipline}\n"
        f"🏷 {lesson_type}\n"
        f"📍 {classroom}\n"
        f"🏫 {address if address else '—'}\n"
        f"👩‍🏫 {teacher_names}"
    )


def get_schedule_for_range(date_from, date_to):
    all_lessons = load_lessons()

    in_range = []
    for lesson in all_lessons:
        lesson_date = lesson.get("date")
        if not lesson_date:
            continue
        try:
            dt = datetime.strptime(lesson_date, "%d.%m.%Y").date()
        except ValueError:
            continue
        if date_from <= dt <= date_to:
            in_range.append((dt, lesson))

    if not in_range:
        if date_from == date_to:
            return f"📅 {date_from.strftime('%d.%m.%Y')}\n🎉 Пар не найдено. Можно отдыхать 😎"
        return (
            f"📆 За период {date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')}\n"
            "🎉 Пар не найдено."
        )

    in_range.sort(key=lambda item: (item[0], item[1].get("startTime", "99:99")))

    lines = [
        f"🗓 Расписание группы {GROUP_NAME}",
        f"📌 Период: {date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')}",
        "",
    ]

    current_day = None
    for dt, lesson in in_range:
        if current_day != dt:
            current_day = dt
            lines.append(f"✨ {dt.strftime('%d.%m.%Y')}")
        lines.append(format_lesson(lesson))
        lines.append("──────────")

    if lines and lines[-1] == "──────────":
        lines.pop()
    return "\n".join(lines)


def get_main_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("Сегодня", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("Завтра", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("Неделя", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("Месяц", color=VkKeyboardColor.POSITIVE)
    keyboard.add_line()
    keyboard.add_button("Выбрать день", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("Выбрать диапазон", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("Меню", color=VkKeyboardColor.NEGATIVE)
    return keyboard.get_keyboard()


def help_text():
    return (
        "🤖 Я умею показывать расписание:\n"
        "• Сегодня\n"
        "• Завтра\n"
        "• Неделя\n"
        "• Месяц\n"
        "• Выбрать день (пример: 27.04)\n"
        "• Выбрать диапазон (пример: 27.04-03.05)\n\n"
        "Нажми кнопку на клавиатуре 👇"
    )


def month_range(today):
    first_day = today.replace(day=1)
    if today.month == 12:
        next_month = date(today.year + 1, 1, 1)
    else:
        next_month = date(today.year, today.month + 1, 1)
    return first_day, next_month - timedelta(days=1)


def parse_range_input(raw_text):
    cleaned = raw_text.strip().replace(" ", "")
    if "-" not in cleaned:
        raise ValueError("Нужен дефис в формате 27.04-03.05")

    left, right = cleaned.split("-", 1)
    start = parse_date_input(left)
    end = parse_date_input(right)
    if end < start:
        raise ValueError("Дата окончания меньше даты начала")
    return start, end


def main():
    print(f"Bot started for group {GROUP_NAME}")
    while True:
        try:
            run_bot()
        except Exception as exc:
            print(f"LongPoll crashed: {type(exc).__name__}: {exc}")
            time.sleep(5)


def run_bot():
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    print("LongPoll connected")

    for event in longpoll.listen():
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue

        msg_obj = event.obj.message
        text = (msg_obj.get("text") or "").strip()
        if not text:
            continue

        peer_id = msg_obj["peer_id"]
        lower_text = text.lower()

        if peer_id not in welcomed_users:
            welcomed_users.add(peer_id)
            send_message(
                vk,
                peer_id,
                (
                    f"👋 Привет! Я бот расписания группы {GROUP_NAME}.\n"
                    "Готов помочь с парами и не только ✨"
                ),
                keyboard=get_main_keyboard(),
            )

        state = user_states.get(peer_id)
        if state == "wait_day":
            try:
                target_date = parse_date_input(lower_text)
                user_states.pop(peer_id, None)
                send_message(vk, peer_id, f"🔎 Ищу расписание на {target_date.strftime('%d.%m.%Y')}...")
                answer = get_schedule_for_range(target_date, target_date)
                send_message(vk, peer_id, answer, keyboard=get_main_keyboard())
            except ValueError:
                send_message(vk, peer_id, "❌ Неверный формат. Пример: 27.04 или 27.04.2026")
            except Exception as exc:
                send_message(vk, peer_id, f"⚠️ Не смог получить расписание: {exc}")
            continue

        if state == "wait_range":
            try:
                date_from, date_to = parse_range_input(lower_text)
                user_states.pop(peer_id, None)
                send_message(
                    vk,
                    peer_id,
                    f"🔎 Ищу расписание за период {date_from.strftime('%d.%m')} - {date_to.strftime('%d.%m')}...",
                )
                answer = get_schedule_for_range(date_from, date_to)
                send_message(vk, peer_id, answer, keyboard=get_main_keyboard())
            except ValueError as exc:
                send_message(vk, peer_id, f"❌ {exc}. Пример: 27.04-03.05")
            except Exception as exc:
                send_message(vk, peer_id, f"⚠️ Не смог получить расписание: {exc}")
            continue

        if lower_text in {"старт", "start", "начать", "меню", "привет"}:
            send_message(
                vk,
                peer_id,
                f"🧭 Меню расписания для {GROUP_NAME}\nВыбирай нужный режим 👇",
                keyboard=get_main_keyboard(),
            )
            continue

        if lower_text == "выбрать день":
            user_states[peer_id] = "wait_day"
            send_message(vk, peer_id, "📅 Введи дату в формате 27.04 или 27.04.2026")
            continue

        if lower_text == "выбрать диапазон":
            user_states[peer_id] = "wait_range"
            send_message(vk, peer_id, "🗓 Введи диапазон: 27.04-03.05")
            continue

        try:
            today = datetime.now().date()
            if lower_text == "сегодня":
                start, end = today, today
            elif lower_text == "завтра":
                start, end = today + timedelta(days=1), today + timedelta(days=1)
            elif lower_text == "неделя":
                start, end = today, today + timedelta(days=6)
            elif lower_text == "месяц":
                start, end = month_range(today)
            else:
                send_message(vk, peer_id, help_text(), keyboard=get_main_keyboard())
                continue

            send_message(vk, peer_id, "🔎 Ищу расписание, подожди чуть-чуть...")
            answer = get_schedule_for_range(start, end)
            send_message(vk, peer_id, answer, keyboard=get_main_keyboard())
        except Exception as exc:
            send_message(
                vk,
                peer_id,
                f"⚠️ Упс, не получилось получить расписание.\nПричина: {exc}\nПопробуй снова через минутку 🙏",
                keyboard=get_main_keyboard(),
            )


if __name__ == "__main__":
    try:
        main()
    finally:
        if _driver is not None:
            _driver.quit()
