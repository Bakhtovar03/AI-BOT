from aiogram.types import Message, CallbackQuery
from aiogram import F,Router
from aiogram.filters import Command,CommandStart
from lexicon.lexicon import COMMAND_LEXICON

user_router = Router()

@user_router.message(CommandStart())
async def start(message: Message):
    await message.answer(COMMAND_LEXICON[message.text])

