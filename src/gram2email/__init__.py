"""gram2email: Periodically fetch public Instagram posts and email their contents.

This package provides functional components, state tracking, and lifecycle hooks
for fetching public Instagram posts anonymously and transmitting them via SMTP.
"""

from gram2email.cli import main
from gram2email.config import AppSettings, SMTPSettings, User
from gram2email.hooks import (
    AFTER_SEND,
    BEFORE_SEND,
    ON_ACCOUNT_END,
    ON_ACCOUNT_START,
    ON_ERROR,
    ON_POST_DISCOVERED,
    HookRegistry,
    create_hook_registry,
    register_hook,
    trigger_hook,
)
from gram2email.instagram import (
    InstagramPost,
    MediaItem,
    create_loader,
    fetch_recent_posts,
)
from gram2email.mailer import (
    build_post_email,
    format_html,
    format_plain_text,
    send_email,
)
from gram2email.pipeline import run_pipeline
from gram2email.storage import (
    is_post_seen,
    load_seen_posts,
    mark_post_seen,
    save_seen_posts,
)

__all__ = [
    "AFTER_SEND",
    "BEFORE_SEND",
    "ON_ACCOUNT_END",
    "ON_ACCOUNT_START",
    "ON_ERROR",
    "ON_POST_DISCOVERED",
    "AppSettings",
    "HookRegistry",
    "InstagramPost",
    "MediaItem",
    "SMTPSettings",
    "User",
    "build_post_email",
    "create_hook_registry",
    "create_loader",
    "fetch_recent_posts",
    "format_html",
    "format_plain_text",
    "is_post_seen",
    "load_seen_posts",
    "main",
    "mark_post_seen",
    "register_hook",
    "run_pipeline",
    "save_seen_posts",
    "send_email",
    "trigger_hook",
]
