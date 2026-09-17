"""Pipeline execution orchestrator for gram2email.

Coordinates state persistence, Instagram post scraping, hook callbacks,
and email dispatching across configured accounts.
"""

import logging

from gram2email.config import AppSettings
from gram2email.hooks import (
    AFTER_SEND,
    BEFORE_SEND,
    ON_ACCOUNT_END,
    ON_ACCOUNT_START,
    ON_ERROR,
    ON_POST_DISCOVERED,
    HookRegistry,
    create_logging_hooks,
    trigger_hook,
)
from gram2email.instagram import create_loader, fetch_recent_posts
from gram2email.mailer import build_post_email, send_email
from gram2email.storage import (
    is_post_seen,
    load_seen_posts,
    mark_post_seen,
    save_seen_posts,
)

logger = logging.getLogger(__name__)


def run_pipeline(
    settings: AppSettings,
    hooks: HookRegistry | None = None,
) -> int:
    """Execute the gram2email scraping and email dispatch pipeline.

    Loads the historical state of seen posts, iterates through each configured
    account, retrieves recent posts, filters out posts that have already been
    processed, sends emails for any new posts found, and updates persistent state.

    Parameters
    ----------
    settings : AppSettings
        Application configuration settings.
    hooks : HookRegistry or None, default None
        Optional lifecycle hook registry. If None and settings.verbose is True,
        default logging hooks are attached.

    Returns
    -------
    int
        Total number of new posts processed and emailed during this run.

    Raises
    ------
    ValueError
        If required settings (such as accounts or recipients) are missing.
    """
    if not settings.accounts:
        logger.warning("No Instagram accounts configured in settings.")
        return 0

    effective_recipients = settings.effective_recipients
    if not effective_recipients and not settings.dry_run:
        raise ValueError("No email recipients configured. Specify at least one user or recipient email.")

    active_hooks = hooks
    if active_hooks is None:
        active_hooks = create_logging_hooks(logger)

    state_path = settings.state_path
    seen_posts = load_seen_posts(state_path)
    total_processed = 0

    loader = create_loader(
        request_timeout=float(settings.request_timeout),
        session_file=settings.session_file,
        session_id=settings.session_id,
        instagram_user=settings.instagram_user,
    )

    for account in settings.accounts:
        account_sent = 0
        trigger_hook(active_hooks, ON_ACCOUNT_START, account)

        try:
            posts = fetch_recent_posts(
                account=account,
                max_posts=settings.max_posts_per_account,
                loader=loader,
                download_media=settings.download_media,
            )
        except Exception as exc:
            logger.error("Failed to retrieve posts for @%s: %s", account, exc)
            trigger_hook(active_hooks, ON_ERROR, f"fetch_posts(@{account})", exc)
            continue

        # Filter for unseen posts and sort chronologically (oldest new post first)
        new_posts = [p for p in posts if not is_post_seen(seen_posts, p.shortcode)]
        new_posts.sort(key=lambda p: p.date_utc)

        for post in new_posts:
            trigger_hook(active_hooks, ON_POST_DISCOVERED, account, post)

            msg = build_post_email(
                post=post,
                sender=settings.smtp.effective_sender,
                recipients=effective_recipients,
            )

            trigger_hook(active_hooks, BEFORE_SEND, msg, post)

            if settings.dry_run:
                logger.info(
                    "[DRY RUN] Would send email for @%s post %s to %s",
                    account,
                    post.shortcode,
                    ", ".join(effective_recipients),
                )
                trigger_hook(active_hooks, AFTER_SEND, post, True)
                account_sent += 1
                total_processed += 1
                continue

            try:
                send_email(msg, settings.smtp)
                seen_posts = mark_post_seen(seen_posts, post.shortcode)
                save_seen_posts(state_path, seen_posts)
                trigger_hook(active_hooks, AFTER_SEND, post, True)
                account_sent += 1
                total_processed += 1
            except Exception as exc:
                logger.error(
                    "Failed to email post %s for @%s: %s",
                    post.shortcode,
                    account,
                    exc,
                )
                trigger_hook(active_hooks, AFTER_SEND, post, False)
                trigger_hook(active_hooks, ON_ERROR, f"send_email({post.shortcode})", exc)

        trigger_hook(active_hooks, ON_ACCOUNT_END, account, account_sent)

    return total_processed
