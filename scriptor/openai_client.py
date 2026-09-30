from __future__ import annotations

import asyncio
import base64
import io
import json
import urllib.error
import urllib.request


def extract_visible_response_text(response: object) -> str:
    """Extract only user-visible text from a Responses payload.

    This is shared by the runtime and opt-in acceptance capture so a nested
    ``output[].content[].text`` response cannot be counted as an empty reply.
    Reasoning summaries and refusal metadata deliberately never become
    scenario prose or evidence output text.
    """
    if not isinstance(response, dict):
        return ""
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    parts: list[str] = []
    output = response.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if not isinstance(content, dict):
                continue
            if content.get("type") not in ("output_text", "text"):
                continue
            text = content.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts)


def extract_response_refusal(response: object) -> str:
    """Return a visible Responses refusal without treating it as prose."""
    if not isinstance(response, dict):
        return ""
    refusals: list[str] = []
    output = response.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if not isinstance(content, dict) or content.get("type") != "refusal":
                continue
            refusal = content.get("refusal")
            if isinstance(refusal, str) and refusal.strip():
                refusals.append(refusal.strip())
    return "\n".join(refusals)


class OpenAIAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

    @property
    def key_unavailable(self):
        value = str(self).lower()
        return self.status_code in (401, 403, 429) or "quota" in value or "billing" in value


class OpenAIResponseStatusError(OpenAIAPIError):
    """A delivered Responses object whose terminal state is not usable prose.

    The visible fragment is deliberately available to the Scenario runtime for
    review/persistence, but it is never returned as a completed Writer part.
    """

    def __init__(
        self,
        message: str,
        *,
        status: str,
        visible_text: str = "",
        response_id: str = "",
        incomplete_reason: str = "",
        refusal: str = "",
    ):
        super().__init__(message)
        self.status = status
        self.visible_text = visible_text
        self.response_id = response_id
        self.incomplete_reason = incomplete_reason
        self.refusal = refusal


class OpenAIResponseIncompleteError(OpenAIResponseStatusError):
    """The API observed an incomplete response, optionally with partial text."""


class OpenAIResponseRefusalError(OpenAIResponseStatusError):
    """The API returned an explicit refusal rather than scenario prose."""


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
            except Exception:  # noqa: BLE001, S112 - a bad optional image is non-fatal
                # A broken or unsupported reference must not cancel a whole
                # batch of thumbnails; FastGen still receives valid files.
                continue
        return content

    async def generate(self, prompt: str, on_progress=None, before_request=None,
                       image_paths: list[str] | None = None,
                       max_output_tokens: int | None = None,
                       instructions: str | None = None,
                       text_format: dict | None = None) -> str:
        content = [{"type": "input_text", "text": prompt}] + self._reference_content(image_paths)
        request_input: object = prompt if len(content) == 1 else [{"role": "user", "content": content}]
        payload = {"model": self.model, "input": request_input}
        if instructions and instructions.strip():
            payload["instructions"] = instructions.strip()
        if max_output_tokens and max_output_tokens > 0:
            payload["max_output_tokens"] = int(max_output_tokens)
        if text_format is not None:
            # Responses Structured Outputs belongs to ``text.format``.  The
            # trusted stage builder supplies this object; do not infer or
            # silently remove it after a provider error, which would create a
            # second differently-shaped logical request.
            payload["text"] = {"format": text_format}
        result = await asyncio.to_thread(
            self._request, "POST", "/v1/responses", payload
        )
        text = extract_visible_response_text(result)
        response_id = str(result.get("id", "") or "") if isinstance(result, dict) else ""
        status = str(result.get("status", "") or "").strip().lower() if isinstance(result, dict) else ""
        incomplete_details = result.get("incomplete_details") if isinstance(result, dict) else None
        incomplete_reason = (
            str(incomplete_details.get("reason", "") or "")
            if isinstance(incomplete_details, dict) else ""
        )
        refusal = extract_response_refusal(result)
        if refusal:
            raise OpenAIResponseRefusalError(
                f"{self.label}: OpenAI отказался выполнить запрос",
                status=status or "refusal",
                visible_text=text,
                response_id=response_id,
                refusal=refusal,
            )
        if status == "incomplete":
            raise OpenAIResponseIncompleteError(
                f"{self.label}: OpenAI вернул незавершённый ответ",
                status=status,
                visible_text=text,
                response_id=response_id,
                incomplete_reason=incomplete_reason,
            )
        if status in {"failed", "cancelled"}:
            raise OpenAIResponseStatusError(
                f"{self.label}: OpenAI завершил ответ со статусом {status}",
                status=status,
                visible_text=text,
                response_id=response_id,
                incomplete_reason=incomplete_reason,
            )
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
                       max_output_tokens: int | None = None,
                       instructions: str | None = None,
                       text_format: dict | None = None) -> str:
        if self._queue is None:
            self._queue = asyncio.Queue()
            for client in self._slots:
                self._queue.put_nowait(client)
        client = await self._queue.get()
        try:
            if before_request:
                await before_request()
            output_kwargs = {"max_output_tokens": max_output_tokens} if max_output_tokens else {}
            if instructions and instructions.strip():
                output_kwargs["instructions"] = instructions.strip()
            if text_format is not None:
                output_kwargs["text_format"] = text_format
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
            raise
        finally:
            self._queue.put_nowait(client)

    async def generate_fresh(self, prompt: str, on_progress=None, image_paths: list[str] | None = None,
                             max_output_tokens: int | None = None,
                             instructions: str | None = None,
                             text_format: dict | None = None) -> str:
        return await self.generate(prompt, on_progress, image_paths=image_paths,
                                   max_output_tokens=max_output_tokens, instructions=instructions,
                                   text_format=text_format)

    async def generate_openai(self, prompt: str, on_progress=None, image_paths: list[str] | None = None,
                              max_output_tokens: int | None = None,
                              instructions: str | None = None,
                              text_format: dict | None = None) -> str:
        return await self.generate(prompt, on_progress, image_paths=image_paths,
                                   max_output_tokens=max_output_tokens, instructions=instructions,
                                   text_format=text_format)
