"""Client for a local llama.cpp OpenAI-compatible server. No API key required."""
import json
import urllib.request
import urllib.error
from config import LOCAL_MODEL_BASE_URL, LOCAL_MODEL_NAME

class LocalModel:
    def __init__(self, base_url=LOCAL_MODEL_BASE_URL, model=LOCAL_MODEL_NAME, timeout=240):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _request_json(self, url, payload=None, timeout=5):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "UniversalCodeAI/1.1"},
            method="GET" if payload is None else "POST")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def health(self):
        url = self.base_url.rsplit("/v1", 1)[0] + "/health"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "UniversalCodeAI/1.1"})
            with urllib.request.urlopen(req, timeout=3) as response:
                raw = response.read(4096).decode("utf-8", "replace")
            try:
                details = json.loads(raw)
            except json.JSONDecodeError:
                details = raw.strip()
            return {"available": True, "details": details}
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def is_available(self):
        return self.health()["available"]

    def list_models(self):
        try:
            data = self._request_json(self.base_url + "/models", timeout=5)
            return {"success": True, "models": data.get("data", [])}
        except Exception as exc:
            return {"success": False, "error": str(exc), "models": []}

    def generate(self, prompt, system="", temperature=0.15, max_tokens=4096):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages, "temperature": temperature,
                   "max_tokens": max_tokens, "stream": False}
        try:
            body = self._request_json(self.base_url + "/chat/completions", payload, self.timeout)
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
            return {"success": bool(str(content).strip()), "content": str(content), "source": "local_model",
                    "usage": body.get("usage", {})}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            return {"success": False, "content": "", "error": f"HTTP {exc.code}: {detail}", "source": "local_model"}
        except Exception as exc:
            return {"success": False, "content": "", "error": str(exc), "source": "local_model"}
