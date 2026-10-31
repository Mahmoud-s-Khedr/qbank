"""The sole entry point for model calls."""

from qbank.llm.client import (
    FakeLLMClient,
    LLMClient,
    LLMResult,
    OpenRouterClient,
    RecordedLLMClient,
    get_llm_client,
    image_part,
)
from qbank.llm.errors import (
    BudgetExceeded,
    LLMError,
    LLMNotConfigured,
    LLMOutputInvalid,
    ModelNotAllowed,
    ModelTooExpensive,
    OrgBudgetExceeded,
)

__all__ = [
    "BudgetExceeded",
    "FakeLLMClient",
    "LLMClient",
    "LLMError",
    "LLMNotConfigured",
    "LLMOutputInvalid",
    "LLMResult",
    "ModelNotAllowed",
    "ModelTooExpensive",
    "OpenRouterClient",
    "OrgBudgetExceeded",
    "RecordedLLMClient",
    "get_llm_client",
    "image_part",
]
