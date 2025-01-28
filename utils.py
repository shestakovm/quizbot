from aiogram import Bot
import logging
from config import ADMIN_IDS
import pytz
from datetime import datetime

async def notify_admin(bot: Bot, message: str):
    """Централизованная функция отправки уведомлений администраторам"""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"🔔 Уведомление:\n{message}")
        except Exception as e:
            logging.error(f"Failed to send notification to admin {admin_id}: {e}")

def get_moscow_time():
    """Получение текущего времени в московской таймзоне"""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow_tz)

def is_admin(user_id: int):
    """Проверка является ли пользователь администратором"""
    return user_id in ADMIN_IDS