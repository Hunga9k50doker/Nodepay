from colorama import Fore, Style
import asyncio
import requests
import time
import uuid
from loguru import logger
import sys
import logging

logging.disable(logging.ERROR)

PING_INTERVAL = 180
RETRIES = 120
TOKEN_FILE = 'data.txt'

DOMAIN_API = {
    "SESSION": "https://api.nodepay.org/api/auth/session?",
    "PING": "https://nw.nodepay.org/api/network/ping"
}

CONNECTION_STATES = {
    "CONNECTED": 1,
    "DISCONNECTED": 2,
    "NONE_CONNECTION": 3
}

status_connect = CONNECTION_STATES["NONE_CONNECTION"]
browser_id = None
account_info = {}
last_ping_time = {}


def uuidv4():
    return str(uuid.uuid4())


def valid_resp(resp):
    if not resp or "code" not in resp or resp["code"] < 0:
        raise ValueError("Invalid response")
    return resp


async def render_profile_info(token):
    global browser_id, account_info

    try:
        np_session_info = load_session_info()

        if not np_session_info:
            browser_id = uuidv4()
            response = await call_api(DOMAIN_API["SESSION"], {}, token)
            if response is None:
                logger.info("Skipping due to 403 error.")
                return
            valid_resp(response)
            account_info = response["data"]
            if account_info.get("uid"):
                save_session_info(account_info)
                await start_ping(token)
            else:
                handle_logout()
        else:
            account_info = np_session_info
            await start_ping(token)
    except Exception as e:
        logger.error(f"Error in render_profile_info: {e}")


async def call_api(url, data, token, max_retries=3):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://app.nodepay.ai"
    }

    for attempt in range(max_retries):
        try:
            loop = asyncio.get_running_loop()
            response_json = await loop.run_in_executor(None, make_request, url, data, headers)
            return valid_resp(response_json)
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on attempt {attempt + 1}: {e}")
            if e.response.status_code == 403:
                logger.error(f"403 Forbidden encountered on attempt {attempt + 1}: {e}")
                return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error on attempt {attempt + 1}: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout on attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")

        await asyncio.sleep(2 ** attempt)

    logger.error(f"Failed API call to {url} after {max_retries} attempts")
    return None


def make_request(url, data, headers):
    response = requests.post(url, json=data, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


async def start_ping(token):
    try:
        while True:
            await ping(token)
            await asyncio.sleep(PING_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Ping task was cancelled")
    except Exception as e:
        logger.error(f"Error in start_ping: {e}")


async def ping(token):
    global last_ping_time, RETRIES, status_connect
    current_time = time.time()
    if "last_ping" in last_ping_time and (current_time - last_ping_time["last_ping"]) < PING_INTERVAL:
        logger.info("Skipping ping, not enough time elapsed")
        return

    last_ping_time["last_ping"] = current_time

    try:
        data = {
            "id": account_info.get("uid"),
            "browser_id": browser_id,
            "timestamp": int(time.time())
        }

        response = await call_api(DOMAIN_API["PING"], data, token)

        if response["code"] == 0:
            logger.info(f"{Fore.GREEN}Ping thành công...")
            logger.info(f"{Fore.MAGENTA}Node đang chạy với điểm kết nối {response['data']['ip_score']}%...")
            RETRIES = 0
            status_connect = CONNECTION_STATES["CONNECTED"]
        else:
            handle_ping_fail(response)
    except Exception as e:
        logger.error(f"Ping không thành công: {e}")
        if(RETRIES == 0):
            logger.info("Đang thử kết nối lại...")
            RETRIES += 1
            await start_ping(token)
        else:
            RETRIES = 0
            handle_ping_fail(None)


def handle_ping_fail(response):
    global RETRIES, status_connect

    RETRIES += 1
    if response and response.get("code") == 403:
        handle_logout()
    elif RETRIES < 2:
        status_connect = CONNECTION_STATES["DISCONNECTED"]
    else:
        status_connect = CONNECTION_STATES["DISCONNECTED"]


def handle_logout():
    global status_connect, account_info

    status_connect = CONNECTION_STATES["NONE_CONNECTION"]
    account_info = {}
    logger.info("Đã đăng xuất và xóa thông tin phiên")


def load_session_info():
    return {}


def save_session_info(data):
    data_to_save = {
        "uid": data.get("uid"),
        "browser_id": browser_id
    }
    # Lưu thông tin phiên nếu cần
    pass


async def send_data_to_server(url, data, token):
    response = await call_api(url, data, token)

    if response is not None:
        logger.info("Gửi yêu cầu đăng nhập")
    else:
        logger.error("Không nhận được phản hồi.")
        logger.info(f"{Fore.BLUE}Đang thử kết nối lại...")


async def main():
    logger.info(f"{Fore.YELLOW}Tool được phát triển bởi nhóm tele Airdrop Hunter Siêu Tốc {Style.RESET_ALL}")

    url = "https://api.nodepay.org/api/auth/session?"
    data = {
        "cache-control": "no-cache, no-store, max-age=0, must-revalidate",
        "cf-cache-status": "DYNAMIC",
        "cf-ray": "8db8aaa27b6fd487-NRT",
        "ary": "origin,access-control-request-method,access-control-request-headers,accept-encoding",
    }

    tokens = load_tokens_from_file(TOKEN_FILE)

    for token in tokens:
        await send_data_to_server(url, data, token)
        await asyncio.sleep(10)

    while True:
        for token in tokens:
            await render_profile_info(token)
            await asyncio.sleep(3)
        await asyncio.sleep(10)


def load_tokens_from_file(filename):
    try:
        with open(filename, 'r') as file:
            tokens = file.read().splitlines()
        return tokens
    except Exception as e:
        logger.error(f"Không đọc được token: {e}")
        raise SystemExit("Dừng code...")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Tool đã dừng thủ công.")