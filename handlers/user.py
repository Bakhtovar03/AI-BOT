

from aiogram.types import Message, CallbackQuery
from aiogram import F,Router
from aiogram.filters import Command,CommandStart
from lexicon.lexicon import COMMAND_LEXICON
from LLM.llm import ask_giga_chat_sync
user_router = Router()

@user_router.message(CommandStart())
async def start(message: Message):
    await message.answer(COMMAND_LEXICON[message.text])

@user_router.message(F.text)
async def llm_response(message: Message):
    await message.answer(ask_giga_chat_sync(message.text))