import sys
import traceback

print("=== main.py запущен ===", flush=True)

try:
    from CHSUBOT import main
    print("=== CHSUBOT импортирован ===", flush=True)
except Exception:
    print("=== ОШИБКА ИМПОРТА ===", flush=True)
    traceback.print_exc()
    sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("=== ОШИБКА В MAIN ===", flush=True)
        traceback.print_exc()
        sys.exit(1)
