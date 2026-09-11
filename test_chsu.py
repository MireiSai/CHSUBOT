# test_chsu.py
from chsu_schedule_api import CHSUApi
from chsu_schedule_api.types import Group
import os
from dotenv import load_dotenv

load_dotenv()

try:
    client = CHSUApi(
        username=os.getenv('CHSU_LOGIN'),
        password=os.getenv('CHSU_PASSWORD')
    )
    client.auth_signin()
    print("✅ Вход в CHSU успешен!")
    
    group = Group(title='2ПДОб-13-1оп-24')
    schedule = client.get_time_table(group)
    
    print(f"✅ Получено {len(schedule)} пар:")
    for lesson in schedule[:5]:  # Первые 5
        print(f"  {lesson.date} {lesson.start_time} - {lesson.discipline.title}")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
