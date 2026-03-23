#!/usr/bin/env python3
"""
Audio server entry point.

Implementation lives in `audio/app/`.
"""

from app import config

config.load_env()

from app.api import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = config.env_str("AUDIO_HOST", "0.0.0.0")
    port = int(config.env_str("AUDIO_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
