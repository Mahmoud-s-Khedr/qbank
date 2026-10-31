"""Public exceptions raised by the LLM layer."""


class LLMError(Exception):
    """Base class for LLM failures."""


class LLMNotConfigured(LLMError):
    pass


class ModelNotAllowed(LLMError):
    pass


class ModelTooExpensive(LLMError):
    pass


class BudgetExceeded(LLMError):
    pass


class OrgBudgetExceeded(LLMError):
    pass


class LLMOutputInvalid(LLMError):
    pass
