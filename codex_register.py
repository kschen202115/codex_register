"""
codex 账号协议注册（纯 HTTP API 版）
直接调用 OpenAI 认证接口完成注册流程，无需浏览器。
通过 MailAPI 获取验证码。

用法:
    python api_register.py                         # 默认配置
    python api_register.py --proxy http://ip:port  # 指定代理
    python api_register.py --workers 5             # 并发数
"""

import base64
import hashlib
import json
import logging
import os
import random
import re
import secrets
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional, Callable
import argparse

from curl_cffi import requests as cffi_requests
from mailapi import MailAPI

# ═══════════════════════════════════════════════════════
# 常量配置
# ═══════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# OpenAI OAuth
OAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAI_AUTH_URL = "https://auth.openai.com/oauth/authorize"
OAI_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAI_SENTINEL_URL = "https://sentinel.openai.com/backend-api/sentinel/req"
OAI_SIGNUP_URL = "https://auth.openai.com/api/accounts/authorize/continue"
OAI_SEND_OTP_URL = "https://auth.openai.com/api/accounts/email-otp/send"
OAI_RESEND_OTP_URL = "https://auth.openai.com/api/accounts/email-otp/resend"
OAI_REGISTER_URL = "https://auth.openai.com/api/accounts/user/register"
OAI_VERIFY_OTP_URL = "https://auth.openai.com/api/accounts/email-otp/validate"
OAI_CREATE_URL = "https://auth.openai.com/api/accounts/create_account"
OAI_WORKSPACE_URL = "https://auth.openai.com/api/accounts/workspace/select"

LOCAL_CALLBACK_PORT = 1455
LOCAL_REDIRECT_URI = f"http://localhost:{LOCAL_CALLBACK_PORT}/auth/callback"

# 文件路径
RESULTS_DIR = os.path.join(SCRIPT_DIR, "tokens")
LOG_FILE = os.path.join(SCRIPT_DIR, "api_register.log")
PROXY_CACHE_FILE = os.path.join(SCRIPT_DIR, "proxy_cache.json")



# 邮箱后缀
EMAIL_DOMAINS = ["example1.com", "example2.com", "example3.com", "example4.com"]
# Token 上传服务器
CPA_URL = "http://your-server:port"
MANAGEMENT_KEY = "your-management-key"
# MailAPI 配置（固定）
MAIL_API_URL = "https://mail.example.com"
MAIL_API_AUTH = "your-mailapi-auth"
MAIL_PASSWD = ""  # 可选，cloudflare_temp_email私有站点密码
# 超时与重试
MAIL_POLL_TIMEOUT = 180
OTP_RESEND_INTERVAL = 25
MAX_RETRY_PER_ACCOUNT = 5





# ═══════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════
def _setup_logger():
    logger = logging.getLogger("api_reg")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger

log = _setup_logger()


# ═══════════════════════════════════════════════════════
# 账号数据结构
# ═══════════════════════════════════════════════════════
@dataclass
class MailAccount:
    """邮箱账号"""
    email: str


def random_email() -> str:
    """随机生成邮箱地址"""
    import string
    local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=14))
    return f"{local}@{random.choice(EMAIL_DOMAINS)}"


def load_proxy_pool(path: str = PROXY_CACHE_FILE) -> list[str]:
    """从 proxy_cache.json 加载代理列表，返回带协议前缀的代理地址列表"""
    if not os.path.isfile(path):
        log.warning(f"代理缓存文件不存在: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning(f"加载代理缓存失败: {e}")
        return []

    result = []
    for item in data.get("usable", []):
        addr = item.get("proxy", "")
        if not addr:
            continue
        # 根据支持的协议添加前缀，优先 socks5 > socks4 > http
        if item.get("socks5"):
            result.append(f"socks5://{addr}")
        elif item.get("socks4"):
            result.append(f"socks4://{addr}")
        elif item.get("http"):
            result.append(f"http://{addr}")
    return result


def pick_random_proxy(pool: list[str]) -> str:
    """从代理池中随机选择一个"""
    if not pool:
        return ""
    return random.choice(pool)



# ═══════════════════════════════════════════════════════
# 姓名 / 生日生成
# ═══════════════════════════════════════════════════════
_GIVEN_NAMES = [
    "Liam", "Noah", "Oliver", "James", "Elijah", "William", "Henry", "Lucas",
    "Benjamin", "Theodore", "Jack", "Levi", "Alexander", "Mason", "Ethan",
    "Daniel", "Jacob", "Michael", "Logan", "Jackson", "Sebastian", "Aiden",
    "Owen", "Samuel", "Ryan", "Nathan", "Carter", "Luke", "Jayden", "Dylan",
    "Caleb", "Isaac", "Connor", "Adrian", "Hunter", "Eli", "Thomas", "Aaron",
    "Olivia", "Emma", "Charlotte", "Amelia", "Sophia", "Isabella", "Mia",
    "Evelyn", "Harper", "Luna", "Camila", "Sofia", "Scarlett", "Elizabeth",
    "Eleanor", "Emily", "Chloe", "Mila", "Avery", "Riley", "Aria", "Layla",
    "Nora", "Lily", "Hannah", "Hazel", "Zoey", "Stella", "Aurora", "Natalie",
    "Emilia", "Zoe", "Lucy", "Lillian", "Addison", "Willow", "Ivy", "Violet",
]

_FAMILY_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Thompson", "White", "Harris", "Clark", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Hill", "Scott", "Green",
    "Adams", "Baker", "Nelson", "Carter", "Mitchell", "Roberts", "Turner",
    "Phillips", "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart",
    "Morris", "Murphy", "Cook", "Rogers", "Morgan", "Cooper", "Peterson",
    "Reed", "Bailey", "Kelly", "Howard", "Ward", "Watson", "Brooks", "Bennett",
    "Gray", "Price", "Hughes", "Sanders", "Long", "Foster", "Powell", "Perry",
    "Russell", "Sullivan", "Bell", "Coleman", "Butler", "Henderson", "Barnes",
]


def random_name() -> str:
    """生成随机英文姓名"""
    return f"{random.choice(_GIVEN_NAMES)} {random.choice(_FAMILY_NAMES)}"


def random_birthday() -> str:
    """生成随机生日（18~40岁之间）"""
    y = random.randint(1986, 2006)
    m = random.randint(1, 12)
    d = random.randint(1, 28)
    return f"{y}-{m:02d}-{d:02d}"


# ═══════════════════════════════════════════════════════
# PKCE + OAuth 工具
# ═══════════════════════════════════════════════════════
def _urlsafe_b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_pkce_pair() -> tuple[str, str]:
    """创建 PKCE code_verifier 和 code_challenge"""
    verifier = secrets.token_urlsafe(48)
    challenge = _urlsafe_b64(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def create_oauth_params() -> dict:
    """生成完整的 OAuth 参数集"""
    verifier, challenge = create_pkce_pair()
    state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode({
        "client_id": OAI_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": LOCAL_REDIRECT_URI,
        "scope": "openid email profile offline_access",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    })
    return {
        "auth_url": f"{OAI_AUTH_URL}?{query}",
        "state": state,
        "verifier": verifier,
    }


def decode_jwt_payload(token: str) -> dict:
    """解码 JWT payload（不验证签名）"""
    try:
        payload = token.split(".")[1]
        padding = "=" * ((4 - len(payload) % 4) % 4)
        raw = base64.urlsafe_b64decode(payload + padding)
        return json.loads(raw)
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════
# MailAPI 验证码获取
# ═══════════════════════════════════════════════════════


def poll_verification_code(
    account: MailAccount,
    mail_api: MailAPI,
    timeout: int = MAIL_POLL_TIMEOUT,
    used_codes: Optional[set] = None,
    resend_fn: Optional[Callable] = None,
    otp_sent_at: Optional[float] = None,
    cancel_fn: Optional[Callable] = None,
) -> str:
    """通过 MailAPI 轮询获取 OpenAI 6 位验证码

    mail_api: MailAPI 实例
    otp_sent_at: OTP 发送时的 Unix 时间戳，只接受此时间之后的邮件
    """
    log.info(f"    📧 等待验证码 ({account.email}, MailAPI)...")
    used = used_codes or set()
    start = time.time()
    intervals = [3, 4, 5, 6, 8, 10]
    idx = 0
    last_resend = 0.0

    def _cancelled():
        return cancel_fn and cancel_fn()

    def _interruptible_sleep(seconds):
        end = time.time() + seconds
        while time.time() < end:
            if _cancelled():
                raise InterruptedError("用户取消")
            time.sleep(min(0.5, max(0, end - time.time())))

    while time.time() - start < timeout:
        if _cancelled():
            raise InterruptedError("用户取消")

        try:
            code = mail_api.get_latest_code(address=account.email)
            if code and code not in used:
                used.add(code)
                elapsed = int(time.time() - start)
                log.info(f"    ✅ 验证码: {code} (耗时 {elapsed}s)")
                return code
        except InterruptedError:
            raise
        except Exception as e:
            log.warning(f"    MailAPI 查询失败: {e}")

        # 定时重发 OTP
        elapsed_now = time.time() - start
        if resend_fn and elapsed_now > 20 and (elapsed_now - last_resend) > OTP_RESEND_INTERVAL:
            try:
                resend_fn()
                last_resend = elapsed_now
                log.info("    🔄 已重发 OTP")
            except Exception:
                pass

        wait = intervals[min(idx, len(intervals) - 1)]
        idx += 1
        _interruptible_sleep(wait)

    raise TimeoutError(f"验证码超时 ({timeout}s)")


# ═══════════════════════════════════════════════════════
# 浏览器指纹伪装
# ═══════════════════════════════════════════════════════
# curl_cffi 可模拟的浏览器身份（会自动生成对应的 TLS 指纹、HTTP/2 设置等）
_BROWSER_PROFILES = ['edge99', 'edge101', 'chrome99', 'chrome100', 
                    'chrome101', 'chrome104', 'chrome107', 'chrome110',
                    'chrome116', 'chrome119', 'chrome120', 'chrome123', 
                    'chrome124', 'chrome131', 'chrome133a', 'chrome136',
                    'chrome142', 
                    'safari153', 'safari155', 'safari170',  
                    'safari180',  'safari184', 
                    'safari260',  'safari2601', 'firefox133', 
                    'firefox135', 'firefox144',  'safari15_3', 
                    'safari15_5', 'safari17_0', 'safari17_2_ios', 'safari18_0', 
                    ]


# 对应不同浏览器的 Accept-Language 头
_ACCEPT_LANGUAGES = [
   # --- 1. 英语主导 (你的原有基础 + 补充) ---
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en,en-US;q=0.9,en-GB;q=0.8",
    
    # --- 2. 中文主导 (如果你爬取的网站面向华人，或者想伪装成国内用户) ---
    "zh-CN,zh;q=0.9",
    "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "zh-TW,zh-HK;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6", # 繁体中文环境 (港台)
    
    # --- 3. 欧洲语系 (配合欧洲节点 IP 使用，效果极佳) ---
    "es-ES,es;q=0.9,en;q=0.8",          # 西班牙语
    "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7", # 墨西哥/拉美西班牙语
    "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7", # 法语
    "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7", # 德语
    "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7", # 俄语
    "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7", # 葡萄牙语(巴西)
    
    # --- 4. 亚洲其他语系 (配合日韩/东南亚 IP) ---
    "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7", # 日语
    "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7", # 韩语
    "vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5", # 越南语
    
    # --- 5. 纯净单语言 (有些用户的浏览器只设置了一种语言) ---
    "en-US",
    "en-GB",
]


def _pick_fingerprint() -> tuple[str, dict]:
    """随机选择浏览器身份和对应请求头"""
    profile = random.choice(_BROWSER_PROFILES)
    lang = random.choice(_ACCEPT_LANGUAGES)
    headers = {
        "Accept-Language": lang,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    return profile, headers


# ═══════════════════════════════════════════════════════
# HTTP 会话（基于 curl_cffi，自带浏览器 TLS 指纹）
# ═══════════════════════════════════════════════════════
class APISession:
    """基于 curl_cffi 的 HTTP 会话，内置浏览器指纹伪装"""

    def __init__(self, proxy: str = ""):
        profile, fp_headers = _pick_fingerprint()
        proxies = {"http": proxy, "https": proxy} if proxy else None
        self._session = cffi_requests.Session(proxies=proxies, impersonate=profile)
        self._session.headers.update(fp_headers)
        self._profile = profile
        log.info(f"    🎭 浏览器指纹: {profile}")

    def get(self, url: str, **kwargs) -> "APIResponse":
        resp = self._session.get(url, timeout=30, **kwargs)
        return APIResponse(resp.status_code, resp.text, dict(resp.headers))

    def post_json(self, url: str, data: dict, headers: Optional[dict] = None) -> "APIResponse":
        hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        resp = self._session.post(url, data=json.dumps(data), headers=hdrs, timeout=30)
        return APIResponse(resp.status_code, resp.text, dict(resp.headers))

    def post_form(self, url: str, data: dict) -> "APIResponse":
        hdrs = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        resp = self._session.post(url, data=urllib.parse.urlencode(data), headers=hdrs, timeout=30)
        return APIResponse(resp.status_code, resp.text, dict(resp.headers))

    def get_cookie(self, name: str) -> Optional[str]:
        return self._session.cookies.get(name)

    def follow_redirects(self, url: str, max_hops: int = 12) -> Optional[str]:
        """跟随 302 重定向链，返回包含 localhost 的回调 URL"""
        for _ in range(max_hops):
            resp = self._session.get(url, allow_redirects=False, timeout=30)
            location = resp.headers.get("Location")
            if not location:
                return None
            if "localhost" in location and "/auth/callback" in location:
                return location
            url = location
        return None

    def close(self):
        self._session.close()

    def __enter__(self): return self
    def __exit__(self, *a): self.close()


@dataclass
class APIResponse:
    status: int
    text: str
    headers: dict

    def json(self) -> dict:
        return json.loads(self.text)

    def ok(self) -> bool:
        return 200 <= self.status < 300

import secrets
import string

def generate_password():
    # 1. 定义字符集
    letters = string.ascii_letters  # 包含所有大小写字母 (a-z, A-Z)
    digits = string.digits          # 包含所有数字 (0-9)
    # 常用的安全符号，排除了容易引起代码解析错误的引号等
    symbols = "!@#$%^&*()_+-=[]{}|;:,.<>?" 

    # 2. 按照要求随机抽取字符
    # 抽取 5 个字母
    pwd_letters = [secrets.choice(letters) for _ in range(5)]
    # 抽取 6 个数字
    pwd_digits = [secrets.choice(digits) for _ in range(6)]
    # 抽取 1 个符号
    pwd_symbols = [secrets.choice(symbols) for _ in range(1)]

    # 3. 将所有字符合并到一个列表中
    password_list = pwd_letters + pwd_digits + pwd_symbols

    # 4. 打乱列表顺序，防止密码格式固定（例如总是以字母开头）
    secrets.SystemRandom().shuffle(password_list)

    # 5. 将列表拼接成完整的字符串
    password = "".join(password_list)
    
    return password
# ═══════════════════════════════════════════════════════
# 核心注册/登录流程
# ═══════════════════════════════════════════════════════
def register_account(
    mail_account: MailAccount,
    mail_api: MailAPI,
    proxy: str = "",
    used_codes: Optional[set] = None,
    password: Optional[str] = None,
    mode: str = "register",
    cancel_fn: Optional[Callable] = None,
) -> dict:
    """
    通过 API 注册或登录 OpenAI 账号。
    返回包含 token 信息的字典。
    """
    email_addr = mail_account.email
    codes = used_codes or set()
    is_login = (mode == "login")
    mode_label = "登录" if is_login else "注册"

    def _check_cancel():
        if cancel_fn and cancel_fn():
            raise InterruptedError("用户取消")

    def _sleep(lo, hi):
        """可中断的随机 sleep"""
        end = time.time() + random.uniform(lo, hi)
        while time.time() < end:
            _check_cancel()
            time.sleep(min(0.3, max(0, end - time.time())))

    with APISession(proxy) as http:
        # --- 1. 发起 OAuth 授权 ---
        _check_cancel()
        oauth = create_oauth_params()
        log.info(f"  [1] 发起 OAuth ({mode_label})...")
        resp = http.get(oauth["auth_url"])
        log.info(f"      状态: {resp.status}")

        device_id = http.get_cookie("oai-did") or ""
        if device_id:
            log.info(f"      设备ID: {device_id[:16]}...")

        _sleep(0.8, 2.0)

        # --- 2. 获取 Sentinel 反机器人令牌 ---
        _check_cancel()
        log.info(f"  [2] 获取 Sentinel token...")
        sentinel_body = {"p": "", "id": device_id, "flow": "authorize_continue"}
        sentinel_resp = http.post_json(
            OAI_SENTINEL_URL, sentinel_body,
            headers={
                "Origin": "https://sentinel.openai.com",
                "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
            }
        )
        if not sentinel_resp.ok():
            raise RuntimeError(f"Sentinel 失败: {sentinel_resp.status} {sentinel_resp.text[:200]}")
        sentinel_token = sentinel_resp.json()["token"]
        sentinel_header = json.dumps({
            "p": "", "t": "", "c": sentinel_token,
            "id": device_id, "flow": "authorize_continue",
        })
        log.info(f"      OK")

        _sleep(0.5, 1.5)

        # --- 3. 提交邮箱---
        _check_cancel()
        # 记录时间戳——已注册账号在此步骤后 OTP 就会自动发送
        otp_sent_at = time.time()
        log.info(f"  [3] 提交邮箱: {email_addr} ({mode_label})")
        signup_resp = http.post_json(
            OAI_SIGNUP_URL,
            {"username": {"value": email_addr, "kind": "email"}, "screen_hint": "signup"},
            headers={
                "Referer": "https://auth.openai.com/create-account",
                "openai-sentinel-token": sentinel_header,
            },
        )
        if not signup_resp.ok():
            raise RuntimeError(f"提交邮箱失败: {signup_resp.status} {signup_resp.text[:300]}")
        log.info(f"      OK")

        # 解析步骤3响应，判断账号状态
        try:
            step3_data = signup_resp.json()
            page_type = step3_data.get("page", {}).get("type", "")
        except Exception:
            step3_data = {}
            page_type = ""
        log.info(f"      页面类型: {page_type}")

        _sleep(0.5, 1.5)

        name = ""
        # 已注册账号：步骤3返回 email_otp_verification → OTP 已自动发送
        is_existing_account = (page_type == "email_otp_verification")

        _check_cancel()
        if is_existing_account:
            # 已注册账号：OTP 在步骤3提交邮箱时已自动发送
            log.info(f"  [4] 跳过发送 OTP（服务器已自动发送）")
        else:
            # --- 4. 请求发送 OTP 验证码（新账号需要手动触发）---
            log.info(f"   设置密码...")
            otp_resp = http.post_json(
                OAI_REGISTER_URL, {"password": password,"username":email_addr},
                headers={"Referer": "https://auth.openai.com/create-account/password"},
            )
            if not otp_resp.ok():
                raise RuntimeError(f"设置密码失败: {otp_resp.status} {otp_resp.text[:300]}")
            log.info(f"      OK，密码已设置{password}")

            otp_sent_at = time.time()
            log.info(f"  [4] 发送 OTP...")
            otp_resp = http.post_json(
                OAI_SEND_OTP_URL, {},
                headers={"Referer": "https://auth.openai.com/create-account/password"},
            )
            if not otp_resp.ok():
                raise RuntimeError(f"发送 OTP 失败: {otp_resp.status} {otp_resp.text[:300]}")
            log.info(f"      OK，验证码已发送到 {email_addr}")

        # --- 5. 通过 MailAPI 获取验证码 ---
        def _resend():
            r = http.post_json(OAI_RESEND_OTP_URL, {},
                headers={"Referer": "https://auth.openai.com/email-verification"})
            return r.ok()

        code = poll_verification_code(
            mail_account, mail_api,
            used_codes=codes,
            resend_fn=_resend,
            otp_sent_at=otp_sent_at,
            cancel_fn=cancel_fn,
        )

        _check_cancel()
        _sleep(0.3, 1.0)

        # --- 6. 验证 OTP ---
        _check_cancel()
        log.info(f"  [6] 验证 OTP: {code}")
        verify_resp = http.post_json(
            OAI_VERIFY_OTP_URL, {"code": code},
            headers={"Referer": "https://auth.openai.com/email-verification"},
        )
        if not verify_resp.ok():
            raise RuntimeError(f"OTP 验证失败: {verify_resp.status} {verify_resp.text[:300]}")
        log.info(f"      OK")

        _sleep(0.5, 1.5)

        # --- 7. 创建账号（仅新注册时，已注册账号跳过）---
        _check_cancel()
        if is_existing_account or is_login:
            log.info(f"  [7] 跳过（账号已存在）")
        else:
            name = random_name()
            birthday = random_birthday()
            log.info(f"  [7] 创建账号: {name}, {birthday}")
            create_resp = http.post_json(
                OAI_CREATE_URL,
                {"name": name, "birthdate": birthday},
                headers={"Referer": "https://auth.openai.com/about-you"},
            )
            if not create_resp.ok():
                raise RuntimeError(f"创建账号失败: {create_resp.status} {create_resp.text[:300]}")
            log.info(f"      OK")
            _sleep(0.5, 1.5)

        # --- 8. 选择 Workspace ---
        auth_cookie = http.get_cookie("oai-client-auth-session")
        if not auth_cookie:
            raise RuntimeError("未获取到 oai-client-auth-session cookie")

        # 解析 cookie 获取 workspace_id
        try:
            cookie_b64 = auth_cookie.split(".")[0]
            padding = "=" * ((4 - len(cookie_b64) % 4) % 4)
            cookie_data = json.loads(base64.b64decode(cookie_b64 + padding))
            workspaces = cookie_data.get("workspaces", [])
            workspace_id = workspaces[0]["id"] if workspaces else None
        except Exception as e:
            raise RuntimeError(f"解析 workspace 失败: {e}")

        if not workspace_id:
            raise RuntimeError("未找到 workspace_id")

        log.info(f"  [8] 选择 Workspace: {workspace_id[:20]}...")
        select_resp = http.post_json(
            OAI_WORKSPACE_URL,
            {"workspace_id": workspace_id},
            headers={"Referer": "https://auth.openai.com/sign-in-with-chatgpt/codex/consent"},
        )
        if not select_resp.ok():
            raise RuntimeError(f"选择 workspace 失败: {select_resp.status}")

        continue_url = select_resp.json().get("continue_url")
        if not continue_url:
            raise RuntimeError("未获取到 continue_url")

        # --- 9. 跟随重定向，获取回调并兑换 token ---
        log.info(f"  [9] 跟随重定向获取 Token...")
        callback_url = http.follow_redirects(continue_url)
        if not callback_url:
            raise RuntimeError("重定向失败，未获取到回调 URL")

        # 解析回调 URL 中的 code
        parsed = urllib.parse.urlparse(callback_url)
        query = urllib.parse.parse_qs(parsed.query)
        auth_code = query.get("code", [""])[0]
        returned_state = query.get("state", [""])[0]

        if not auth_code:
            raise RuntimeError("回调 URL 缺少 code")
        if returned_state != oauth["state"]:
            raise RuntimeError("State 不匹配")

        # 兑换 token
        token_resp = http.post_form(OAI_TOKEN_URL, {
            "grant_type": "authorization_code",
            "client_id": OAI_CLIENT_ID,
            "code": auth_code,
            "redirect_uri": LOCAL_REDIRECT_URI,
            "code_verifier": oauth["verifier"],
        })
        if not token_resp.ok():
            raise RuntimeError(f"Token 兑换失败: {token_resp.status} {token_resp.text[:300]}")

        token_data = token_resp.json()

        # 解析 id_token 获取额外信息
        claims = decode_jwt_payload(token_data.get("id_token", ""))
        auth_claims = claims.get("https://api.openai.com/auth", {})

        now = int(time.time())
        result = {
            "email": email_addr,
            "type": "codex",
            "name": name or claims.get("name", ""),
            "access_token": token_data.get("access_token", ""),
            "refresh_token": token_data.get("refresh_token", ""),
            "id_token": token_data.get("id_token", ""),
            "account_id": auth_claims.get("chatgpt_account_id", ""),
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(now + int(token_data.get("expires_in", 0)))),
            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "mode": mode,
        }

        log.info(f"  🎉 {mode_label}成功！")
        return result


# ═══════════════════════════════════════════════════════
# 单账号注册（带重试）
# ═══════════════════════════════════════════════════════
def _do_one(
    account: MailAccount,
    mail_api: MailAPI,
    idx: int,
    total: int,
    proxy_pool: list[str],
    stats: dict,
    lock: threading.Lock,
    delay: float = 0,
):
    """单个账号注册任务（线程安全）"""
    if delay > 0:
        time.sleep(delay)


    start_t = time.time()

    used = set()
    log.info(f"\n{'─'*50}")
    log.info(f"[{idx}/{total}] {account.email}")
    log.info(f"{'─'*50}")

    ok = False
    for attempt in range(1, MAX_RETRY_PER_ACCOUNT + 1):
        proxy = pick_random_proxy(proxy_pool)
        if attempt > 1:
            log.info(f"  重试 #{attempt}...")
            time.sleep(random.uniform(2, 5))
        log.info(f"  🌐 代理: {proxy or '无'}")
        try:
            password = generate_password()
            result = register_account(account, mail_api, proxy, used,password)
            elapsed = round(time.time() - start_t, 1)
            result["elapsed_seconds"] = elapsed

            # 保存结果
            os.makedirs(RESULTS_DIR, exist_ok=True)
            fpath = os.path.join(RESULTS_DIR, f"{account.email}--{password}.json")
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            with lock:
                stats["ok"] += 1

            log.info(f"  💾 已保存: {fpath} ({elapsed}s)")
            ok = True
            break

        except Exception as e:
            log.warning(f"  ❌ 尝试 {attempt} 失败: {type(e).__name__}: {str(e)[:150]}")

    if not ok:
        with lock:
            stats["fail"] += 1


# ═══════════════════════════════════════════════════════
# Token 上传与清理
# ═══════════════════════════════════════════════════════
def upload_and_cleanup(directory: str):
    """将 tokens 目录下的所有 JSON 文件上传到管理服务器，成功后删除本地文件"""
    import requests as std_requests

    if not os.path.isdir(directory):
        return

    files = [f for f in os.listdir(directory) if f.endswith(".json")]
    if not files:
        log.info("📤 没有需要上传的文件")
        return

    log.info(f"\n📤 开始上传 {len(files)} 个 token 文件到 {CPA_URL}")
    uploaded = 0
    failed = 0

    for fname in files:
        fpath = os.path.join(directory, fname)
        try:
            with open(fpath, "rb") as f:
                resp = std_requests.post(
                    CPA_URL+f'/v0/management/auth-files?name={fname}',
                    files={"file": (fname, f, "application/json")},
                    headers={"Authorization": f"Bearer {MANAGEMENT_KEY}"},
                    timeout=30,
                )
            if resp.status_code in (200, 201):
                os.remove(fpath)
                uploaded += 1
                log.info(f"  ✅ 上传成功: {fname}")
            else:
                failed += 1
                log.warning(f"  ❌ 上传失败: {fname} (HTTP {resp.status_code}: {resp.text[:100]})")
        except Exception as e:
            failed += 1
            log.warning(f"  ❌ 上传异常: {fname} ({e})")

    log.info(f"📤 上传完成: {uploaded} 成功, {failed} 失败")


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="OpenAI 协议注册（纯 API 版）")
    parser.add_argument("--workers", type=int, default=1, help="并发线程数")
    parser.add_argument("--count", type=int, default=5, help="注册数量")
    args = parser.parse_args()

    log.info("=" * 55)
    log.info("  OpenAI 协议注册 v1.0")
    log.info("=" * 55)

    mail_api = MailAPI(worker_url=MAIL_API_URL, admin_auth=MAIL_API_AUTH)
    log.info(f"📨 MailAPI: {MAIL_API_URL}")


    # 加载代理池
    proxy_pool = load_proxy_pool()
    if proxy_pool:
        log.info(f"🌐 代理池: {len(proxy_pool)} 个可用代理")
    else:
        log.warning("⚠️ 代理池为空，将直连（可能被封）")

    # 自动生成随机邮箱
    batch = [MailAccount(email=random_email()) for _ in range(args.count)]
    total = len(batch)
    log.info(f"🚀 本次注册: {total} 个 (并发: {args.workers})")

    stats = {"ok": 0, "fail": 0}

    lock = threading.Lock()
    t0 = time.time()

    if args.workers <= 1:
        # 串行模式
        for i, acc in enumerate(batch, 1):
            _do_one(acc, mail_api, i, total, proxy_pool, stats, lock)
    else:
        # 并行模式
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {}
            for i, acc in enumerate(batch, 1):
                # 同一波次内错开启动
                wave_pos = (i - 1) % args.workers
                delay = wave_pos * random.uniform(1.0, 2.5) if wave_pos > 0 else 0
                fut = pool.submit(_do_one, acc, mail_api, i, total, proxy_pool, stats, lock, delay)
                futs[fut] = acc.email

            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as e:
                    log.error(f"线程异常 [{futs[fut]}]: {e}")

    elapsed = time.time() - t0
    log.info(f"\n{'='*55}")
    log.info(f"  注册完成")
    log.info(f"{'='*55}")
    log.info(f"  ✅ 成功: {stats['ok']}")
    log.info(f"  ❌ 失败: {stats['fail']}")
    log.info(f"  ⏱️ 耗时: {elapsed:.1f}s ({elapsed/60:.1f}m)")
    log.info(f"  📁 结果: {RESULTS_DIR}")

    # 上传并清理
    if stats["ok"] > 0:
        upload_and_cleanup(RESULTS_DIR)


if __name__ == "__main__":
    main()
