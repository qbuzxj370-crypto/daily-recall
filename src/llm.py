"""LLM 공급자 경계.

애플리케이션은 이 모듈의 `invoke_structured`만 호출한다. LangChain이 모델 SDK 차이를
흡수하고, 새 공급자는 여기의 작은 어댑터 하나로 추가한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import settings


class LLMConfigurationError(RuntimeError):
    """모델 체인 또는 공급자 설정이 올바르지 않을 때 발생한다."""


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> "ModelTarget":
        provider, separator, model = value.strip().partition(":")
        if not separator or not provider or not model:
            raise LLMConfigurationError(
                "DR_MODEL_CHAIN의 각 값은 provider:model 형식이어야 합니다: "
                f"{value!r}"
            )
        return cls(provider=provider.lower(), model=model)

    def label(self) -> str:
        return f"{self.provider}:{self.model}"


def model_chain() -> list[ModelTarget]:
    """환경 설정을 순서가 있는 모델 대상 목록으로 변환한다."""
    values = [part for part in settings.MODEL_CHAIN.split(",") if part.strip()]
    if not values:
        raise LLMConfigurationError("DR_MODEL_CHAIN에 모델을 하나 이상 설정하세요.")
    return [ModelTarget.parse(value) for value in values]


def invoke_structured(
    target: ModelTarget,
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """공급자 고유 API를 숨기고 구조화된 결과를 dict로 정규화한다."""
    if target.provider == "gemini":
        return _invoke_gemini(
            target,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
        )
    raise LLMConfigurationError(
        f"지원하지 않는 provider: {target.provider}. 현재 지원: gemini"
    )


def _invoke_gemini(
    target: ModelTarget,
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Gemini 네이티브 JSON Schema 출력을 사용하는 LangChain 어댑터."""
    if not settings.GEMINI_API_KEY:
        raise LLMConfigurationError("GEMINI_API_KEY가 설정되지 않았습니다.")

    # 지연 import로 --mock 경로는 AI 라이브러리 설치 없이도 동작한다.
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = ChatGoogleGenerativeAI(
        model=target.model,
        api_key=settings.GEMINI_API_KEY,
        max_tokens=settings.MAX_TOKENS,
    )
    structured_model = model.with_structured_output(schema, method="json_schema")
    result = structured_model.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    if not isinstance(result, dict):
        raise TypeError(f"{target.label()}의 구조화 출력이 dict가 아님: {type(result).__name__}")
    return result
