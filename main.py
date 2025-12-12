import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import redis.asyncio as redis
from aiogram.fsm.storage.redis import RedisStorage


from config.config import load_config
from handlers.user import user_router
from handlers.admin import admin_router

# Логгер для вывода информации о работе бота
logger = logging.getLogger(__name__)

async def main():


    # Подключаем Redis для хранения данных (например, фотографий)
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_client = redis.Redis(host=redis_host, port=redis_port,decode_responses=True)
    storage = RedisStorage(redis_client)

    # Создаем диспетчер для хэндлеров
    dp = Dispatcher(storage=storage)
    # Загружаем конфиг
    config = load_config()

    # Настройка логирования
    logging.basicConfig(
        level=logging.getLevelName(level=config.log.level),
        format=config.log.format,
    )

    # Создаем объект бота
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),  # HTML-разметка по умолчанию
    )

    logger.info('Starting bot')

    # Подключаем роутеры (админ и пользователь)
    dp.include_router(admin_router)
    dp.include_router(user_router)

    setattr(bot, 'redis_client', redis_client)  # сохраняем клиент Redis в объекте бота

    # Запуск polling (бот начинает получать сообщения)
    await dp.start_polling(bot)

# Точка входа
if __name__ == '__main__':
    asyncio.run(main())
