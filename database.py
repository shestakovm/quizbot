import aiosqlite
import logging
from datetime import datetime
from typing import List, Optional, Tuple

class Database:
    def __init__(self, db_name: str = 'quiz.db'):
        self.db_name = db_name

    async def init(self):
        """Инициализация базы данных"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                # Создаем таблицу пользователей
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        full_name TEXT NOT NULL,
                        office TEXT NOT NULL,
                        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Создаем таблицу ответов
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS answers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        question_id INTEGER,
                        answer TEXT,
                        is_correct BOOLEAN,
                        answer_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')

                await db.commit()
        except Exception as e:
            logging.error(f"Database initialization error: {e}")
            raise

    async def register_user(self, user_id: int, full_name: str, office: str):
        """Регистрация нового пользователя"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    'INSERT OR REPLACE INTO users (user_id, full_name, office) VALUES (?, ?, ?)',
                    (user_id, full_name, office)
                )
                await db.commit()
        except Exception as e:
            logging.error(f"Error registering user {user_id}: {e}")
            raise

    async def get_all_users(self) -> List[int]:
        """Получение списка всех пользователей"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute('SELECT user_id FROM users') as cursor:
                    return [row[0] async for row in cursor]
        except Exception as e:
            logging.error(f"Error getting users list: {e}")
            return []

    async def save_answer(self, user_id: int, question_id: int, answer: str, is_correct: Optional[bool]):
        """Сохранение ответа пользователя"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    'INSERT INTO answers (user_id, question_id, answer, is_correct) VALUES (?, ?, ?, ?)',
                    (user_id, question_id, answer, is_correct)
                )
                await db.commit()
        except Exception as e:
            logging.error(f"Error saving answer for user {user_id}: {e}")
            raise

    async def check_if_answered(self, user_id: int, question_id: int) -> bool:
        """Проверка, отвечал ли пользователь на вопрос"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute(
                        'SELECT COUNT(*) FROM answers WHERE user_id = ? AND question_id = ?',
                        (user_id, question_id)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] > 0
        except Exception as e:
            logging.error(f"Error checking answer for user {user_id}: {e}")
            return False

    async def get_user_statistics(self, user_id: int) -> Tuple[int, int]:
        """Получение статистики пользователя (всего ответов, правильных ответов)"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute(
                    '''SELECT COUNT(*) as total, 
                       SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct 
                       FROM answers WHERE user_id = ? AND question_id != 999''',
                    (user_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] or 0, result[1] or 0
        except Exception as e:
            logging.error(f"Error getting statistics for user {user_id}: {e}")
            return 0, 0

    async def get_all_final_answers(self) -> List[Tuple[int, str, datetime]]:
        """Получение всех финальных ответов"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute(
                    '''SELECT user_id, answer, answer_time 
                       FROM answers WHERE question_id = 6 
                       ORDER BY answer_time DESC'''
                ) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            logging.error("Error getting final answers: {e}")
            return []