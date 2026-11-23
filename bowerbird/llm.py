"""One structured model call, on whichever provider is configured.

`complete()` takes a prompt and a JSON schema and returns the JSON object the
model produced, or None when the model refused. Two providers:

  anthropic (default)  the anthropic SDK, keyed by ANTHROPIC_API_KEY
  openai               any OpenAI-compatible chat-completions endpoint, reached
                       through OPENAI_BASE_URL and OPENAI_API_KEY — OpenAI,
                       OpenRouter, Ollama, LM Studio, vLLM and the like

Whatever goes wrong raises LLMError, which says what the user can do about it.
"""

from __future__ import annotations

import json
import os
import time

import httpx

from .models import ASSIGN_DEFAULT, TAXONOMY_DEFAULT

PROVIDERS = ("anthropic", "openai")
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
TIMEOUT = httpx.Timeout(600.0, connect=10.0)
MODEL_VARIABLES = ("BOWERBIRD_TAXONOMY_MODEL", "BOWERBIRD_ASSIGN_MODEL", "BOWERBIRD_CHAT_MODEL")
MODELS_ADVICE = "set BOWERBIRD_TAXONOMY_MODEL, BOWERBIRD_ASSIGN_MODEL and BOWERBIRD_CHAT_MODEL"


class LLMError(Exception):
    """A model call that could not complete.

    `status` is the provider's HTTP status when there was one. `advice` is set
    when the fix is on the user's side — a key, a model name, a URL — rather
    than the provider's.
    """

    def __init__(self, message: str, *, status: int | None = None, advice: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.advice = advice

    def __str__(self) -> str:
        return f"{self.args[0]} — {self.advice}" if self.advice else str(self.args[0])


def provider() -> str:
    value = os.environ.get("BOWERBIRD_LLM_PROVIDER", "anthropic").strip().lower()
    if value not in PROVIDERS:
        raise LLMError(f"BOWERBIRD_LLM_PROVIDER is {value!r}, not one of {', '.join(PROVIDERS)}",
                       advice="unset it for Anthropic, or set it to openai")
    return value


def complete(user: str, schema: dict, max_tokens: int, *, model: str,
             system: str | None = None, effort: str | None = None) -> dict | None:
    """The model's answer as a dict matching `schema`, or None when it refused.

    `effort` is Anthropic's reasoning effort; other providers ignore it.
    """
    if provider() == "anthropic":
        return _anthropic(user, schema, max_tokens, model, system, effort)
    # The built-in model IDs are Anthropic's; a compatible server will not have them.
    if model in (TAXONOMY_DEFAULT, ASSIGN_DEFAULT) and model not in {
            os.environ.get(name) for name in MODEL_VARIABLES}:
        raise LLMError(f"{model!r} is an Anthropic model ID", advice=MODELS_ADVICE)
    return _openai_compatible(user, schema, max_tokens, model, system)


def _anthropic(user: str, schema: dict, max_tokens: int, model: str,
               system: str | None, effort: str | None) -> dict | None:
    import anthropic

    output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort
    kwargs: dict = {"output_config": output_config}
    if system:
        # The assignment rules and taxonomy repeat for every batch: cache them.
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    try:
        response = anthropic.Anthropic().messages.create(
            model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": user}], **kwargs)
    except anthropic.APIError as exc:
        raise LLMError(f"the Anthropic API failed: {exc.message}",
                       status=getattr(exc, "status_code", None)) from exc
    except TypeError as exc:
        if "authentication" not in str(exc).lower():
            raise
        raise LLMError("no Anthropic API key was found", advice="set ANTHROPIC_API_KEY") from exc
    if response.stop_reason == "refusal":
        return None
    return _parse(next((block.text for block in response.content if block.type == "text"), None))


def _openai_compatible(user: str, schema: dict, max_tokens: int, model: str,
                       system: str | None) -> dict | None:
    base = os.environ.get("OPENAI_BASE_URL", OPENAI_DEFAULT_BASE).rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise LLMError(f"OPENAI_BASE_URL {base!r} needs an http:// or https:// prefix")
    headers = {"Content-Type": "application/json"}
    if os.environ.get("OPENAI_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['OPENAI_API_KEY']}"
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": user}]
    body: dict = {
        "model": model, "messages": messages, "max_tokens": max_tokens,
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "bowerbird", "strict": True, "schema": schema}},
    }
    url = f"{base}/chat/completions"

    with httpx.Client(timeout=TIMEOUT) as client:
        for _ in range(3):
            status, text = _post(client, url, headers, body)
            if status == 200:
                break
            # Compatible servers differ on structured output and on the token-limit
            # field; each rejects the request with a 400 that names the offender.
            if status in (400, 422) and "response_format" in text:
                body.pop("response_format", None)
                body["messages"] = [{"role": "system",
                                     "content": "Answer with one JSON object and nothing else."}] + messages
            elif status in (400, 422) and "max_completion_tokens" in text:
                body["max_completion_tokens"] = body.pop("max_tokens")
            else:
                raise _openai_error(status, text, base, model)
        else:
            raise LLMError(f"the server at {base} kept rejecting the request: {text[:200]}",
                           status=status)

    try:
        choice = json.loads(text)["choices"][0]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"the server at {base} sent something other than a chat completion: "
                       f"{text[:200]!r}") from exc
    if choice.get("finish_reason") == "content_filter":
        return None
    return _parse((choice.get("message") or {}).get("content"))


def _post(client: httpx.Client, url: str, headers: dict, body: dict) -> tuple[int, str]:
    """(status, body text). A busy or unreachable server is tried three times."""
    for attempt in range(3):
        try:
            resp = client.post(url, headers=headers, json=body)
        except httpx.UnsupportedProtocol as exc:
            raise LLMError(f"OPENAI_BASE_URL {url!r} needs an http:// or https:// prefix") from exc
        except httpx.InvalidURL as exc:
            raise LLMError(f"OPENAI_BASE_URL is not a valid URL: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise LLMError(f"{url} did not answer in time") from exc
        except httpx.HTTPError as exc:
            if attempt == 2:
                raise LLMError(f"could not reach {url}: {exc}") from exc
        else:
            if resp.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                return resp.status_code, resp.text
        time.sleep(2 * (attempt + 1))
    raise LLMError(f"could not reach {url}")


def _openai_error(status: int, text: str, base: str, model: str) -> LLMError:
    try:
        message = str(json.loads(text)["error"]["message"])
    except (ValueError, KeyError, TypeError):
        message = text[:300] or "(no body)"
    if status in (401, 403):
        return LLMError(f"the server at {base} rejected the request: {message}", status=status,
                        advice="check OPENAI_API_KEY")
    if status == 404 and "model" in message.lower():
        return LLMError(f"the server at {base} does not know the model {model!r}", status=status,
                        advice=MODELS_ADVICE)
    return LLMError(f"the server at {base} answered {status}: {message}", status=status)


def _parse(text: str | None) -> dict:
    if text is None:
        raise LLMError("the model returned no text")
    candidates = [text]
    if "{" in text:
        candidates.append(text[text.index("{"):text.rindex("}") + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
        break
    raise LLMError("the model's answer was not a JSON object")
