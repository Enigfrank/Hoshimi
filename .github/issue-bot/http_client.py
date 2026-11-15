"""仅访问预先配置的 JSON API，不跟随携带凭据的重定向。"""

import json
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """禁止将鉴权请求重定向到其他地址。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """让重定向作为 HTTP 错误返回，避免转发 Authorization。"""
        return


class JsonAPI:
    """以固定地址和凭据发送 JSON 请求。"""

    def __init__(self, base_url, token, *, github=False):
        """校验 HTTPS 地址；日志与异常均不包含凭据或响应正文。"""
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("API 地址必须是无凭据、无查询参数的 HTTPS 地址")
        if not token:
            raise ValueError("缺少 API 凭据")
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json" if github else "application/json",
            "User-Agent": "Hoshimi-Issue-Assistant",
        }
        if github:
            self.headers["X-GitHub-Api-Version"] = "2022-11-28"
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, *, method="GET", data=None, allow_missing=False):
        """发送单次请求；仅允许调用者明确接受的 404，其他错误终止操作。"""
        headers = dict(self.headers)
        payload = None
        if data is not None:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=payload, headers=headers, method=method,
        )
        try:
            with self.opener.open(request, timeout=180) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("API 响应超出读取上限")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if allow_missing and error.code == 404:
                return None
            raise RuntimeError(f"{method} 请求失败：HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError(f"{method} 请求失败：连接异常或超时") from None

    def pages(self, path):
        """按 GitHub 的每页 100 条规则完整读取列表。"""
        result = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            rows = self.request(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(rows, list):
                raise TypeError("GitHub 列表响应格式错误")
            result.extend(rows)
            if len(rows) < 100:
                return result
            page += 1
