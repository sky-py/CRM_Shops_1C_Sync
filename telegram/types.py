from dataclasses import dataclass


@dataclass(slots=True)
class Notification:
    source: str
    order_id: int
    shop_name: str
    text: str
    button: bool = True
