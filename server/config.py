import os

THINKING_MODEL: str = os.getenv("THINKING_MODEL", "openai/gpt-oss-120b")
SMALL_MODEL: str = os.getenv("SMALL_MODEL", "llama-3.1-8b-instant")