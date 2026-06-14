#!/usr/bin/env python3
"""Shared cursor-agent CLI argv for non-interactive (headless) runs."""


def argv(prompt, model="composer-2.5"):
    """Build cursor-agent command; --force trusts the workspace without a TTY prompt."""
    return ["cursor-agent", "-p", "--force", "--model", model, prompt]
