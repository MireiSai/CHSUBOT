from datetime import datetime
from typing import TYPE_CHECKING
import json

from chsu_schedule_api.client.aiohttp import AiohttpClient
from chsu_schedule_api.constants import (
    AUTH_SIGNIN,
    TIMETABLE,
)
from chsu_schedule_api.enums import Methods
from chsu_schedule_api.errors import (
    CHSUApiUnauthorizedError,
    CHSUApiResponseError,
)
from chsu_schedule_api.types import (
    GroupId,
    StudentGroup,
    TimeTable,
)

from chsu_schedule_api.api.abc import ABCApi

if TYPE_CHECKING:
    from chsu_schedule_api.client.abc import ABCHttpClient


class FixedCHSUApi(ABCApi):
    """Исправленный CHSU API wrapper"""

    def __init__(
        self,
        username: str,
        password: str,
        client: "ABCHttpClient | None" = None,
    ) -> None:
        self._headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
        self._auth_data = {"username": username, "password": password}
        self._cache: dict = {"groups": {}}
        super().__init__(client or AiohttpClient())

    async def auth_signin(self) -> bool:
        """
        ИСПРАВЛЕННАЯ авторизация
        """
        print(f"🔑 Пробую авторизацию с логином: {self._auth_data['username']}")
        
        resp = await self.request_json(
            Methods.POST,
            AUTH_SIGNIN,
            json=self._auth_data,
            headers=self._headers,
        )
        
        print(f"📡 Ответ сервера: {resp}")
        
        # Проверяем разные форматы ответа
        if isinstance(resp, dict):
            # Вариант 1: как в оригинале
            if resp.get("error") is None and "data" in resp:
                self._headers["Authorization"] = f'Bearer {resp["data"]}'
                print("✅ Авторизация успешна (формат 1)")
                return True
            
            # Вариант 2: access_token
            if "access_token" in resp:
                self._headers["Authorization"] = f'Bearer {resp["access_token"]}'
                print("✅ Авторизация успешна (формат 2)")
                return True
            
            # Вариант 3: token
            if "token" in resp:
                self._headers["Authorization"] = f'Bearer {resp["token"]}'
                print("✅ Авторизация успешна (формат 3)")
                return True
            
            # Вариант 4: ошибка в другом формате
            if "error" in resp:
                error_msg = resp.get("error")
                if isinstance(error_msg, dict):
                    raise CHSUApiUnauthorizedError(
                        error_msg.get("code", 401), 
                        error_msg.get("description", "Неизвестная ошибка")
                    )
                else:
                    raise CHSUApiUnauthorizedError(401, str(error_msg))
        
        raise CHSUApiUnauthorizedError(401, "Не корректные данные для авторизации")

    async def get_student_groups(self) -> list[StudentGroup]:
        """Get student group list"""
        resp = await self.request_json(
            Methods.GET, 
            "/StudentGroup", 
            headers=self._headers
        )
        return [StudentGroup.model_validate(gr) for gr in resp]

    async def get_time_table(self, group_title: str) -> list[TimeTable]:
        """ИСПРАВЛЕННОЕ получение расписания"""
        print(f"📚 Ищу группу: {group_title}")
        
        # Получаем список всех групп
        groups = await self.get_student_groups()
        group_id = None
        
        for g in groups:
            if g.title == group_title:
                group_id = g.id
                print(f"✅ Найдена группа ID: {group_id}")
                break
        
        if not group_id:
            print(f"❌ Группа {group_title} не найдена")
            return []
        
        # Получаем расписание по ID
        resp = await self.request_json(
            Methods.GET,
            f"{TIMETABLE}/group/{group_id}",
            headers=self._headers,
        )
        
        if isinstance(resp, list):
            print(f"✅ Получено {len(resp)} записей")
            return [TimeTable.model_validate(tt) for tt in resp]
        
        return []

    # Добавляем синхронные методы для удобства
    def auth_signin_sync(self) -> bool:
        """Синхронная версия авторизации"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.auth_signin())
    
    def get_time_table_sync(self, group_title: str) -> list[TimeTable]:
        """Синхронная версия получения расписания"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.get_time_table(group_title))
