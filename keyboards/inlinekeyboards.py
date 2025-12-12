from aiogram.filters import callback_data
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from lexicon.lexicon import BUTTON_LEXICON


def create_inline_keyboards(*buttons: str):
    kb_builder = InlineKeyboardBuilder()
    kb_builder.row(*[
        InlineKeyboardButton(
            text=BUTTON_LEXICON.get(button,button) ,
            callback_data=str(button)
        ) for button in buttons
    ],width=1)
    return kb_builder.as_markup()
