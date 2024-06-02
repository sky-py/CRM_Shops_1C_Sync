import os
import telebot
from dotenv import load_dotenv

load_dotenv('c:/Scripts/env/tg.env')

admin_tg = os.getenv('admin_tg')
tg_token_salon = os.getenv('tg_token_salon')
tg_token_tools = os.getenv('tg_token_tools')
DO_SEND_TO_BOT = True if os.getenv('DO_SEND_TO_BOT') == 'True' else False

bot = telebot.TeleBot(tg_token_salon)
bot_tools = telebot.TeleBot(tg_token_tools)


def send_tg_message(text: str, *users: int):
    if DO_SEND_TO_BOT:
        for user in users:
            try:
                bot.send_message(user, text)
            except:
                bot_tools.send_message(admin_tg, f'Ошибка отправки сообщения пользователю {user}')
        bot.send_message(admin_tg, text)
    else:
        print('===TEST=== ', text)


def send_service_tg_message(text: str):
    if DO_SEND_TO_BOT:
        bot_tools.send_message(admin_tg, text)
