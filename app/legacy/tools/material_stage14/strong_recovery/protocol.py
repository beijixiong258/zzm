"""Non-streaming OpenAI-compatible client. Only numeric loopback, no lifecycle.

An injectable transport is for explicitly labelled protocol fixtures, not GPU
acceptance. Records preserve exact request/response bytes as base64 + SHA256.
No retries, proxy environment, redirects, model loading, leases, or GPU commands.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import http.client
import ipaddress
import json
from typing import Callable
from urllib.parse import urlsplit

SOURCE_FAITHFUL_PROMPT = """Transcribe only the visible literal text in this source image, one physical reading-order line per string. Preserve source spelling, capitalization, punctuation, digits, symbols, bullets, and end-of-line hyphens exactly, even when a name or word looks unusual. Never correct spelling or substitute a familiar name. Do not complete missing, clipped, faint, or unreadable text from context. Do not summarize, explain, infer relationships, or reconstruct table/diagram structure. A linear transcription is not table topology or diagram semantics. Return only a JSON object with keys \"lines\" (array of strings) and \"uncertainties\" (array of objects with zero-based \"line_index\" and \"reason\"; use null line_index for uncertainty affecting the whole image). Include uncertain observed lines rather than silently dropping them; describe their uncertainty separately. Do not add invisible text, page numbers, references, or citations. An empty uncertainties array is only your report, not verification."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class HTTPReply:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


Transport = Callable[[str, bytes, float], HTTPReply]


def loopback_endpoint(base_url: str) -> str:
    parts = urlsplit(base_url)
    if parts.scheme != "http" or parts.username is not None or parts.password is not None:
        raise ValueError("Only plain HTTP numeric loopback URLs without credentials are supported")
    try:
        address = ipaddress.ip_address(parts.hostname or "")
        port = parts.port
    except ValueError as exc:
        raise ValueError("Use an explicit numeric loopback host and valid port") from exc
    if not address.is_loopback or port is None or parts.query or parts.fragment:
        raise ValueError("Explicit loopback host/port, no query or fragment, required")
    if parts.path.rstrip("/") not in ("", "/v1"):
        raise ValueError("Base URL must be http://127.0.0.1:PORT[/v1] or IPv6 equivalent")
    return f"http://{parts.netloc}/v1/chat/completions"


def http_transport(url: str, body: bytes, timeout: float) -> HTTPReply:
    parts = urlsplit(url)
    # http.client ignores HTTP_PROXY and does not follow redirects.
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    try:
        connection.request("POST", parts.path, body=body,
                           headers={"Content-Type": "application/json", "Accept": "application/json"})
        response = connection.getresponse()
        return HTTPReply(response.status, tuple(response.getheaders()), response.read())
    finally:
        connection.close()


def generation_from_reply(reply: HTTPReply) -> tuple[dict, object]:
    """Extract transport finish evidence, never a finish claimed inside model text."""
    errors = []
    if reply.status != 200:
        errors.append("http_status_not_200")
    parsed = None
    try:
        parsed = json.loads(reply.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append("invalid_response_json")
    generation = {"content": None, "finish_reason": None, "usage": None,
                  "finish_provenance": "openai_compatible_response_choice",
                  "protocol_errors": errors}
    if not isinstance(parsed, dict):
        if "invalid_response_json" not in errors:
            errors.append("response_not_object")
        return generation, parsed
    generation["usage"] = parsed.get("usage")
    choices = parsed.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        errors.append("expected_exactly_one_choice")
        return generation, parsed
    choice = choices[0]
    generation["finish_reason"] = choice.get("finish_reason")
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        errors.append("missing_text_message_content")
    else:
        generation["content"] = message["content"]
    return generation, parsed


class LoopbackLineClient:
    def __init__(self, base_url: str, model: str, *, transport: Transport | None = None,
                 timeout: float = 180, max_tokens: int = 2048):
        self.endpoint = loopback_endpoint(base_url)
        if not isinstance(model, str) or not model.strip():
            raise ValueError("An explicit model alias is required")
        if timeout <= 0 or isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("Positive timeout and integer max_tokens required")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.transport = transport or http_transport
        self.injected = transport is not None

    def transcribe(self, image: bytes, *, mime: str = "image/png",
                   evidence_kind: str = "unclassified_protocol_capture") -> dict:
        if mime not in {"image/png", "image/jpeg", "image/webp"} or not image:
            raise ValueError("A nonempty supported image is required")
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": SOURCE_FAITHFUL_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Return source-faithful physical lines and uncertainties only."},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"}}]}],
                   "temperature": 0, "stream": False, "n": 1, "max_tokens": self.max_tokens,
                   "cache_prompt": False}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        record = {"schema": "strong-line-protocol-capture/1", "evidence_kind": evidence_kind,
                  "gpu_acceptance": False, "transport_injected": self.injected,
                  "endpoint": self.endpoint, "model_alias": self.model,
                  "image_sha256": sha256(image), "image_bytes": len(image), "mime": mime,
                  "prompt_sha256": sha256(SOURCE_FAITHFUL_PROMPT.encode("utf-8")),
                  "request": {"body_base64": base64.b64encode(body).decode("ascii"),
                              "body_sha256": sha256(body), "body_bytes": len(body)},
                  "response": None, "generation": None}
        try:
            reply = self.transport(self.endpoint, body, self.timeout)
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            record["transport_error"] = {"type": type(exc).__name__, "message": str(exc)}
            record["generation"] = {"content": None, "finish_reason": None, "usage": None,
                                    "finish_provenance": "none",
                                    "protocol_errors": ["transport_failure"]}
            return record
        generation, parsed = generation_from_reply(reply)
        generation["input_image_sha256"] = sha256(image)
        record["response"] = {"status": reply.status, "headers": list(reply.headers),
                              "body_base64": base64.b64encode(reply.body).decode("ascii"),
                              "body_sha256": sha256(reply.body), "body_bytes": len(reply.body),
                              "parsed": parsed}
        record["generation"] = generation
        return record
