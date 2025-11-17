import asyncio
import logging
import sys
from aiogram import Bot,Dispatcher
from aiogram.client import bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config.config import load_config
from handlers.user import user_router

logger = logging.getLogger(__name__)

async def main():
    dp =Dispatcher()
    config = load_config()
    logging.basicConfig(
        level=logging.getLevelName(level=config.log.level),
        format = config.log.format,
    )

    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    logger.info('Starting bot')

    dp.include_router(user_router)

    await dp.start_polling(bot)



if __name__ == '__main__':
    asyncio.run(main())