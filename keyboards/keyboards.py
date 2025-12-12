from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder



def create_keyboards(button_names: list[str],width: int) -> ReplyKeyboardBuilder:
    kb_builder= ReplyKeyboardBuilder()
    buttons = [KeyboardButton(text=f'{name}')for name in button_names]
    kb_builder.row(*buttons,width=width)
    return kb_builder

