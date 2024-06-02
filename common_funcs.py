import re


def international_phone(phone: str | None) -> str | None:
    """
    Convert a phone number to international format.

    :param phone: A string representing a phone number or None if no phone number is provided.
    :type phone: str | None

    :return: A string representing the phone number in international format or None if no phone number is provided.
    :rtype: str | None


    """
    if not phone:
        return phone

    phone = ''.join(re.findall('\\d+', str(phone)))
    if len(phone) < 9:
        return phone

    if len(phone) == 11:
        phone = phone.removeprefix('8')

    if len(phone) == 10:
        phone = phone.removeprefix('0')

    if len(phone) == 9:
        phone = '+380' + phone
    else:
        phone = '+' + phone

    return phone

