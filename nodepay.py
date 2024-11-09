import asyncio
import cloudscraper
import requests
import time
import uuid
from loguru import logger
import sys
import logging
logging.disable(logging.ERROR)

# Constants
PING_INTERVAL = 180  # Time between pings (in seconds)
RETRIES = 120  # Number of retries for failed pings
TOKEN_FILE = 'data.txt'  # File containing the tokens

DOMAIN_API = {
    "SESSION": "https://api.nodepay.org/api/auth/session?",  # API endpoint for session authentication
    "PING": "https://nw.nodepay.org/api/network/ping"  # API endpoint for ping
}

CONNECTION_STATES = {
    "CONNECTED": 1,  # Represents an active connection
    "DISCONNECTED": 2,  # Represents a disconnected state
    "NONE_CONNECTION": 3  # No connection state
}

# Variables to store connection state and account information
status_connect = CONNECTION_STATES["NONE_CONNECTION"]
browser_id = None
account_info = {}
last_ping_time = {}

# Function to generate a random UUID
def uuidv4():
    return str(uuid.uuid4())

# Function to check the validity of the response from the API
def valid_resp(resp):
    if not resp or "code" not in resp or resp["code"] < 0:
        raise ValueError("Invalid response")
    return resp

# Function to render profile information
async def render_profile_info(proxy, token):
    global browser_id, account_info

    try:
        np_session_info = load_session_info(proxy)

        # If no session info, create a new session
        if not np_session_info:
            browser_id = uuidv4()
            response = await call_api(DOMAIN_API["SESSION"], {}, proxy, token)
            if response is None:
                logger.info(f"Skipping proxy {proxy} due to 403 error.")
                return
            valid_resp(response)
            account_info = response["data"]
            if account_info.get("uid"):
                save_session_info(proxy, account_info)
                await start_ping(proxy, token)
            else:
                handle_logout(proxy)
        else:
            account_info = np_session_info
            await start_ping(proxy, token)
    except Exception as e:
        logger.error(f"Error in render_profile_info for proxy {proxy}: {e}")

# Function to make API requests
async def call_api(url, data, proxy, token, max_retries=3):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://app.nodepay.ai"
    }

    # Try multiple attempts to make the API call
    for attempt in range(max_retries):
        try:
            loop = asyncio.get_running_loop()
            response_json = await loop.run_in_executor(None, make_request, url, data, headers, proxy)
            return valid_resp(response_json)
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on attempt {attempt + 1} for proxy {proxy}: {e}")
            if e.response.status_code == 403:
                logger.error(f"403 Forbidden encountered on attempt {attempt + 1}: {e}")
                return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error on attempt {attempt + 1} for proxy {proxy}: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout on attempt {attempt + 1} for proxy {proxy}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt + 1} for proxy {proxy}: {e}")

        await asyncio.sleep(2 ** attempt)  # Exponential backoff for retries

    logger.error(f"Failed API call to {url} after {max_retries} attempts with proxy {proxy}")
    return None

# Function to actually make the HTTP request using cloudscraper
def make_request(url, data, headers, proxy):
    scraper = cloudscraper.create_scraper()
    if proxy:
        proxies = {
            'http': proxy,
            'https': proxy
        }
        scraper.proxies.update(proxies)

    response = scraper.post(url, json=data, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()

# Function to start sending ping requests
async def start_ping(proxy, token):
    try:
        while True:
            await ping(proxy, token)
            await asyncio.sleep(PING_INTERVAL)  # Sleep between pings
    except asyncio.CancelledError:
        logger.info(f"Ping task for proxy {proxy} was cancelled")
    except Exception as e:
        logger.error(f"Error in start_ping for proxy {proxy}: {e}")

# Function to send a ping request to the server
async def ping(proxy, token):
    global last_ping_time, RETRIES, status_connect

    current_time = time.time()
    if proxy in last_ping_time and (current_time - last_ping_time[proxy]) < PING_INTERVAL:
        logger.info(f"Skipping ping for proxy {proxy}, not enough time elapsed")
        return

    last_ping_time[proxy] = current_time

    try:
        data = {
            "id": account_info.get("uid"),
            "browser_id": browser_id,
            "timestamp": int(time.time())
        }

        response = await call_api(DOMAIN_API["PING"], data, proxy, token)
        if response["code"] == 0:
            logger.info(f"Ping successful with {proxy}: {response}")
            RETRIES = 0
            status_connect = CONNECTION_STATES["CONNECTED"]
        else:
            handle_ping_fail(proxy, response)
    except Exception as e:
        logger.error(f"Ping failed with proxy {proxy}: {e}")
        handle_ping_fail(proxy, None)

# Function to handle ping failure
def handle_ping_fail(proxy, response):
    global RETRIES, status_connect

    RETRIES += 1
    if response and response.get("code") == 403:
        handle_logout(proxy)
    elif RETRIES < 2:
        status_connect = CONNECTION_STATES["DISCONNECTED"]
    else:
        status_connect = CONNECTION_STATES["DISCONNECTED"]

# Function to handle logout and clear session
def handle_logout(proxy):
    global status_connect, account_info

    status_connect = CONNECTION_STATES["NONE_CONNECTION"]
    account_info = {}
    save_status(proxy, None)
    logger.info(f"Logged out and cleared session info for proxy {proxy}")

# Function to load proxies from a file
def load_proxies(proxy_file):
    try:
        with open(proxy_file, 'r') as file:
            proxies = file.read().splitlines()
        return proxies
    except Exception as e:
        logger.error(f"Unable to read proxy file: {e}")
        raise SystemExit("Exiting code...")

# Dummy function to save session status
def save_status(proxy, status):
    pass

# Function to save session info
def save_session_info(proxy, data):
    data_to_save = {
        "uid": data.get("uid"),
        "browser_id": browser_id
    }
    pass

# Function to load session info (placeholder)
def load_session_info(proxy):
    return {}

# Function to check if proxy is valid
def is_valid_proxy(proxy):
    return True

# Function to remove proxy from the list (not implemented)
def remove_proxy_from_list(proxy):
    pass

# Function to load tokens from a file
def load_tokens_from_file(filename):
    try:
        with open(filename, 'r') as file:
            tokens = file.read().splitlines()
        return tokens
    except Exception as e:
        logger.error(f"Unable to read token file: {e}")
        raise SystemExit("Exiting code...")

# Function to send data to the server
async def send_data_to_server(url, data, token):
    proxy = None  # No proxy for this request
    response = await call_api(url, data, proxy, token)

    if response is not None:
        logger.info(f"Sent login request")
    else:
        logger.error("No response received.")

# Main function that runs the process
async def main():
    print("AirDrop worker!")

    url = "https://api.nodepay.org/api/auth/session?"
    data = {
        "cache-control": "no-cache, no-store, max-age=0, must-revalidate",
        "cf-cache-status": "DYNAMIC",
        "cf-ray": "8db8aaa27b6fd487-NRT",
        "ary": "origin,access-control-request-method,access-control-request-headers,accept-encoding",
    }

    all_proxies = load_proxies('proxy.txt')
    tokens = load_tokens_from_file(TOKEN_FILE)

    # Send data for each token
    for token in tokens:
        await send_data_to_server(url, data, token)
        await asyncio.sleep(10)

    # Main loop to keep the proxies active
        await send_data_to_server(url, data, token)
        await asyncio.sleep(10)

    while True:
            active_proxies = [proxy for proxy in all_proxies if is_valid_proxy(proxy)][:100]
            tasks = {asyncio.create_task(render_profile_info(proxy, token)): proxy for proxy in active_proxies}

            done, pending = await asyncio.wait(tasks.keys(), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                failed_proxy = tasks[task]
                if task.result() is None:
                    logger.info(f"Loại bỏ và thay thế proxy bị lỗi: {failed_proxy}")
                    active_proxies.remove(failed_proxy)
                    if all_proxies:
                        new_proxy = all_proxies.pop(0)
                        if is_valid_proxy(new_proxy):
                            active_proxies.append(new_proxy)
                            new_task = asyncio.create_task(render_profile_info(new_proxy, token))
                            tasks[new_task] = new_proxy
                tasks.pop(task)

            for proxy in set(active_proxies) - set(tasks.values()):
                new_task = asyncio.create_task(render_profile_info(proxy, token))
                tasks[new_task] = proxy

            await asyncio.sleep(3)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bạn đã dừng code.")
cessary