from gc import callbacks

from aiogram.types import Message, CallbackQuery
from aiogram import F,Router
from aiogram.filters import Command,CommandStart
from lexicon.lexicon import COMMAND_LEXICON,OTHER_LEXICON
from LLM.llm import ask_giga_chat
from keyboards.inlinekeyboards import create_inline_keyboards
user_router = Router()

@user_router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        text=COMMAND_LEXICON[message.text],
        reply_markup=create_inline_keyboards(
            'sign_up',
            'consultation'
        )
    )


@user_router.callback_query(F.data=='sign_up')
async def sign_up_for_classes(callback_query: CallbackQuery):
    await callback_query.message.answer(text=OTHER_LEXICON['sign up for a course'])
    await callback_query.answer()


@user_router.callback_query(F.data=='consultation')
async def consultation_response(callback_query: CallbackQuery):

    await callback_query.message.answer(OTHER_LEXICON['consultation'])
    await callback_query.answer()

@user_router.message(F.text)
async def llm_response(message: Message):
    await message.answer(
        text=ask_giga_chat(message.text,str(message.from_user.id)),
        reply_markup=create_inline_keyboards('sign_up')
    )
@user_router.message()
async def default_response(message: Message):
    await message.answer('Извините, я отвечаю только на текстовые сообщения')