from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, ADMIN_IDS
from database import Database
from logger import MessageLogger
from questions import QUESTIONS, INFO_POSTS, reset_times
from utils import notify_admin, get_moscow_time, is_admin
from scheduler import Scheduler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import asyncio
from datetime import datetime
scheduler_task = None
# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
db = Database()
logger = MessageLogger()

# Словарь для хранения времени последнего запроса подсказки
last_hint_request = {}

class QuizStates(StatesGroup):
    registration = State()
    answering = State()



def create_options_keyboard(options: list) -> InlineKeyboardMarkup:
    """Создание инлайн-клавиатуры с вариантами ответов"""
    keyboard = []
    for option in options:
        # Добавляем кнопку с текстом option и callback_data равной этому тексту
        keyboard.append([InlineKeyboardButton(text=option, callback_data=option)])
    return InlineKeyboardMarkup(keyboard)

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await logger.log_message(message)
    try:
        # Отправляем приветственную картинку
        try:
            with open('welcomepicture.jpg', 'rb') as photo:
                await message.answer_photo(photo)
        except Exception as e:
            logging.error(f"Failed to send welcome image: {e}")

        # Приветственное сообщение
        welcome_text = """Привет! Тебя ожидает захватывающий квиз-путешествие по Китаю. Твоя задача — собрать фрагменты загадки и разгадать, как они связаны.\n
Те, кто соберут все кусочки загадки и правильно назовут задуманное, получат «золотой» билет для участия в розыгрыше поездки в Китай за счет компании.\nОбязательно прочитайте правила по команде /rules"""

        registration_text = "Пожалуйста, введите ваши Фамилию, Имя и офис через пробел, например: Иванов Иван Осень"

        await message.answer(welcome_text)
        await message.answer(registration_text)
        await QuizStates.registration.set()

    except Exception as e:
        error_msg = f"Error in start command: {e}"
        logging.error(error_msg)
        await notify_admin(bot, error_msg)
        await message.answer(welcome_text)
        await message.answer(registration_text)
        await QuizStates.registration.set()

@dp.message_handler(commands=['rules'], state='*')  # state='*' означает, что команда будет работать в любом состоянии
async def cmd_rules(message: types.Message, state: FSMContext):  # добавляем state в параметры
    await logger.log_message(message)

    rules_text = """Задания открываются последовательно и имеют ограничение на прохождение по времени, будьте внимательны.

После того, как задание закрыто, ответы не принимаются.

Принимается только один ответ, хорошенько подумайте, прежде чем отправить его.\n Этот квиз проверяет не только вашу эрудицию, но и внимательность - проверяйте свои ответы на наличие опечаток"""

    await message.answer(rules_text)

@dp.message_handler(commands=['admin'],  state='*')
async def cmd_admin(message: types.Message):
    """Административная команда для получения статистики"""
    if not is_admin(message.from_user.id):
        return

    try:
        users = await db.get_all_users()
        total_users = len(users)
        final_answers = await db.get_all_final_answers()
        total_final = len(final_answers)

        stats = f"""📊 Статистика квиза:

Всего участников: {total_users}
Финальных ответов: {total_final}

Последние 300 финальных ответов:"""

        for user_id, answer, time in final_answers[:300]:
            user_data = await db.get_user_statistics(user_id)
            stats += f"\n- Участник {user_id}: {answer} ({time})"

        await message.answer(stats)
    except Exception as e:
        error_msg = f"Error getting admin statistics: {e}"
        logging.error(error_msg)
        await message.answer("Произошла ошибка при получении статистики")

@dp.message_handler(state=QuizStates.registration)
async def process_registration(message: types.Message, state: FSMContext):
    await logger.log_message(message)

    user_data = message.text.split()
    if len(user_data) >= 2:  # Проверяем, что введены все данные
        full_name = " ".join(user_data[:-1])
        office = user_data[-1]

        try:
            await db.register_user(
                user_id=message.from_user.id,
                full_name=full_name,
                office=office
            )
            await message.answer("Регистрация успешна!")
            await state.finish()
            await QuizStates.answering.set()

            # Проверяем, есть ли активный вопрос
            current_time = get_moscow_time()
            active_question = None
            question_id = None

            for qid, question in QUESTIONS.items():
                if question['start_time'] <= current_time <= question['end_time']:
                    active_question = question
                    question_id = qid
                    break

            if active_question:
                if await db.check_if_answered(message.from_user.id, question_id):
                    await message.answer("Вы уже ответили на текущий вопрос. Ожидайте следующий!")
                    return

                # Отправляем активный вопрос
                if 'question_image' in active_question:
                    with open(active_question['question_image'], 'rb') as photo:
                        await message.answer_photo(photo, caption=active_question['text'])
                elif 'video_path' in active_question:
                    with open(active_question['video_path'], 'rb') as video:
                        await message.answer_video(video, caption=active_question['text'])
                else:
                    await message.answer(active_question['text'])

                # Если есть варианты ответов, отправляем их
                if 'options' in active_question:
                    keyboard = create_options_keyboard(active_question['options'])
                    await message.answer("Выберите ваш ответ:", reply_markup=keyboard)
                else:
                    await message.answer("Введите ваш ответ:", reply_markup=ReplyKeyboardRemove())

                # Если это второй вопрос, информируем о подсказке
                if question_id == 2:
                    hint_info = f"Подсказка будет доступна через {active_question['hint_delay'] // 60} минут. Используйте команду /hint для её получения."
                    await message.answer(hint_info)
            else:
                await message.answer("В данный момент нет активных вопросов. Ожидайте следующий вопрос!")

            # Уведомляем админа о новой регистрации
            await notify_admin(bot, f"Новый участник зарегистрирован:\nИмя: {full_name}\nОфис: {office}")

        except Exception as e:
            error_msg = f"Error during registration: {e}"
            logging.error(error_msg)
            await message.answer("Произошла ошибка при регистрации. Пожалуйста, попробуйте еще раз.")
    else:
        await message.answer("Пожалуйста, введите ФИО и офис через пробел")

@dp.message_handler(commands=['hint'], state='*')
async def cmd_hint(message: types.Message):
    await logger.log_message(message)

    current_time = get_moscow_time()
    question_2 = QUESTIONS[2]

    # Проверяем, активен ли второй вопрос
    if not (question_2['start_time'] <= current_time <= question_2['end_time']):
        await message.answer("Подсказка доступна только для активного второго вопроса!")
        return

    user_id = message.from_user.id
    time_passed = current_time - question_2['start_time']

    if time_passed.total_seconds() < question_2['hint_delay']:
        remaining_time = question_2['hint_delay'] - time_passed.total_seconds()
        minutes = int(remaining_time // 60)
        await message.answer(f"Подсказка будет доступна через {minutes} минут")
        return

    # Отправляем подсказку
    await message.answer(question_2['hint'])


@dp.callback_query_handler(state=QuizStates.answering)
async def process_callback_answer(callback_query: types.CallbackQuery, state: FSMContext):
    await logger.log_message(callback_query.message)

    # Сразу отвечаем на callback query
    await callback_query.answer()

    current_time = get_moscow_time()
    active_question = None
    question_id = None

    # Остальной код функции...
    try:
        # Находим активный вопрос
        for qid, question in QUESTIONS.items():
            if question['start_time'] <= current_time <= question['end_time']:
                active_question = question
                question_id = qid
                break

        if not active_question:
            await callback_query.message.answer("В данный момент нет активных вопросов!")
            return

        # Проверяем, не отвечал ли уже пользователь на этот вопрос
        if await db.check_if_answered(callback_query.from_user.id, question_id):
            next_question = None
            next_time = None
            for qid, q in QUESTIONS.items():
                if qid > question_id:
                    next_question = q
                    next_time = q['start_time']
                    break

            if next_time:
                time_str = next_time.strftime('%H:%M:%S')
                await callback_query.message.answer(
                    f"Вы уже ответили на текущий вопрос! Следующий вопрос будет доступен в {time_str}")
            else:
                await callback_query.message.answer("Вы уже ответили на текущий вопрос! Ожидайте следующий.")
            return

        user_answer = callback_query.data.lower().strip()

        # Сохраняем ответ и отправляем сообщение
        is_correct = user_answer == active_question['correct_answer']
        await db.save_answer(
            user_id=callback_query.from_user.id,
            question_id=question_id,
            answer=user_answer,
            is_correct=is_correct
        )

        if is_correct:
            await callback_query.message.answer(active_question['correct_answer_text'])
            if 'image_correct' in active_question:
                with open(active_question['image_correct'], 'rb') as photo:
                    await callback_query.message.answer_photo(photo)
        else:
            await callback_query.message.answer(active_question['wrong_answer_text'])

        # Удаляем клавиатуру после ответа
        await callback_query.message.edit_reply_markup(reply_markup=None)

    except Exception as e:
        error_msg = f"Error processing callback answer: {e}"
        logging.error(error_msg)
        await callback_query.message.answer("Произошла ошибка при обработке ответа. Пожалуйста, попробуйте еще раз.")
        await notify_admin(bot, f"Ошибка при обработке ответа от {callback_query.from_user.id}: {e}")

# @dp.callback_query_handler(state=QuizStates.answering)
# async def process_callback_answer(callback_query: types.CallbackQuery, state: FSMContext):
#     await logger.log_message(callback_query.message)
#
#     current_time = get_moscow_time()
#     active_question = None
#     question_id = None
#
#     # Находим активный вопрос
#     for qid, question in QUESTIONS.items():
#         if question['start_time'] <= current_time <= question['end_time']:
#             active_question = question
#             question_id = qid
#             break
#
#     if not active_question:
#         await callback_query.message.answer("В данный момент нет активных вопросов!")
#         await callback_query.answer()
#         return
#
#     # Проверяем, не отвечал ли уже пользователь на этот вопрос
#     if await db.check_if_answered(callback_query.from_user.id, question_id):
#         next_question = None
#         next_time = None
#         for qid, q in QUESTIONS.items():
#             if qid > question_id:
#                 next_question = q
#                 next_time = q['start_time']
#                 break
#
#         if next_time:
#             time_str = next_time.strftime('%H:%M:%S')
#             await callback_query.message.answer(
#                 f"Вы уже ответили на текущий вопрос! Следующий вопрос будет доступен в {time_str}")
#         else:
#             await callback_query.message.answer("Вы уже ответили на текущий вопрос! Ожидайте следующий.")
#         await callback_query.answer()
#         return
#
#     user_answer = callback_query.data.lower().strip()
#
#     try:
#         # Проверяем правильность ответа
#         is_correct = user_answer == active_question['correct_answer']
#         await db.save_answer(
#             user_id=callback_query.from_user.id,
#             question_id=question_id,
#             answer=user_answer,
#             is_correct=is_correct
#         )
#
#         if is_correct:
#             await callback_query.message.answer(active_question['correct_answer_text'])
#             if 'image_correct' in active_question:
#                 with open(active_question['image_correct'], 'rb') as photo:
#                     await callback_query.message.answer_photo(photo)
#         else:
#             await callback_query.message.answer(active_question['wrong_answer_text'])
#
#         # Удаляем клавиатуру после ответа
#         await callback_query.message.edit_reply_markup(reply_markup=None)
#
#     except Exception as e:
#         error_msg = f"Error processing callback answer: {e}"
#         logging.error(error_msg)
#         await callback_query.message.answer("Произошла ошибка при обработке ответа. Пожалуйста, попробуйте еще раз.")
#         await notify_admin(bot, f"Ошибка при обработке ответа от {callback_query.from_user.id}: {e}")
#
#     finally:
#         await callback_query.answer()



@dp.message_handler(lambda message: not message.text.startswith('/'), state=QuizStates.answering)
async def process_answer(message: types.Message):


    await logger.log_message(message)

    current_time = get_moscow_time()
    active_question = None
    question_id = None

    # Находим активный вопрос
    for qid, question in QUESTIONS.items():
        if question['start_time'] <= current_time <= question['end_time']:
            active_question = question
            question_id = qid
            break

    if not active_question:
        await message.answer("В данный момент нет активных вопросов!")
        return

    # Проверяем, не отвечал ли уже пользователь на этот вопрос
    if await db.check_if_answered(message.from_user.id, question_id):
        next_question = None
        next_time = None
        for qid, q in QUESTIONS.items():
            if qid > question_id:
                next_question = q
                next_time = q['start_time']
                break

        if next_time:
            time_str = next_time.strftime('%H:%M:%S')
            await message.answer(f"Вы уже ответили на текущий вопрос! Следующий вопрос будет доступен в {time_str}")
        else:
            await message.answer("Вы уже ответили на текущий вопрос! Ожидайте следующий.")
        return

    user_answer = message.text.lower().strip()

    try:
        # Если это финальный вопрос (6-й)
        if question_id == 6:
            await db.save_answer(
                user_id=message.from_user.id,
                question_id=question_id,
                answer=user_answer,
                is_correct=None  # для финального вопроса не определяем правильность
            )
            await message.answer("Ответ принят! Результаты будут объявлены 12 февраля.")
            return

        # Для остальных вопросов проверяем правильность
        is_correct = user_answer == active_question['correct_answer']
        await db.save_answer(
            user_id=message.from_user.id,
            question_id=question_id,
            answer=user_answer,
            is_correct=is_correct
        )

        if is_correct:
            await message.answer(active_question['correct_answer_text'])
            if 'image_correct' in active_question:
                with open(active_question['image_correct'], 'rb') as photo:
                    await message.answer_photo(photo)
        else:
            await message.answer(active_question['wrong_answer_text'])

    except Exception as e:
        error_msg = f"Error processing answer: {e}"
        logging.error(error_msg)
        await message.answer("Произошла ошибка при обработке ответа. Пожалуйста, попробуйте еще раз.")
        await notify_admin(bot, f"Ошибка при обработке ответа от {message.from_user.id}: {e}")


async def main():
    try:
        global scheduler_task  # Добавьте эту строку

        # Настройка базового логирования
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Инициализация базы данных
        await db.init()

        # Сброс времен вопросов при запуске
        logging.info("Resetting question times...")
        reset_times()

        # Уведомляем админов о запуске бота
        await notify_admin(bot, "🚀 Бот запущен и готов к работе")

        # Запуск планировщика
        logging.info("Creating scheduler...")
        scheduler = Scheduler(bot, db)
        logging.info("Starting scheduler...")
        scheduler_task = asyncio.create_task(scheduler.start())  # Сохраняем задачу в глобальную переменную
        logging.info("Scheduler task created")

        # Запуск бота
        logging.info("Starting polling...")
        await dp.start_polling()

    except Exception as e:
        logging.error(f"Critical error: {e}", exc_info=True)
        await notify_admin(bot, f"❌ Критическая ошибка: {e}")
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
    except Exception as e:
        logging.error(f"Fatal error: {e}")