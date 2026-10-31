class DomainError(Exception):
    status = 500
    code = "internal_error"

    def __init__(self, code: str | None = None, extra: dict[str, object] | None = None) -> None:
        self.code = code or self.code
        self.extra = extra or {}
        super().__init__(self.code)


class NotFound(DomainError):  # noqa: N818 -- domain names are part of the service API
    status = 404
    code = "not_found"


class Conflict(DomainError):  # noqa: N818 -- domain names are part of the service API
    status = 409
    code = "conflict"


class Invalid(DomainError):  # noqa: N818 -- domain names are part of the service API
    status = 422
    code = "validation_error"


class Forbidden(DomainError):  # noqa: N818 -- domain names are part of the service API
    status = 403
    code = "forbidden"


class Unauthorized(DomainError):  # noqa: N818 -- domain names are part of the service API
    status = 401
    code = "unauthorized"


class PaymentRequired(DomainError):  # noqa: N818 -- domain names are part of the service API
    status = 402
    code = "budget_exceeded"


class BadGateway(DomainError):  # noqa: N818 -- domain names are part of the service API
    status = 502
    code = "llm_output_invalid"


class VersionConflict(Conflict):
    code = "version_conflict"
