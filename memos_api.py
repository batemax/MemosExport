#!/usr/bin/env python3

import json
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_USER_AGENT = "memos-export-import/1.0 (+https://github.com/)"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    def __init__(self, status_code, reason, body, url):
        self.status_code = status_code
        self.reason = reason
        self.body = body
        self.url = url
        super().__init__(f"{status_code} {reason} for {url}: {body}")


class MemosAPI:
    def __init__(self, base_url, token, timeout=60, max_retries=3, retry_delay=1.0):
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v1"
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def request(self, method, path, query=None, body=None, headers=None):
        url = self._build_api_url(path, query=query)
        return self._request_json(method, url, body=body, headers=headers)

    def _build_api_url(self, path, query=None):
        url = f"{self.api_base}{path}"
        if query:
            params = {
                key: value
                for key, value in query.items()
                if value is not None and value != ""
            }
            encoded = urllib.parse.urlencode(params)
            if encoded:
                url = f"{url}?{encoded}"
        return url

    def _request_json(self, method, url, body=None, headers=None):
        request_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            # Some Cloudflare setups block urllib's default signature.
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)

        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            url=url,
            data=data,
            headers=request_headers,
            method=method,
        )

        payload = self._perform_request(request, url)

        if not payload:
            return {}
        return json.loads(payload.decode("utf-8"))

    def request_bytes(self, method, url, headers=None):
        request_headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if headers:
            request_headers.update(headers)

        request = urllib.request.Request(
            url=url,
            headers=request_headers,
            method=method,
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read(), dict(response.headers.items())
            except urllib.error.HTTPError as exc:
                raw_body = exc.read().decode("utf-8", errors="replace")
                if exc.code in RETRY_STATUS_CODES and attempt < self.max_retries:
                    time.sleep(self.retry_delay * (2**attempt))
                    continue
                raise ApiError(exc.code, exc.reason, raw_body, url) from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * (2**attempt))
                    continue
                raise RuntimeError(f"Network error calling {url}: {exc}") from exc

    def _perform_request(self, request, url):
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                raw_body = exc.read().decode("utf-8", errors="replace")
                if exc.code in RETRY_STATUS_CODES and attempt < self.max_retries:
                    time.sleep(self.retry_delay * (2**attempt))
                    continue
                raise ApiError(exc.code, exc.reason, raw_body, url) from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * (2**attempt))
                    continue
                raise RuntimeError(f"Network error calling {url}: {exc}") from exc

    def get_current_user(self):
        response = self.request("GET", "/auth/me")
        return response.get("user", response)

    def get_memo(self, memo_id):
        try:
            return self.request("GET", f"/memos/{urllib.parse.quote(memo_id)}")
        except ApiError as exc:
            if exc.status_code == 404:
                return None
            raise

    def list_memos(self, state, page_size, order_by, filter_expression):
        page_token = ""
        while True:
            response = self.request(
                "GET",
                "/memos",
                query={
                    "pageSize": min(page_size, 1000),
                    "pageToken": page_token,
                    "state": state,
                    "orderBy": order_by,
                    "filter": filter_expression,
                },
            )
            for memo in response.get("memos", []):
                yield memo
            page_token = response.get("nextPageToken", "")
            if not page_token:
                break

    def list_memo_attachments(self, memo_id, page_size=200):
        page_token = ""
        attachments = []
        while True:
            response = self.request(
                "GET",
                f"/memos/{urllib.parse.quote(memo_id)}/attachments",
                query={
                    "pageSize": min(page_size, 1000),
                    "pageToken": page_token,
                },
            )
            attachments.extend(response.get("attachments", []))
            page_token = response.get("nextPageToken", "")
            if not page_token:
                break
        return attachments

    def download_attachment_file(self, attachment_id, filename):
        url = f"{self.base_url}/file/attachments/{urllib.parse.quote(attachment_id)}/{urllib.parse.quote(filename)}"
        return self.request_bytes("GET", url)

    def create_memo(self, memo_id, payload):
        return self.request(
            "POST",
            "/memos",
            query={"memoId": memo_id},
            body=payload,
        )

    def create_memo_comment(self, memo_id, comment_id, payload):
        query = {}
        if comment_id:
            query["commentId"] = comment_id
        return self.request(
            "POST",
            f"/memos/{urllib.parse.quote(memo_id)}/comments",
            query=query,
            body=payload,
        )

    def update_memo(self, memo_id, payload, update_mask):
        return self.request(
            "PATCH",
            f"/memos/{urllib.parse.quote(memo_id)}",
            query={"updateMask": ",".join(update_mask)},
            body=payload,
        )

    def create_attachment(self, attachment_id, payload):
        query = {}
        if attachment_id:
            query["attachmentId"] = attachment_id
        return self.request(
            "POST",
            "/attachments",
            query=query,
            body=payload,
        )

    def set_memo_relations(self, memo_id, relations):
        return self.request(
            "PATCH",
            f"/memos/{urllib.parse.quote(memo_id)}/relations",
            body={
                "name": f"memos/{memo_id}",
                "relations": relations,
            },
        )
