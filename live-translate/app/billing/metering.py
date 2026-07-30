"""Token -> char (字数) conversion and upstream usage extraction.

We bill against the same token usage DashScope reports (so cost and revenue
align 1:1). For display we convert tokens to "翻译字数" using ~1.5 Chinese
characters per token.
"""
from __future__ import annotations

import math

from app.billing.quota import IMAGE_TOKENS_PER_FRAME, TOKENS_PER_CHAR


def extract_usage(event: dict) -> tuple[int, int]:
    """Return (input_tokens, output_tokens) from a response.done usage block."""
    usage = (event.get("response") or {}).get("usage") or {}
    in_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    out_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    return in_tokens, out_tokens


def usage_to_chars(
    in_tokens: int = 0, out_tokens: int = 0, image_frames: int = 0
) -> int:
    """Convert audio/text/image token usage into billable 字数."""
    total_tokens = (
        (in_tokens or 0)
        + (out_tokens or 0)
        + (image_frames or 0) * IMAGE_TOKENS_PER_FRAME
    )
    return max(0, int(math.ceil(total_tokens / TOKENS_PER_CHAR)))
