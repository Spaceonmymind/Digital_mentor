from app.core.errors import AppError


class LLMError(AppError):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 502,
        details: dict | None = None,
        retryable: bool = False,
    ):
        self.retryable = retryable
        super().__init__(code, message, status_code=status_code, details=details)


class LLMConfigurationError(LLMError):
    def __init__(self, message: str = "LLM provider is not configured"):
        super().__init__("LLM_CONFIGURATION_ERROR", message, status_code=500)


class LLMResponseValidationError(LLMError):
    def __init__(self, details: dict | None = None):
        super().__init__("LLM_RESPONSE_VALIDATION_ERROR", "LLM returned invalid structured response", details=details)
