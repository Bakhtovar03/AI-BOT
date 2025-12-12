from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message, CallbackQuery, InputMediaVideo, InputMediaPhoto
from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from lexicon.lexicon import COMMAND_LEXICON, OTHER_LEXICON
from LLM.llm import ask_giga_chat_async, redis_client
from keyboards.inlinekeyboards import create_inline_keyboards


user_router = Router()

# Фильтр: хэндлеры обрабатывают сообщения только в default_state
user_router.message.filter(StateFilter(default_state))

# -------------------- ХЭНДЛЕРЫ --------------------


# /start — приветственное сообщение с кнопками
@user_router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        text=COMMAND_LEXICON[message.text],  # текст из словаря COMMAND_LEXICON
        reply_markup=create_inline_keyboards(
            'sign_up',       # кнопка "Записаться на курс"
            'consultation',   # кнопка "Консультация"
            'view_media'    # кнопка для просмотра фото и видео с занятий
        )
    )


# Обработка нажатия кнопки "Записаться на курс"
@user_router.callback_query(F.data=='sign_up')
async def sign_up_for_classes(callback_query: CallbackQuery):
    await callback_query.message.answer(text=OTHER_LEXICON['sign up for a course'])
    await callback_query.answer()  # убираем "часики" в интерфейсе Telegram


# Обработка нажатия кнопки "Консультация"
@user_router.callback_query(F.data=='consultation')
async def consultation_response(callback_query: CallbackQuery):
    await callback_query.message.answer(OTHER_LEXICON['consultation'])
    await callback_query.answer()  # убираем "часики"


# Ответы через LLM на любые текстовые сообщения
@user_router.message(F.text)
async def llm_response(message: Message):
    # Генерируем ответ через GigaChat
    response = await ask_giga_chat_async(message.text, str(message.from_user.id))
    await message.answer(
        text=response,
        reply_markup=create_inline_keyboards('sign_up','view_media')
    )


# Обработка нажатия кнопки "Посмотреть фото и видео с занятий"
@user_router.callback_query(F.data=='view_media')
async def view_media_response(callback_query: CallbackQuery):
    redis_client = getattr(callback_query.bot,'redis_client')
    photos = await redis_client.lrange('photos',0,-1)
    videos = await redis_client.lrange('videos',0,-1)

    videos = [InputMediaVideo(media=vid) for vid in videos]
    photos = [InputMediaPhoto(media=photo) for photo in photos]
    media = videos+photos
    # Если в списке media от 2 до 10 элементов — отправляем их как медиа-группу
    # Telegram API позволяет отправлять одновременно максимум 10 и минимум 2 элементов как группу
    if 1 < len(media) <= 10:
        await callback_query.message.answer_media_group(media)
    elif len(media) >10:
        for i in range(0,len(media),10): # если больше 10 - разбиваем на части
            await callback_query.message.answer_media_group(media[i:i+10])

    else:
        # Обрабатываем все остальные случаи с помощью match-case
        match len(media):
            case 0:
                # Если список media пуст — информируем пользователя
                await callback_query.message.answer("Нет медиа для отображения.")
            case 1:
                # Если только один элемент — нужно проверить его тип
                # и отправить соответствующим методом (отдельное фото или видео)
                match media[0]:
                    case InputMediaPhoto():
                        # Отправляем фотографию
                        await callback_query.message.answer_photo(media[0].media)
                    case InputMediaVideo():
                        # Отправляем видео
                        await callback_query.message.answer_video(media[0].media)

    await callback_query.answer()

# Обработка сообщений, которые не являются текстом
@user_router.message()
async def default_response(message: Message):
    await message.answer('Извините, я отвечаю только на текстовые сообщения')
