class ConflictError(ValueError):
    pass


class DatabaseUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("The database is temporarily unavailable. Please try again.")
