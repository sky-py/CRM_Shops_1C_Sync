from openai import OpenAI
import constants

client = OpenAI(api_key=constants.OPENAI_UKRSALON_API_KEY)
model = 'gpt-4o-mini'
timeout = 5

def ai_reorder_names(fio: str) -> str:
    completion = client.chat.completions.create(
        model= model,
        messages=[
            {'role': 'system', 'content': 'Ты дотошный нотариус'},
            {'role': 'user', 'content': 'Тебе необходимо записать в правильной последовательности данные клиента. '
                                        'Последовательность такая:\nФамилия Имя Отчество\n'
                                        'В ответе надо указать ИСКЛЮЧИТЕЛЬНО Фамилию Имя Отчество клиента.\n'
                                        'Если какой-то из элеметов ФИО отсутсвует, то его не надо указывать.\n'
                                        'Если в переданных данных присутсвует какое-то посторонее слово, '
                                        'кроме фамилии, имени, отчества, тогда твой ответ - это пустая строка. '
                                        'НЕ НУЖНО ПЕРЕДАВАТЬ ЧАСТЬ СЛОВ ИЛИ СИМВОЛОВ! Ты либо передаёшь ВСЕ слова '
                                        'в правильной последовательности, либо пустую строку!\n'
                                        'НЕ НУЖНО ВКЛЮЧАТЬ В ОТВЕТ ОБЪЯСНЕНИЯ!\n'
                                        },
            {'role': 'user', 'content': fio},

        ],
        timeout=timeout
    )

    answer = completion.choices[0].message.content
    return answer
