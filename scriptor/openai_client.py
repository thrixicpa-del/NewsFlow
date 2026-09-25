from __future__ import annotations

import asyncio
import base64
import io
import json
import urllib.error
import urllib.request


class OpenAIAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def key_unavailable(self):
        value = str(self).lower()
        return self.status_code in (401, 403, 429) or "quota" in value or "billing" in value


class OpenAITextClient:
    def __init__(self, api_key: str, model: str = "gpt-5.4-mini", label: str = "OpenAI"):
        self.api_key = api_key.strip()
        self.model = model.strip() or "gpt-5.4-mini"
        self.label = label

    def _request(self, method, path, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            "https://api.openai.com" + path, data=body, method=method,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenAIAPIError(f"{self.label}: OpenAI API ({exc.code}): {detail}", exc.code) from exc
        except urllib.error.URLError as exc:
            raise OpenAIAPIError(f"{self.label}: ошибка сети OpenAI: {exc.reason}") from exc

    @staticmethod
    def _reference_content(image_paths: list[str] | None) -> list[dict]:
        """Make compact vision inputs; never upload an original larger than needed."""
        if not image_paths:
            return []
        content: list[dict] = []
        for raw_path in image_paths[:6]:
            try:
                from PIL import Image
                with Image.open(raw_path) as source:
                    image = source.convert("RGB")
                    image.thumbnail((1024, 1024))
                    encoded = io.BytesIO()
                    image.save(encoded, format="JPEG", quality=84, optimize=True)
                data_url = "data:image/jpeg;base64," + base64.b64encode(encoded.getvalue()).decode("ascii")
                content.append({"type": "input_image", "image_url": data_url, "detail": "low"})
            except Exception:
                # A broken or unsupported reference must not cancel a whole
                # batch of thumbnails; FastGen still receives valid files.
                continue
        return content

    async def generate(self, prompt: str, on_progress=None, before_request=None,
                       image_paths: list[str] | None = None,
                       max_output_tokens: int | None = None) -> str:
        content = [{"type": "input_text", "text": prompt}] + self._reference_content(image_paths)
        request_input: object = prompt if len(content) == 1 else [{"role": "user", "content": content}]
        payload = {"model": self.model, "input": request_input}
        if max_output_tokens and max_output_tokens > 0:
            payload["max_output_tokens"] = int(max_output_tokens)
        result = await asyncio.to_thread(
            self._request, "POST", "/v1/responses", payload
        )
        text = result.get("output_text", "")
        if not text:
            parts = []
            for output in result.get("output", []):
                for content in output.get("content", []):
                    if content.get("type") in ("output_text", "text") and content.get("text"):
                        parts.append(content["text"])
            text = "\n".join(parts)
        if not text:
            raise OpenAIAPIError(f"{self.label}: OpenAI не вернул текст")
        if on_progress:
            on_progress(text)
        return text

    def validate(self):
        return self._request("GET", "/v1/models")


class HybridTextPool:
    """A key pool for ChatGPT and NewsFlow's specialised text agents.

    The historical constructor kept ``sessions`` and ``chat_url`` parameters so
    existing saved routes remain compatible.  They are intentionally ignored:
    NewsFlow no longer sends work to browser-based Claude chats.
    """

    def __init__(self, sessions, openai_keys, chat_url, model="gpt-5.4-mini"):
        del sessions, chat_url
        self.openai_clients = [OpenAITextClient(item.secret, model, item.label) for item in openai_keys
                               if item.active and item.secret.strip()]
        if not self.openai_clients:
            raise ValueError("Добавьте активный API-ключ ChatGPT в разделе «API-ключи»")
        # Every enabled API key receives two independent queue slots.  Thus
        # adding another key immediately adds two simultaneous requests to all
        # batch tools that use HybridTextPool; no manual pool setup is needed.
        self._slots = [client for client in self.openai_clients for _ in range(2)]
        self.concurrency = len(self._slots)
        self._queue: asyncio.Queue[OpenAITextClient] | None = None

    async def generate(self, prompt: str, on_progress=None, before_request=None,
                       image_paths: list[str] | None = None,
                       max_output_tokens: int | None = None) -> str:
        if self._queue is None:
            self._queue = asyncio.Queue()
            for client in self._slots:
                self._queue.put_nowait(client)
        client = await self._queue.get()
        try:
            if before_request:
                await before_request()
            output_kwargs = {"max_output_tokens": max_output_tokens} if max_output_tokens else {}
            # Preserve compatibility with lightweight provider adapters and
            # tests that implement the historical two-argument method.
            if image_paths is None:
                return await client.generate(prompt, on_progress, **output_kwargs)
            return await client.generate(prompt, on_progress, image_paths=image_paths, **output_kwargs)
        except OpenAIAPIError as first:
            if not first.key_unavailable:
                raise
            for fallback in self.openai_clients:
                if fallback is client:
                    continue
                try:
                    if before_request:
                        await before_request()
                    if image_paths is None:
                        return await fallback.generate(prompt, on_progress, **output_kwargs)
                    return await fallback.generate(prompt, on_progress, image_paths=image_paths, **output_kwargs)
                except OpenAIAPIError as exc:
                    if not exc.key_unavailable:
                        raise
            raise first
        finally:
            self._queue.put_nowait(client)

    async def generate_fresh(self, prompt: str, on_progress=None, image_paths: list[str] | None = None,
                             max_output_tokens: int | None = None) -> str:
        return await self.generate(prompt, on_progress, image_paths=image_paths,
                                   max_output_tokens=max_output_tokens)

    async def generate_openai(self, prompt: str, on_progress=None, image_paths: list[str] | None = None,
                              max_output_tokens: int | None = None) -> str:
        return await self.generate(prompt, on_progress, image_paths=image_paths,
                                   max_output_tokens=max_output_tokens)
