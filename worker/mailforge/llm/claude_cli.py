"""Alternative backend: headless Claude Code (`claude -p --tools ""`), prompt via stdin.

Requires the `claude` binary in the image (the `-cli` image tag / INSTALL_CLAUDE_CLI=true).
Auth, either:
  * ANTHROPIC_API_KEY  -> runs with `--bare` (fast, ignores local config), or
  * CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`, Claude subscription) -> `--bare` is
    omitted because bare mode only authenticates with an API key.
"""
from __future__ import annotations

import json
import os
import subprocess

from .anthropic_sdk import Usage


class CliClient:
    def __init__(self, pricing: dict | None = None, timeout: int = 300):
        self.timeout = timeout

    def complete(self, model: str, system: str, user: str, max_tokens: int) -> tuple[str, Usage]:
        # max_tokens is not controllable via the CLI; prompts already ask for terse output.
        cmd = ["claude", "-p", "--tools", "", "--model", model,
               "--system-prompt", system, "--output-format", "json"]
        if os.environ.get("ANTHROPIC_API_KEY"):
            cmd.insert(2, "--bare")
        p = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=self.timeout)
        if p.returncode != 0:
            raise RuntimeError(f"claude CLI exit {p.returncode}: {p.stderr.strip()[:200]}")
        j = json.loads(p.stdout)
        if j.get("is_error"):
            raise RuntimeError(f"claude CLI error: {str(j.get('result'))[:200]}")
        us = j.get("usage") or {}
        return j.get("result", ""), Usage(
            input=us.get("input_tokens", 0), output=us.get("output_tokens", 0),
            cache_read=us.get("cache_read_input_tokens", 0),
            cache_write=us.get("cache_creation_input_tokens", 0),
            cost=float(j.get("total_cost_usd") or 0.0),
        )
