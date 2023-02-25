import logging
import os
import sys
import time
from logging import StreamHandler

import requests
import telegram
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
    '''Проверяет наличие токенов и данных о чате'''
    if TELEGRAM_TOKEN == None:
        logger.critical('Отсутствует TELEGRAM_TOKEN, проверьте файл .env')
        raise Exception('Отсутствует TELEGRAM_TOKEN, проверьте файл .env')
    if PRACTICUM_TOKEN == None:
        logger.critical('Отсутствует PRACTICUM_TOKEN, проверьте файл .env')
        raise Exception('Отсутствует PRACTICUM_TOKEN, проверьте файл .env')
    if TELEGRAM_CHAT_ID == None:
        logger.critical('Отсутствует TELEGRAM_CHAT_ID, проверьте файл .env')
        raise Exception('Отсутствует TELEGRAM_CHAT_ID, проверьте файл .env')


def send_message(bot, message):
    '''Отправка сообщения от бота пользователю'''
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение отправлено')
    except telegram.error.TelegramError as error:
        logger.error(f'Сообщение не было отправлено - {error}')


def get_api_answer(timestamp):
    '''Делает запрос к API практикума, возвращает ответ, изменяет параметр TIME'''
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS,
                                params=payload)
        if response.status_code != 200:
            logger.error('Эндпоинт не доступен')
            send_message(bot=telegram.Bot(token=TELEGRAM_TOKEN),
                         message='Эндпоинт не доступен')
            raise PracticumApiErrorException
        return response.json()
    except RequestException as error:
        raise PracticumApiErrorException(error)




def check_response(response):
    '''Проверяет полученный от API ответ на соответствие документации'''
    if not isinstance(response, dict):
        logger.error('Response не является словарем ', response)
        send_message(bot=telegram.Bot(token=TELEGRAM_TOKEN),
                     message='Response не является словарем')
        raise TypeError('Response не является словарем')
    elif "homeworks" not in response:
        logger.error('В ответе API отсутствует ключ homeworks ', response)
        send_message(bot=telegram.Bot(token=TELEGRAM_TOKEN),
                     message='В ответе API отсутствует ключ homeworks')
        raise PracticumApiErrorException('В ответе API отсутствует ключ homeworks')
    elif not isinstance(response["homeworks"], list):
        logger.error('Неверный тип данных у элемента homeworks ', response)
        send_message(bot=telegram.Bot(token=TELEGRAM_TOKEN),
                     message='Неверный тип данных у элемента homeworks')
        raise TypeError('Неверный тип данных у элемента homeworks')
    return True


def parse_status(homework):
    '''Проверяет статус работы возвращает строку для сообщения'''
    try:
        if 'homework_name' not in homework:
            logger.error('В ответе API нет ключа homework_name ', homework)
            send_message(bot=telegram.Bot(token=TELEGRAM_TOKEN),
                         message='В ответе API нет ключа homework_name')
            raise Exception('В ответе API нет ключа homework_name')
        homework_name = homework['homework_name']
        verdict = HOMEWORK_VERDICTS[homework['status']]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    except KeyError as error:
        message = f'Получен некорректный ключ от практикума {error}'
        send_message(telegram.Bot(token=TELEGRAM_TOKEN), message)
        logger.error(message, homework)
        raise KeyError('Получен некорректный ключ от практикума')


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    logger.debug('Бот запущен')
    timestamp = int(time.time())
    temp_error = None
    while True:
        try:
            response = get_api_answer(timestamp)
            logger.debug('Дынные запрошены у API')
            if len(response.get('homeworks')) > 0 and check_response(response):
                send_message(bot, parse_status(response.get('homeworks')[0]))
            else:
                logger.debug("Статусы не обновились на данный момент.")
            timestamp = response['current_date']
            time.sleep(RETRY_PERIOD)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.exception(message)
            if error != temp_error:
                bot.send_message(message)
            temp_error = error


if __name__ == '__main__':
    main()
