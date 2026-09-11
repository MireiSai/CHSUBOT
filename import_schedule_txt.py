import json
import re
from datetime import datetime
from pathlib import Path

SOURCE_FILE = "Расписание.txt"
TARGET_FILE = "manual_schedule.json"

DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}\s*-\s*\d{2}:\d{2}$")

TYPE_MAP = {
    "Л": "Лекция",
    "П": "Практические занятия",
    "З": "Зачет",
    "Э": "Экзамен",
    "ИКР": "Индивидуальная контактная работа",
}


def is_address_line(text: str) -> bool:
    return (
        text.startswith("пр-кт ")
        or text.startswith("ул. ")
        or text.startswith("пер. ")
        or text.startswith("наб. ")
    )


def _make_lesson(date, time_range, lesson_type_raw, discipline, address, classroom, teacher):
    start_time, end_time = [part.strip() for part in time_range.split("-")]
    teachers = {}
    if teacher and teacher not in {"-", "—"}:
        teachers = {"0": {"fio": teacher}}
    return {
        "date": date,
        "startTime": start_time,
        "endTime": end_time,
        "discipline": discipline,
        "groupType": TYPE_MAP.get(lesson_type_raw, lesson_type_raw),
        "address": address,
        "classroom": classroom or "—",
        "teachers": teachers,
    }


def parse_csv_lessons(raw_lines: list[str]) -> list[dict]:
    lessons: list[dict] = []
    for line in raw_lines:
        text = line.strip()
        if not text or text.startswith("Дата;"):
            continue
        parts = [part.strip() for part in text.split(";")]
        if len(parts) < 8:
            continue
        date = parts[0]
        time_range = parts[2]
        lesson_type_raw = parts[3]
        discipline = parts[4]
        address = parts[5]
        classroom = parts[6]
        # В выгрузке у нескольких преподавателей бывают лишние `;`,
        # поэтому ФИО берём между аудиторией и последней колонкой (кафедра).
        teacher = ", ".join(p for p in parts[7:-1] if p and p not in {"-", "—"}).strip(" ,")
        if not DATE_RE.match(date) or not TIME_RE.match(time_range):
            continue
        lessons.append(
            _make_lesson(date, time_range, lesson_type_raw, discipline, address, classroom, teacher)
        )
    return lessons


def parse_block_lessons(raw_lines: list[str]) -> list[dict]:
    lines = [line.strip() for line in raw_lines]
    lines = [line for line in lines if line and line != "В начало"]

    lessons: list[dict] = []
    i = 0
    while i < len(lines):
        if not DATE_RE.match(lines[i]):
            i += 1
            continue

        if i + 7 >= len(lines):
            break

        date = lines[i]
        time_range = lines[i + 2]
        lesson_type_raw = lines[i + 3]
        discipline = lines[i + 4]
        cursor = i + 5

        if cursor < len(lines) and lines[cursor] == discipline:
            cursor += 1

        if not TIME_RE.match(time_range):
            i += 1
            continue

        address = lines[cursor] if cursor < len(lines) else ""
        if not is_address_line(address):
            found_address = ""
            for j in range(cursor, min(cursor + 4, len(lines))):
                if is_address_line(lines[j]):
                    found_address = lines[j]
                    cursor = j
                    break
            address = found_address

        classroom = lines[cursor + 1] if cursor + 1 < len(lines) else "—"
        teacher = lines[cursor + 2] if cursor + 2 < len(lines) else "-"
        lessons.append(
            _make_lesson(date, time_range, lesson_type_raw, discipline, address, classroom, teacher)
        )
        i = cursor + 3
    return lessons


def parse_lessons(raw_lines: list[str]) -> list[dict]:
    joined = "\n".join(raw_lines[:5])
    if "Дата;" in joined or (raw_lines and ";" in raw_lines[0] and DATE_RE.match(raw_lines[0].split(";")[0].strip())):
        lessons = parse_csv_lessons(raw_lines)
    else:
        lessons = parse_block_lessons(raw_lines)
        if not lessons:
            lessons = parse_csv_lessons(raw_lines)

    unique = {}
    for lesson in lessons:
        key = (
            lesson["date"],
            lesson["startTime"],
            lesson["endTime"],
            lesson["discipline"],
            lesson["classroom"],
            lesson["groupType"],
        )
        unique[key] = lesson

    result = list(unique.values())
    result.sort(
        key=lambda x: (
            datetime.strptime(x["date"], "%d.%m.%Y"),
            x["startTime"],
            x["discipline"],
        )
    )
    return result


def load_lessons_from_txt(source: Path | None = None) -> list[dict]:
    path = source or Path(__file__).with_name(SOURCE_FILE)
    if not path.exists():
        return []
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    return parse_lessons(raw_lines)


def main() -> None:
    source = Path(__file__).with_name(SOURCE_FILE)
    target = Path(__file__).with_name(TARGET_FILE)

    if not source.exists():
        raise FileNotFoundError(f"Не найден файл: {source.name}")

    lessons = load_lessons_from_txt(source)
    target.write_text(
        json.dumps({"lessons": lessons}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Готово: {len(lessons)} записей сохранено в {target.name}")


if __name__ == "__main__":
    main()
