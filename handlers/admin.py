from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import StatesGroup, State, default_state
from aiogram.types import Message, CallbackQuery, InputMediaPhoto, InputMediaVideo, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
import secrets
from LLM.llm import redis_client
from keyboards.keyboards import create_keyboards
from lexicon.lexicon import ADMIN_BUTTON_LEXICON
from utils import IsAdmin
from keyboards.inlinekeyboards import create_inline_keyboards, create_inline_keyboards_callback

# Создаем роутер для админ-команд
admin_router = Router()

# Список ID админов

admin_list = [5393901453]


# Фильтр, чтобы проверять админов

admin_router.message.filter(IsAdmin(admin_list=admin_list,redis_set='admins',))

# FSM для админ-панели
class FSMAdmin(StatesGroup):
    admin_panel = State()       # Главное меню админа
    add_video = State()         # Состояние добавления видео
    add_photo = State()         # Состояние добавления фото
    add_new_admin = State()     # Состояние добавления нового админа
    delete_admin = State()      # Состояние удаления админа
    delete_photo = State()      # Состояние удаления фото
    delete_video = State()      # Состояние удаления видео
# -------------------- ХЭНДЛЕРЫ --------------------

# /admin — показать панель администратора
@admin_router.message(Command(commands='admin'), StateFilter(default_state))
async def admin_buttons(message: Message, state: FSMContext):
    button_list = [value for key, value in ADMIN_BUTTON_LEXICON.items()]
    await message.answer(
        text='Панель Администратора',
        reply_markup=create_keyboards(button_list, 2).as_markup(resize_keyboard=True)
    )
    await state.set_state(FSMAdmin.admin_panel)


@admin_router.message(F.text=='выйти из админ-панели', StateFilter(FSMAdmin.admin_panel))
async def user_panel(message: Message, state: FSMContext):
    await message.answer('Вы вышли из панели администратора.\n'
                         'Что бы вернуться в админ-режим введите команду /admin ',reply_markup=ReplyKeyboardRemove())
    await state.clear()



# запрос на добавления нового админа
@admin_router.message(F.text == ADMIN_BUTTON_LEXICON['add_new_admin'] , StateFilter(FSMAdmin.admin_panel))
async def add_new_admin(message: Message, state: FSMContext):

    await message.answer(
        'Перешлите мне любое сообщения от пользователя '
             'которому хотите выдать админ-права',
              reply_markup=create_keyboards(['отмена'], 2).as_markup(resize_keyboard=True))
    await state.set_state(FSMAdmin.add_new_admin)


# добавления админа
@admin_router.message(F.text !='отмена',StateFilter(FSMAdmin.add_new_admin))
async def save_new_admin(message: Message, state: FSMContext):
    redis_client = getattr(message.bot, 'redis_client')
    if message.forward_from:
        user_id = message.forward_from.id
        await redis_client.sadd('admins', user_id)
        await message.answer(
            'Новый Администратор успешно добавлен!',
            reply_markup=create_keyboards(['ок'], 2).as_markup(resize_keyboard=True)
        )
        await state.set_state(FSMAdmin.admin_panel)
    else:
        await message.answer(
            'на данном шаге нужно переслать любое сообщение от пользователя '
            'которого хотите назначить администратором',
            reply_markup=create_keyboards(['отмена'], 2).as_markup(resize_keyboard=True)
        )

# запрос на удаления админа бота
@admin_router.message(F.text=='Удалить админа бота',StateFilter(FSMAdmin.admin_panel))
async def response_delete_admin(message: Message, state: FSMContext):
    redis_client = getattr(message.bot, 'redis_client')
    admin_ids = await redis_client.smembers('admins')
    admins_names =[]

    if admin_ids:
        for admin_id in admin_ids:
            admin = await  message.bot.get_chat(admin_id)
            admins_names.append(admin.first_name)

        admin_id_and_name = dict(zip(admin_ids, admins_names))

        await message.answer(
            'Выберите админа которого хотите удалить:',
            reply_markup=create_inline_keyboards_callback(admin_id_and_name)
        )
        await message.answer(text='Нажмите на кнопку с именем админа которого нужно удалить',
            reply_markup=create_keyboards(["отмена"], 1).as_markup(resize_keyboard=True))

        await state.set_state(FSMAdmin.delete_admin)
    else:
        await message.answer('Список админов пуст')


# Обработчик callback запроса для удаления администратора
@admin_router.callback_query(F.data, FSMAdmin.delete_admin)
async def delete_admin(callback: CallbackQuery, state: FSMContext):
    # Получаем объект Redis из бота
    redis_client = getattr(callback.bot, 'redis_client')

    # Получаем ID администратора из callback data
    admin_id = callback.data

    # Проверяем, что admin_id является числом
    if not admin_id.isdigit():
        # Если нет, отправляем пользователю сообщение
        await callback.message.answer("Выберите администратора которого хотите удалить из списка выше")
        await callback.answer()  # Завершаем callback
        return

    # Преобразуем admin_id в число
    admin_id = int(admin_id)

    # Получаем объект чата администратора
    name = await callback.bot.get_chat(admin_id)

    # Проверяем, есть ли этот админ в Redis
    is_admin = await redis_client.sismember('admins', admin_id)

    if not is_admin:
        # Если админа нет в списке, отправляем сообщение
        await callback.message.answer("Выберите администратора которого хотите удалить из списка выше")
        await callback.answer()
        return

    # Удаляем администратора из Redis
    await redis_client.srem('admins', admin_id)

    # Отправляем сообщение пользователю о том, что админ удален
    await callback.message.answer(
        f'{name.first_name} Больше не является Администратором',
        reply_markup=create_keyboards(["ок"], 1).as_markup(resize_keyboard=True)
    )

    # Завершаем callback
    await callback.answer()

    # Возвращаем состояние в панель администратора
    await state.set_state(FSMAdmin.admin_panel)


# Просмотр всех фотографий из базы Redis
@admin_router.message(F.text == ADMIN_BUTTON_LEXICON['get_photos'], StateFilter(FSMAdmin.admin_panel))
async def get_photos(message: Message, state: FSMContext):
    redis_client = getattr(message.bot, 'redis_client')
    photo_list = await redis_client.lrange("photos", 0, -1)
    if not photo_list:
        await message.answer("фотографий пока нет.")
        return
    else:
        media = [InputMediaPhoto(media=pid) for pid in photo_list]
        await message.answer_media_group(media)

# Просмотр всех видео из Redis
@admin_router.message(F.text == ADMIN_BUTTON_LEXICON['get_videos'], StateFilter(FSMAdmin.admin_panel))
async def get_videos(message: Message, state: FSMContext):
    redis_client = getattr(message.bot, 'redis_client')
    video_list = await redis_client.lrange("videos", 0, -1)
    if not video_list:
        await message.answer("Видео пока нет.")
        return
    else:
        media = [InputMediaVideo(media=vid) for vid in video_list]
        await message.answer_media_group(media)


# Начало добавления видео
@admin_router.message(F.text==ADMIN_BUTTON_LEXICON['add_video'], StateFilter(FSMAdmin.admin_panel))
async def add_video(message: Message, state: FSMContext):
    await message.answer(
        text='Отправьте мне видео которое хотите добавить',
        reply_markup=create_keyboards(["отмена"], 1).as_markup(resize_keyboard=True)
    )
    await state.set_state(FSMAdmin.add_video)

# Сохранение видео
@admin_router.message(F.content_type == 'video', StateFilter(FSMAdmin.add_video))
async def save_video(message: Message, state: FSMContext):
    redis_client = getattr(message.bot, 'redis_client')
    video_list = await redis_client.lrange("videos", 0, -1)
    if len(video_list)>=10:
        await message.answer("Количество видео в хранилище достигло 10 шт,"
                             "Сначала удалите один из старых видео ")

    else:
        video_id = message.video.file_id
        await redis_client.rpush('videos', video_id)
        await message.answer(
        'Видео успешно сохранено!',
        reply_markup=create_keyboards(["ок"],1).as_markup(resize_keyboard=True)
    )
    await state.set_state(FSMAdmin.admin_panel)


# запрос на удаление видео
@admin_router.message(F.text == ADMIN_BUTTON_LEXICON['delete_video'], StateFilter(FSMAdmin.admin_panel))
async def request_for_remove_video(message: Message, state: FSMContext):
    redis_client = getattr(message.bot, 'redis_client')
    video_list = await redis_client.lrange("videos", 0, -1)
    if not video_list:
        await message.answer('видеоматериалов нет, удалять нечего')
    else:
        media = [InputMediaVideo(media=pid) for pid in video_list]
        await message.answer_media_group(media)
        await message.answer(
            'Введите порядковый номер видео который хотите удалить',
            reply_markup=create_keyboards(["отмена"],1).as_markup(resize_keyboard=True)
        )
        await state.set_state(FSMAdmin.delete_video)


# удаление видео
@admin_router.message(~F.text != 'отмена', StateFilter(FSMAdmin.delete_video))
async def delete_video(message: Message, state: FSMContext):
    if message.text.isdigit() and (0 < int(message.text) <= 10):
        redis_client = getattr(message.bot, 'redis_client')
        delete_video_id = await redis_client.lindex('videos', int(message.text)-1)
        if delete_video_id:
            await message.answer('Вы удалили данное видео:')
            await message.answer_video(delete_video_id)
            await redis_client.lrem('videos', 1, delete_video_id)
            await state.set_state(FSMAdmin.admin_panel)
            button_list = [value for key, value in ADMIN_BUTTON_LEXICON.items()]
            await message.answer('Панель Администратора',
                reply_markup = create_keyboards(button_list,2).as_markup(resize_keyboard=True)
            )
    else:
        await message.answer(
            "Видео под таким индексом нет",
            reply_markup = create_keyboards(["отмена"], 1).as_markup(resize_keyboard=True)
        )



# запрос на удаление фото
@admin_router.message(F.text == ADMIN_BUTTON_LEXICON['delete_photo'], StateFilter(FSMAdmin.admin_panel))
async def request_for_remove_photo(message: Message, state: FSMContext):
    redis_client = getattr(message.bot, 'redis_client')
    photo_list = await redis_client.lrange("photos", 0, -1)
    if not photo_list:
        await message.answer('фотографий нет, удалять нечего')
    else:
        media = [InputMediaPhoto(media=pid) for pid in photo_list]
        await message.answer_media_group(media)
        await message.answer(
            'Введите порядковый номер фото которого хотите удалить',
            reply_markup=create_keyboards(["отмена"],1).as_markup(resize_keyboard=True)
        )
        await state.set_state(FSMAdmin.delete_photo)

# удаление фото
@admin_router.message(F.text != 'отмена', StateFilter(FSMAdmin.delete_photo))
async def delete_video(message: Message, state: FSMContext):
    if message.text.isdigit() and (0 < int(message.text) <= 10):
        redis_client = getattr(message.bot, 'redis_client')
        delete_photo_id = await redis_client.lindex('photos', int(message.text)-1)
        if delete_photo_id:
            await message.answer('Вы удалили данное фото:')
            await message.answer_photo(delete_photo_id)
            await redis_client.lrem('photos', 1, delete_photo_id)

            button_list = [value for key, value in ADMIN_BUTTON_LEXICON.items()]
            await message.answer(
                'Панель Администратора',
                reply_markup=create_keyboards(button_list, 2).as_markup(resize_keyboard=True)

            )
            await state.set_state(FSMAdmin.admin_panel)

    else:
        await message.answer(
            "фотографии под таким индексом нет",
            reply_markup=create_keyboards(["отмена"], 1).as_markup(resize_keyboard=True)
                             )

# Начало добавления фото
@admin_router.message(F.text ==ADMIN_BUTTON_LEXICON['add_photo'], StateFilter(FSMAdmin.admin_panel))
async def add_photo(message: Message, state: FSMContext):
    await message.answer(
        'Отправьте мне фотографию которою хотите добавить',
        reply_markup=create_keyboards(["отмена"], 1).as_markup(resize_keyboard=True)
    )
    await state.set_state(FSMAdmin.add_photo)

# Сохранение фото в Redis
@admin_router.message(F.content_type == 'photo', StateFilter(FSMAdmin.add_photo))
async def save_photo(message: Message, state: FSMContext):
    redis_client = getattr(message.bot,'redis_client')
    photo_list = await redis_client.lrange("photos", 0, -1)
    if len(photo_list)>=10:
        await message.answer("Количество фотографий в хранилище достигло 10 шт,"
                             "Сначала удалите один из старых видео ")
    else:
        photo_id = message.photo[-1].file_id
        await redis_client.rpush('photos', photo_id)
        await message.answer(
        'Фотография успешно сохранена!',
        reply_markup=create_keyboards(["ок"], 1).as_markup(resize_keyboard=True)
    )
    await state.set_state(FSMAdmin.admin_panel)



# Отмена текущего действия
@admin_router.message(F.text.in_(['отмена','ок']), ~StateFilter([default_state, FSMAdmin.admin_panel]))
async def cancel_action(message: Message, state: FSMContext):
    button_list = [value for key, value in ADMIN_BUTTON_LEXICON.items()]
    await message.answer(
        'Панель Администратора',
        reply_markup=create_keyboards(button_list, 2).as_markup(resize_keyboard=True)
    )
    await state.set_state(FSMAdmin.admin_panel)

# Ошибка при отправке не видео вместо видео
@admin_router.message(StateFilter(FSMAdmin.add_video))
async def error_save_video(message: Message, state: FSMContext):
    await message.answer(
        'Это не видео)',
        reply_markup=create_keyboards(["отмена"], 1).as_markup(resize_keyboard=True)
    )

# Ошибка при отправке не фото вместо фото
@admin_router.message(StateFilter(FSMAdmin.add_photo))
async def error_save_photo(message: Message, state: FSMContext):
    await message.answer(
        'Это не фотография)',
        reply_markup = create_keyboards(["отмена"], 1).as_markup(resize_keyboard=True)
    )
