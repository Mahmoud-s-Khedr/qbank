"""Public exceptions raised by the LLM layer."""

from decimal import Decimal


class LLMError(Exception):
    """Base class for LLM failures."""

    # Spend already incurred by the failed call (0 when it failed before any request).
    cost_usd: Decimal = Decimal(0)


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


# Errors that mean "fix the configuration or budget, then resume": the pipeline pauses the
# source instead of failing its pages (a missing key must not burn a whole workbook).
PAUSE_ERRORS: tuple[type[LLMError], ...] = (
    BudgetExceeded,
    OrgBudgetExceeded,
    LLMNotConfigured,
    ModelNotAllowed,
    ModelTooExpensive,
)
