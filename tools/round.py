from decimal import Decimal, ROUND_HALF_UP


def classic_round(number: float, decimals=0) -> float:
    # Создаем объект Decimal из числа (лучше из строки, чтобы избежать неточностей float)
    d_number = Decimal(str(number))
    # Создаем шаблон для квантования (округления)
    # '1e-' + str(decimals) создает '1e-0', '1e-1', '1e-2' и т.д.
    # что эквивалентно Decimal('1'), Decimal('0.1'), Decimal('0.01')
    exponent = Decimal('1e-' + str(decimals))
    # Округляем с использованием нужной стратегии
    return float(d_number.quantize(exponent, rounding=ROUND_HALF_UP))