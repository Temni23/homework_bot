import logging
import os
import sys
import time
from logging import StreamHandler

import requests
import telegram
from http import HTTPStatus
from dotenv import load_dotenv
from requests import RequestException

from exceptions import PracticumApiErrorException

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = StreamHandler(stream=sys.stdout)
logger.addHandler(handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет наличие токенов и данных о чате."""
    if TELEGRAM_TOKEN is None:
        logger.critical('Отсутствует TELEGRAM_TOKEN, проверьте файл .env')
        raise Exception('Отсутствует TELEGRAM_TOKEN, проверьте файл .env')
    # Комменария для Ревьювера: Вы писали про логи в данной функции
    # "Тут не нужно логирование, так-как оно произойдет при обработке
    # исключения в main()." Однако, при после того как я убрал логирование
    # в данной функции перестал проходить pytest
    # AssertionError: Убедитесь, что при отсутствии обязательных переменных
    # окружения событие логируется с уровнем `CRITICAL`.
    # В итоге оставил исходный вариант
    if PRACTICUM_TOKEN is None:
        logger.critical('Отсутствует PRACTICUM_TOKEN, проверьте файл .env')
        raise Exception('Отсутствует PRACTICUM_TOKEN, проверьте файл .env')
    if TELEGRAM_CHAT_ID is None:
        logger.critical('Отсутствует TELEGRAM_CHAT_ID, проверьте файл .env')
        raise Exception('Отсутствует TELEGRAM_CHAT_ID, проверьте файл .env')
    return True


def send_message(bot, message):
    """Отправка сообщения от бота пользователю."""
    try:
        logger.debug('Пробуем отправить сообщение пользователю')
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение отправлено пользователю')
    except telegram.error.TelegramError as error:
        logger.error(f'Сообщение не было отправлено - {error}')


def get_api_answer(timestamp):
    """Делает запрос к API практикума, возвращает ответ."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS,
                                params=payload)
        if response.status_code != HTTPStatus.OK:
            send_message(bot=telegram.Bot(token=TELEGRAM_TOKEN),
                         message='Эндпоинт не доступен')
            raise PracticumApiErrorException('Эндпоинт не доступен')
        return response.json()
    except RequestException as error:
        raise PracticumApiErrorException(error)


def check_response(response):
    """Проверяет полученный от API ответ на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Response не является словарем')
    if 'homeworks' not in response:
        raise PracticumApiErrorException('В ответе API '
                                         'отсутствует ключ homeworks')
    if 'current_date' not in response:
        raise PracticumApiErrorException('В ответе API '
                                         'отсутствует ключ current_date')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Неверный тип данных у homeworks')
    return homeworks


def parse_status(homework):
    """Проверяет статус работы возвращает строку для сообщения."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if 'homework_name' not in homework:
        raise Exception('В ответе API нет ключа homework_name')
    if 'status' not in homework:
        raise Exception('В ответе API нет ключа status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise Exception('В ответе API неизвестный статус задания')
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    timestamp = int(time.time())
    temp_error = None
    last_status = None
    if not check_tokens():
        sys.exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    logger.debug('Бот запущен')
    while True:
        try:
            response = get_api_answer(timestamp)
            logger.debug('Дынные запрошены у API')
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                if message != last_status:
                    send_message(bot, message)
                    last_status = message
            else:
                logger.debug('Статусы не обновились на данный момент.')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.exception(message)
            if error != temp_error:
                bot.send_message(message)
            temp_error = error
        finally:
            timestamp = int(time.time())
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
