import os


def load_env() -> None:
    """
    Load .env if python-dotenv is installed.
    Safe to call multiple times.
    """
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    load_dotenv()


def env_bool(key: str, default: str = "0") -> bool:
    return os.environ.get(key, default).lower() in ("1", "true", "yes", "on")

