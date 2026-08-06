from app.core.errors import AppError


class ExecutionError(AppError):
    pass


def execution_error(code: str, message: str, status_code: int = 400, details: dict | None = None) -> ExecutionError:
    return ExecutionError(code, message, status_code=status_code, details=details)
