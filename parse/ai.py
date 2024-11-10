from asyncio import timeout

import constants
from openai import OpenAI

client = OpenAI(api_key=constants.OPENAI_UKRSALON_API_KEY)
model = 'gpt-4o-mini'
timeout = 5

def reorder_names(fio: str) -> str:
    completion = client.chat.completions.create(
        model= model,
        messages=[
            {'role': 'system', 'content': 'Ты дотошный нотариус'},  # <-- This is the system message that provides context to the model
            {'role': 'user', 'content': 'Тебе необходимо записать в правильной последовательности данные клиента. '
                                        'Последовательность такая:\nФамилия Имя Отчество\n'
                                        'В ответе надо указать ИСКЛЮЧИТЕЛЬНО Фамилию Имя Отчество клиента.\n'
                                        'Если какой-то из элеметов ФИО отсутсвует, то его не надо указывать.\n'
                                        'Если в переданных данных присутсвует какое-то посторонее слово, '
                                        'кроме фамилии, имени, отчества, тогда твой ответ - это пустая строка '
                                        '(не нужно передавать часть слов или символов!) .\n'
                                        'Итак, вот данные клиента:\n'
                                        '{fio}'.format(fio=fio)}   # <-- This is the user message for which the model will generate a response
        ],
        timeout=timeout
    )

    answer = completion.choices[0].message.content
    return answer
