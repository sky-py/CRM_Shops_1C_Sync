# This mudule is for sending service sync messages through sync telegram library

from typing import Iterable
import telebot
from constants import DO_SEND_TO_BOT, TG_MAX_MESSAGE_LENGTH, admin_tg, tg_token_salon, tg_token_tools

bot = telebot.TeleBot(tg_token_salon)
bot_tools = telebot.TeleBot(tg_token_tools)


def send_tg_message(text: str, users: Iterable[int]):
    text = text[0:TG_MAX_MESSAGE_LENGTH]
    if DO_SEND_TO_BOT:
        for user in users:
            try:
                bot.send_message(user, text)
            except:
                send_service_tg_message(f'Ошибка отправки сообщения пользователю {user}')
        bot.send_message(admin_tg, text)
    else:
        print('===TEST=== ', text)


def send_service_tg_message(text: str):
    text = text[0:TG_MAX_MESSAGE_LENGTH]
    if DO_SEND_TO_BOT:
        bot_tools.send_message(admin_tg, text)
