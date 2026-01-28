"""LLM backend abstraction layer for OpenAI-compatible API and mlx-lm."""

import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from an LLM backend."""

    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMBackend(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        """Send a chat completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.
            timeout: Request timeout in seconds.

        Returns:
            LLMResponse with the generated content and token usage.
        """

    @abstractmethod
    def check_connection(self) -> bool:
        """Check if the LLM backend is available."""

    @abstractmethod
    def get_available_models(self) -> list[str]:
        """Get list of available models."""


class OpenAIBackend(LLMBackend):
    """Backend using an OpenAI-compatible API (e.g. LM Studio, Ollama)."""

    def __init__(self, host: str, port: int, model: str) -> None:
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(
            base_url=f"http://{host}:{port}/v1",
            api_key="lm-studio",
            timeout=30.0,
        )

    def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        client = self._client
        if timeout is not None:
            client = self._client.with_options(timeout=timeout)

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content

        usage = getattr(response, "usage", None)
        if usage:
            return LLMResponse(
                content=content,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
        return LLMResponse(content=content)

    def check_connection(self) -> bool:
        try:
            response = self._client.models.list()
            model_ids = [m.id for m in response.data]
            return self.model in model_ids or len(model_ids) > 0
        except Exception:
            return False

    def get_available_models(self) -> list[str]:
        try:
            response = self._client.models.list()
            return [m.id for m in response.data]
        except Exception:
            return []


class MLXBackend(LLMBackend):
    """Backend using mlx-lm for local inference on Apple Silicon."""

    def __init__(self, model: str) -> None:
        try:
            from mlx_lm import generate, load
            from mlx_lm.sample_utils import make_sampler
        except ImportError:
            raise ImportError(
                "mlx-lm is required for the mlx backend. "
                "Install it with: pip install -e '.[mlx]'"
            )

        self.model_name = model
        self._load = load
        self._generate = generate
        self._make_sampler = make_sampler
        self._lock = threading.Lock()
        self._model, self._tokenizer = load(model)

    def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        sampler = self._make_sampler(temp=temperature)
        kwargs: dict = {"sampler": sampler}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        with self._lock:
            content = self._generate(
                self._model, self._tokenizer, prompt=prompt, verbose=False, **kwargs
            )

        # Strip reasoning/thinking tags (handle missing opening tag too)
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
        content = re.sub(r"^.*?</think>\s*", "", content, flags=re.DOTALL)

        return LLMResponse(content=content)

    def check_connection(self) -> bool:
        return self._model is not None

    def get_available_models(self) -> list[str]:
        return [self.model_name]


def create_backend(config: dict) -> LLMBackend:
    """Factory function to create the appropriate LLM backend from config.

    Config keys used:
        llm.backend: "mlx" or "openai" (default: "mlx")
        llm.model: model name/path
        llm.host: API host (openai backend only)
        llm.port: API port (openai backend only)
    """
    llm_config = config.get("llm", {})
    backend_type = llm_config.get("backend", "mlx")
    model = llm_config.get("model", "mlx-community/GLM-4.7-Flash-4bit")

    if backend_type == "openai":
        host = llm_config.get("host", "localhost")
        port = llm_config.get("port", 1234)
        return OpenAIBackend(host=host, port=port, model=model)
    elif backend_type == "mlx":
        return MLXBackend(model=model)
    else:
        raise ValueError(f"Unknown LLM backend: {backend_type!r}. Use 'mlx' or 'openai'.")
