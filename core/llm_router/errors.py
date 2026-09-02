"""Exception hierarchy for the LLM router."""


class LLMRouterError(Exception):
    """Base for all router-specific exceptions."""


class BackendNotFoundError(LLMRouterError):
    """Target alias / physical name / category did not resolve to any backend."""


class BackendDisabledError(LLMRouterError):
    """Raised when dispatch targets a backend that is administratively disabled.

    Distinct from BackendNotFoundError so HTTP layer can return 503 (Service
    Unavailable) instead of 404, and clients can avoid retry loops that would
    otherwise treat disabled as 'model deleted'.

    The `alias` attribute exposes the backend alias as structured data so
    callers (e.g. the HTTP layer) do not need to parse it out of the message.
    """

    def __init__(self, alias: str, message: str | None = None) -> None:
        self.alias = alias
        super().__init__(message or f"backend '{alias}' is administratively disabled")


class BackendUnreachableError(LLMRouterError):
    """The backend host is unreachable (network / DNS / connect failure)."""


class BackendTimeoutError(LLMRouterError):
    """The backend did not respond within the configured timeout."""


class TranslationError(LLMRouterError):
    """Failed to translate a request or response between protocols."""


class NotImplementedFeatureError(LLMRouterError):
    """The requested feature (image, prefill, etc.) is not implemented in this version."""


class AuthenticationError(LLMRouterError):
    """Auth check failed."""
