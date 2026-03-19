#!/usr/bin/env python3
"""
Audio server entry point.

Implementation lives in `audio/app/`.
"""

import os

from app.api import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("AUDIO_HOST", "0.0.0.0")
    port = int(os.environ.get("AUDIO_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
