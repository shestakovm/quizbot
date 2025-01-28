from aiogram import Bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import Database
from questions import QUESTIONS, INFO_POSTS
from utils import notify_admin, get_moscow_time
import asyncio
from datetime import datetime
import pytz
import logging


class Scheduler:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.running = True
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        self.last_log_time = datetime.now(self.moscow_tz)
        logging.info("Scheduler initialized")

    async def start(self):
        """Запуск планировщика"""
        logging.info("Schedule loop is starting...")
        try:
            while self.running:
                current_time = datetime.now(self.moscow_tz)

                # Проверяем, прошел ли час с последней записи лога
                time_diff = (current_time - self.last_log_time).total_seconds()
                should_log = time_diff >= 3600  # 3600 секунд = 1 час

                if should_log:
                    logging.info(f"=== Scheduler check at {current_time} ===")
                    self.last_log_time = current_time

                # Проверяем количество пользователей
                users = await self.db.get_all_users()
                if should_log:
                    logging.info(f"Total registered users: {len(users)}")

                # Проверяем вопросы
                for q_id, question in QUESTIONS.items():
                    if should_log:
                        logging.info(f"\nChecking question {q_id}:")
                        logging.info(f"Start time: {question['start_time']}")
                        logging.info(f"End time: {question['end_time']}")
                        logging.info(f"Current time: {current_time}")
                        logging.info(f"Is notified: {question.get('notified', False)}")

                    # Проверяем, наступило ли время отправки и не был ли вопрос уже отправлен
                    if (question['start_time'] <= current_time <= question['end_time'] and
                            not question.get('notified', False)):
                        # Дополнительная проверка - отправляем, только если текущее время после start_time
                        if current_time >= question['start_time']:
                            logging.info(f"Time to send question {q_id}!")
                            await self._send_question(q_id)
                            question['notified'] = True
                            logging.info(f"Question {q_id} marked as notified")

                            # Уведомляем админов о публикации вопроса
                            await notify_admin(self.bot,
                                               f"🎯 Опубликован вопрос {q_id}\n"
                                               f"Время публикации: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                                               f"Время окончания: {question['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")

                # Проверяем инфопосты
                for post_id, post in INFO_POSTS.items():
                    if should_log:
                        logging.info(f"\nChecking info post {post_id}:")
                        logging.info(f"Publish time: {post['publish_time']}")
                        logging.info(f"Current time: {current_time}")
                        logging.info(f"Is notified: {post.get('notified', False)}")

                    # Проверяем, наступило ли время публикации и не был ли пост уже отправлен
                    if (current_time >= post['publish_time'] and
                            not post.get('notified', False)):
                        logging.info(f"Time to send info post {post_id}!")
                        await self._send_info_post(post_id)
                        post['notified'] = True
                        logging.info(f"Info post {post_id} marked as notified")

                        # Уведомляем админов о публикации инфопоста
                        await notify_admin(self.bot,
                                           f"📢 Опубликован инфопост {post_id}\n"
                                           f"Время публикации: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

                # Увеличиваем интервал проверки до 30 секунд, так как у нас фиксированное расписание
                await asyncio.sleep(30)

        except Exception as e:
            logging.error(f"Error in schedule loop: {e}", exc_info=True)
            await notify_admin(self.bot, f"❌ Ошибка в планировщике: {e}")

    async def _send_question(self, question_id: int):
        """Отправка вопроса всем пользователям"""
        try:
            users = await self.db.get_all_users()
            question = QUESTIONS[question_id]

            logging.info(f"Sending question {question_id} to {len(users)} users")

            for user_id in users:
                try:
                    logging.info(f"Sending to user {user_id}")

                    # Отправляем медиа контент
                    if 'question_image' in question:
                        try:
                            with open(question['question_image'], 'rb') as photo:
                                await self.bot.send_photo(
                                    user_id,
                                    photo,
                                    caption=question['text']
                                )
                                logging.info(f"Sent photo to user {user_id}")
                        except Exception as e:
                            logging.error(f"Failed to send photo, sending text only: {e}")
                            await self.bot.send_message(user_id, question['text'])

                    elif 'video_path' in question:
                        try:
                            with open(question['video_path'], 'rb') as video:
                                await self.bot.send_video(
                                    user_id,
                                    video,
                                    caption=question['text']
                                )
                                logging.info(f"Sent video to user {user_id}")
                        except Exception as e:
                            logging.error(f"Failed to send video, sending text only: {e}")
                            await self.bot.send_message(user_id, question['text'])

                    else:
                        await self.bot.send_message(user_id, question['text'])
                        logging.info(f"Sent text to user {user_id}")

                    # Отправляем клавиатуру с вариантами ответов, если они есть
                    if 'options' in question:
                        keyboard = InlineKeyboardMarkup()
                        for option in question['options']:
                            keyboard.add(InlineKeyboardButton(text=option, callback_data=option))
                        await self.bot.send_message(
                            user_id,
                            "Выберите ваш ответ:",
                            reply_markup=keyboard
                        )
                        logging.info(f"Sent inline keyboard to user {user_id}")

                    # Информация о подсказке для второго вопроса
                    if question_id == 2:
                        hint_info = f"Подсказка будет доступна через {question['hint_delay'] // 60} минут. Используйте команду /hint для её получения."
                        await self.bot.send_message(user_id, hint_info)
                        logging.info(f"Sent hint info to user {user_id}")

                    # Добавляем небольшую задержку между отправками разным пользователям
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logging.error(f"Error sending to user {user_id}: {e}", exc_info=True)
                    await notify_admin(self.bot, f"❌ Ошибка отправки вопроса {question_id} пользователю {user_id}: {e}")

        except Exception as e:
            logging.error(f"Error in _send_question: {e}", exc_info=True)
            await notify_admin(self.bot, f"❌ Критическая ошибка при отправке вопроса {question_id}: {e}")

    async def _send_info_post(self, post_id: int):
        """Отправка информационного поста всем пользователям"""
        try:
            users = await self.db.get_all_users()
            post = INFO_POSTS[post_id]
            logging.info(f"Sending info post {post_id} to {len(users)} users")

            for user_id in users:
                try:
                    logging.info(f"Sending to user {user_id}")

                    # Если есть картинка, отправляем ее с текстом в качестве подписи
                    if 'image_path' in post:
                        try:
                            with open(post['image_path'], 'rb') as photo:
                                await self.bot.send_photo(user_id, photo, caption=post['text'])
                                logging.info(f"Sent photo with caption to user {user_id}")
                        except Exception as e:
                            logging.error(f"Failed to send photo with caption: {e}")
                            await self.bot.send_message(user_id, post['text'])
                    else:
                        await self.bot.send_message(user_id, post['text'])
                        logging.info(f"Sent text to user {user_id}")

                    # Добавляем небольшую задержку между отправками разным пользователям
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logging.error(f"Error sending info post to user {user_id}: {e}")
                    await notify_admin(self.bot, f"❌ Ошибка отправки инфопоста {post_id} пользователю {user_id}: {e}")

        except Exception as e:
            logging.error(f"Error in _send_info_post: {e}")
            await notify_admin(self.bot, f"❌ Критическая ошибка при отправке инфопоста {post_id}: {e}")