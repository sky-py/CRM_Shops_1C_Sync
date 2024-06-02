import xml.etree.cElementTree as ET
import datetime
from pathlib import Path

xml_file = Path('c:/Quad Solutions/files/1_ main/ukrstil_ua.xml')
root = None


def is_time(hour: int = None, minute: int = None) -> bool:
    """
    Checks if the current time is within a 10-minute window after the specified hour and minute.

    :param hour: The hour to check against (defaults to the current hour).
    :param minute: The minute to check against (defaults to 0).
    :return: True if the current time falls within the 10-minute window, False otherwise.
    :rtype: bool
    """

    if minute is None:
        minute = 0
    if hour is None:
        hour = datetime.datetime.now().hour
    close_time = datetime.datetime.combine(datetime.datetime.today(), datetime.time(hour=hour, minute=minute))
    if close_time < datetime.datetime.now() < close_time + datetime.timedelta(minutes=2):
        return True
    else:
        return False


def get_xml_root(xml_file: Path | str):
    tree = ET.parse(xml_file)
    return tree.getroot()


def get_name_by_sku(sku: str):
    global root
    if root is None or is_time(minute=0):
        root = get_xml_root(xml_file)

    for offer in root.findall(".//offer"):
        sku_tag = offer.find('vendorCode')
        name_tag = offer.find('name')
        if sku_tag is not None and name_tag is not None:
            if sku_tag.text.lower() == sku.lower():
                return name_tag.text


