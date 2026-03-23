import os

# Путь к audio/.env (config.py в audio/app/)
_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def load_env() -> None:
    """
    Load .env from audio/ if python-dotenv is installed.
    Safe to call multiple times.
    """
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    load_dotenv(_ENV_PATH)


def env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: str = "0") -> bool:
    return os.environ.get(key, default).lower() in ("1", "true", "yes", "on")

