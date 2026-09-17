"""HTTP client for YU AI Manager REST API."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class YuManagerClient:
    """Thin HTTP wrapper around the YU AI Manager REST API."""

    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _request(
        self, method: str, path: str,
        params: dict[str, str] | None = None,
        body: Any = None,
    ) -> dict:
        url = self.base_url + path
        if params:
            qs = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None and v != ""}
            )
            if qs:
                url += "?" + qs

        data = None
        headers = self._headers()
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                if not raw:
                    return {"ok": False, "error": f"Empty response from {url}"}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    # Server returned non-JSON (e.g. HTML error page)
                    snippet = raw[:200].decode("utf-8", errors="replace")
                    return {"ok": False, "error": f"Non-JSON response from {url}: {snippet}"}
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                return json.loads(body)
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}: {e.reason} ({url})"}
        except urllib.error.URLError as e:
            return {"ok": False, "error": f"Connection failed ({self.base_url}): {e.reason}"}
        except Exception as e:
            return {"ok": False, "error": f"{e} ({url})"}

    def get(self, path: str, params: dict[str, str] | None = None) -> dict:
        """Send a GET request."""
        return self._request("GET", path, params=params)

    def get_text(self, path: str, params: dict[str, str] | None = None) -> str:
        """Send a GET request and return raw response body as text.

        Use for endpoints that return plain text rather than JSON.
        Returns the raw text on success, or an error string prefixed with 'Error: '.
        """
        url = self.base_url + path
        if params:
            qs = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None and v != ""}
            )
            if qs:
                url += "?" + qs

        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return f"Error: HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return f"Error: Connection failed ({self.base_url}): {e.reason}"
        except Exception as e:
            return f"Error: {e} ({url})"

    def post(self, path: str, body: Any = None) -> dict:
        """Send a POST request with JSON body."""
        return self._request("POST", path, body=body)

    def put(self, path: str, body: Any = None) -> dict:
        """Send a PUT request with JSON body."""
        return self._request("PUT", path, body=body)

    def patch(self, path: str, body: Any = None) -> dict:
        """Send a PATCH request with JSON body."""
        return self._request("PATCH", path, body=body)

    def delete(self, path: str, body: Any = None) -> dict:
        """Send a DELETE request, optionally with JSON body."""
        return self._request("DELETE", path, body=body)

    def post_sse(self, path: str, body: Any = None, timeout: int = 300) -> dict:
        """POST して SSE ストリームを消費し、最終結果を返す。

        Hailo LLM/VLM の generate エンドポイント用。
        SSE の各 ``data:`` 行を JSON パースし、token を結合して返す。
        """
        url = self.base_url + path
        data = None
        headers = self._headers()
        headers["Accept"] = "text/event-stream"
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return json.loads(raw)
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}: {e.reason} ({url})"}
        except urllib.error.URLError as e:
            return {"ok": False, "error": f"Connection failed ({self.base_url}): {e.reason}"}
        except Exception as e:
            return {"ok": False, "error": f"{e} ({url})"}

        tokens: list[str] = []
        last_data: dict = {}
        try:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
                if not line.startswith("data: "):
                    continue
                try:
                    chunk = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if "token" in chunk:
                    tokens.append(chunk["token"])
                if "error" in chunk:
                    return {"ok": False, "error": chunk["error"]}
                last_data = chunk
        finally:
            resp.close()

        full_text = last_data.get("full_text", "".join(tokens))
        result: dict[str, Any] = {"status": "ok", "text": full_text}
        # Transfer meta info from SSE initial data
        for key in ("conversation_id", "title", "search_results", "vlm"):
            if key in last_data:
                result[key] = last_data[key]
        return result
