import requests
from loguru import logger
import os
from dotenv import load_dotenv
from parse.parse_constants import TTN_SENT_BY_CAR


load_dotenv('/etc/env/sms.env')

DO_SEND_SMS = True if os.getenv('DO_SEND_SMS') == 'True' else False
sms_login = os.getenv('sms_login')
sms_password = os.getenv('sms_password')
sms_url = "https://gate.smsclub.mobi/xml/"
sms_headers = {'Content-Type': 'text/xml; charset=utf-8'}
alpha_names = [
    os.getenv('alpha_shop_zakaz'),
    os.getenv('alpha_ukrsalon'),
    os.getenv('alpha_ukrstil'),
    os.getenv('alpha_beauty'),
    os.getenv('alpha_klimazon'),
    os.getenv('alpha_krasunia'),
   ]

ttn_text_template = ('Ми відправили Ваше замовлення{by_service} '
                 'Обов"язково перевіряйте відсутність механічних пошкоджень і комплектацію, наявність всіх одиниць '
                 'товару при отриманні замовлення в присутності співробітника служби доставки. Ми не гарантуємо '
                 'вирішення спірних ситуацій з товаром на Вашу користь, якщо товар не було перевірено під час отримання'
                 )

by_car_text_template = ' машиною.'
by_post_text_template = ', ТТН {tracking_code} Відстежити: https://t.me/SalonSenderbot?start={tracking_code}s={shop_number}'

def send_ttn_sms(phone: str, tracking_code: str, shop_sql_id: int):
    """Sends SMS.
    :param phone: Phone at +38.... format.
    :param tracking_code: tracking_code
    :param shop_sql_id: Shop id in terms of 1C SQL db
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """

    alpha = alpha_names[shop_sql_id]
    service_text = (by_car_text_template if tracking_code == TTN_SENT_BY_CAR else
                    by_post_text_template.format(tracking_code=tracking_code, shop_number=shop_sql_id))
    text = ttn_text_template.format(by_service=service_text)
    return send_sms(phone=phone, alpha_name=alpha, text=text)


def send_sms(phone: str, alpha_name: str, text: str):
    """Sends SMS.

    :param phone: Phone at +38.... format.
    :param alpha_name: alpha_name
    :param text: SMS content
    :return: :class:`Response <Response>` object
    :rtype: requests.Response
    """

    phone = phone.replace('+', '')
    xml = f"""<?xml version='1.0' encoding='utf-8'?>
                <request_sendsms>
                    <username><![CDATA[{sms_login}]]></username>
                    <password><![CDATA[{sms_password}]]></password>
                    <from><![CDATA[{alpha_name}]]></from>
                    <to><![CDATA[{phone}]]></to>
                    <text><![CDATA[{text}]]></text>
                </request_sendsms>"""
    # print('sending: ', alpha_name, phone, text)
    if DO_SEND_SMS:
        r = requests.post(url=sms_url, data=xml.encode('utf-8'), headers=sms_headers)
        log_text = f'SEND SMS: {phone} | {alpha_name} => | {text} | Reply: {r.text}'
        logger.info(log_text) if r else logger.error(log_text)
        return r
    else:
        logger.info(f'TEST SEND SMS {phone} | {alpha_name} => | {text} | Reply:')

