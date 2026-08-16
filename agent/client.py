from __future__ import annotations

import os

from openai import OpenAI


class ModelConfigurationError(RuntimeError):
    """Raised when the real model client has not been configured."""


class ModelClient:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ModelConfigurationError("OPENAI_API_KEY is required for a model call")

        model = os.getenv("AGENT_MODEL")
        if not model:
            raise ModelConfigurationError("AGENT_MODEL is required for a model call")

        base_url = os.getenv("OPENAI_BASE_URL") or None
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("the model returned an empty response")
        return content.strip()
