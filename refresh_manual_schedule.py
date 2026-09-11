import html
import json
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

# Этот файл только для локального обновления расписания с сайта.
# На хостинге должен запускаться CHSUBOT.py, а не этот скрипт.
try:
    from bs4 import BeautifulSoup
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except ImportError as exc:
    raise SystemExit(
        "refresh_manual_schedule.py нельзя запускать как бота. "
        "На Amvera в scriptName укажи CHSUBOT.py."
    ) from exc

GROUP_NAME = "2ПДОб-13-1оп-24"
CHSU_GROUP_URL = "https://www.chsu.ru/schedule/groups?search={group}"


def extract_events_from_snapshot(snapshot):
    if "serverMemo" in snapshot:
        data = snapshot.get("serverMemo", {}).get("data", {})
    else:
        data = snapshot.get("data", {})
    return data.get("events", {})


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


def to_manual_lesson(lesson):
    return {
        "date": lesson.get("date") or lesson.get("dateLesson"),
        "startTime": lesson.get("startTime") or lesson.get("timeStart") or "??:??",
        "endTime": lesson.get("endTime") or lesson.get("timeEnd") or "??:??",
        "discipline": lesson.get("discipline") or "Без названия",
        "groupType": lesson.get("groupType") or lesson.get("lessonType") or "Занятие",
        "address": lesson.get("address") or "",
        "classroom": lesson.get("classroom") or lesson.get("auditorium") or "—",
        "teachers": lesson.get("teachers") or {},
    }


def load_lessons_from_page_source(page_source):
    soup = BeautifulSoup(page_source, "html.parser")
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

    state_match = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*({.*?});",
        page_source,
        re.DOTALL,
    )
    if state_match:
        try:
            state = json.loads(state_match.group(1))
            return flatten_events(state.get("events", {}))
        except json.JSONDecodeError:
            pass

    return []


def unique_and_sort_lessons(lessons):
    unique = {}
    for lesson in lessons:
        key = (
            lesson.get("date"),
            lesson.get("startTime"),
            lesson.get("endTime"),
            lesson.get("discipline"),
            lesson.get("classroom"),
        )
        unique[key] = lesson

    result = list(unique.values())
    result.sort(key=lambda x: ((x.get("date") or "99.99.9999"), x.get("startTime") or "99:99"))
    return result


def save_manual_schedule(lessons):
    output = {"lessons": unique_and_sort_lessons(lessons)}
    out_path = Path(__file__).with_name("manual_schedule.json")
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def main():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,2000")
    options.add_argument("--lang=ru-RU")

    driver = webdriver.Chrome(options=options)
    try:
        url = CHSU_GROUP_URL.format(group=quote_plus(GROUP_NAME))
        print(f"Открываю страницу: {url}")
        driver.get(url)
        print("Если нужно, авторизуйся/пролистай страницу расписания в браузере.")
        input("Когда расписание на экране — нажми Enter здесь...")
        time.sleep(1)

        lessons = load_lessons_from_page_source(driver.page_source)
        if not lessons:
            print("Не удалось достать расписание со страницы.")
            return

        normalized = [to_manual_lesson(lesson) for lesson in lessons if lesson.get("date") or lesson.get("dateLesson")]
        out_path = save_manual_schedule(normalized)
        print(f"Готово! Сохранено {len(normalized)} записей в {out_path.name}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
