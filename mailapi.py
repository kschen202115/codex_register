import requests
import re


class MailAPI:
    def __init__(self, worker_url: str, admin_auth: str, webmail_password: str = ""):
        self.url = worker_url.rstrip("/") + "/admin/mails"
        self.headers = {
            "x-admin-auth": admin_auth
        }

        # 可选的 Webmail 认证头，仅在传入时附加
        if webmail_password:
            self.headers["x-custom-auth"] = webmail_password

    def get_mails(self, limit=1, offset=0, address=None):
        params = {
            "limit": limit,
            "offset": offset
        }

        if address:
            params["address"] = address

        resp = requests.get(self.url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_latest_code(self, address=None):
        data = self.get_mails(limit=1, offset=0, address=address)

        if not data["results"]:
            return None

        raw = data["results"][0]["raw"]

        # 提取6位验证码
        match = re.search(r"\b\d{6}\b", raw)
        if match:
            return match.group(0)

        return None


if __name__ == "__main__":
    api = MailAPI(
        worker_url="https://xxxxxxxxxxx",
        admin_auth="xxxxxx"
    )

    code = api.get_latest_code("xxxxxxxx@xxxx.xxx")
    print("验证码:", code)