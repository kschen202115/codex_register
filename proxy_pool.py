import requests
import json
import os
import threading
import queue
from datetime import datetime

BASE_API = "https://api.checkerproxy.net/v1/landing/archive/{}"
TEST_URL = "https://auth.openai.com/"
CACHE_FILE = "proxy_cache.json"
TIMEOUT = 8
THREADS = 30


def today():
    return datetime.utcnow().strftime("%Y-%m-%d")


def fetch_proxy_list(date):
    url = BASE_API.format(date)
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        return []
    return data["data"]["proxyList"]


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r") as f:
        return json.load(f)


def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)


def test_proxy_http(proxy):
    proxies = {
        "http": f"http://{proxy}",
        "https": f"http://{proxy}"
    }
    try:
        r = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT)
        return r.status_code == 200
    except:
        return False


def test_proxy_socks4(proxy):
    proxies = {
        "http": f"socks4://{proxy}",
        "https": f"socks4://{proxy}"
    }
    try:
        r = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT)
        return r.status_code == 200
    except:
        return False


def test_proxy_socks5(proxy):
    proxies = {
        "http": f"socks5://{proxy}",
        "https": f"socks5://{proxy}"
    }
    try:
        r = requests.get(TEST_URL, proxies=proxies, timeout=TIMEOUT)
        return r.status_code == 200
    except:
        return False


def test_proxy_all(proxy):
    result = {
        "proxy": proxy,
        "http": False,
        "socks4": False,
        "socks5": False
    }

    if test_proxy_http(proxy):
        result["http"] = True

    if test_proxy_socks4(proxy):
        result["socks4"] = True

    if test_proxy_socks5(proxy):
        result["socks5"] = True

    return result


def build_cache():
    date = today()
    cache = load_cache()

    # 缓存日期过期时，先删除旧文件，避免读取到过期代理
    if cache.get("date") and cache.get("date") != date:
        try:
            os.remove(CACHE_FILE)
        except OSError:
            pass
        cache = {}

    if cache.get("date") == date and cache.get("usable"):
        return

    proxies = fetch_proxy_list(date)

    q = queue.Queue()
    for p in proxies:
        q.put(p)

    usable = []
    lock = threading.Lock()

    def worker():
        while True:
            try:
                proxy = q.get_nowait()
            except queue.Empty:
                return

            res = test_proxy_all(proxy)

            if res["http"] or res["socks4"] or res["socks5"]:
                with lock:
                    usable.append(res)

            q.task_done()

    threads = []
    for _ in range(THREADS):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    save_cache({
        "date": date,
        "usable": usable
    })


def get_proxy():
    build_cache()
    cache = load_cache()

    proxies = cache.get("usable", [])
    if not proxies:
        return None

    proxy = proxies.pop(0)

    save_cache({
        "date": cache["date"],
        "usable": proxies
    })

    return proxy


if __name__ == "__main__":
    p = get_proxy()
    print(p)