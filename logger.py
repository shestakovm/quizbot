import logging
from datetime import datetime
from aiogram import types
import json
import os


class MessageLogger:
    def __init__(self, log_file: str = 'messages.log'):
        self.log_file = log_file

        # Настройка логгера
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('QuizBot')

    async def log_message(self, message: types.Message):
        """Логирование сообщения пользователя"""
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'user_id': message.from_user.id,
            'username': message.from_user.username,
            'full_name': f"{message.from_user.first_name} {message.from_user.last_name or ''}",
            'message_text': message.text,
            'message_type': message.content_type
        }

        # Логируем в файл
        self.logger.info(json.dumps(log_data, ensure_ascii=False))