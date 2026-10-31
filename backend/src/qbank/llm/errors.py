"""Public exceptions raised by the LLM layer."""

from decimal import Decimal


class LLMError(Exception):
    """Base class for LLM failures."""


class LLMNotConfigured(LLMError):
    pass


class ModelNotAllowed(LLMError):
    pass


class ModelTooExpensive(LLMError):
    pass


class BudgetExceeded(LLMError):
    cost_usd: Decimal = Decimal(0)


class OrgBudgetExceeded(LLMError):
    cost_usd: Decimal = Decimal(0)


class LLMOutputInvalid(LLMError):
    def __init__(self, message: str, *, cost_usd: Decimal = Decimal(0)) -> None:
        super().__init__(message)
        self.cost_usd = cost_usd
