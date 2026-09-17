"""Functional hooks and lifecycle event dispatcher for gram2email.

Provides a functional hook registry to observe and customize pipeline events
such as post discovery, email preparation, and transmission status.
"""

import logging
from collections.abc import Callable
from typing import Any

# Standard Hook Events
ON_ACCOUNT_START = "on_account_start"
ON_POST_DISCOVERED = "on_post_discovered"
BEFORE_SEND = "before_send"
AFTER_SEND = "after_send"
ON_ACCOUNT_END = "on_account_end"
ON_ERROR = "on_error"

HookRegistry = dict[str, list[Callable[..., Any]]]


def create_hook_registry() -> HookRegistry:
    """Create an empty hook registry mapping event names to callback lists.

    Returns
    -------
    HookRegistry
        A dictionary initialized with empty callback lists for standard events.
    """
    return {
        ON_ACCOUNT_START: [],
        ON_POST_DISCOVERED: [],
        BEFORE_SEND: [],
        AFTER_SEND: [],
        ON_ACCOUNT_END: [],
        ON_ERROR: [],
    }


def register_hook(
    registry: HookRegistry,
    event: str,
    callback: Callable[..., Any],
) -> HookRegistry:
    """Register a callback function for a specific lifecycle event.

    Parameters
    ----------
    registry : HookRegistry
        The hook registry dictionary to update.
    event : str
        The event name to subscribe to.
    callback : Callable[..., Any]
        The callable to invoke when the event is triggered.

    Returns
    -------
    HookRegistry
        The updated hook registry.
    """
    if event not in registry:
        registry[event] = []
    registry[event].append(callback)
    return registry


def trigger_hook(
    registry: HookRegistry | None,
    event: str,
    *args: Any,
    **kwargs: Any,
) -> list[Any]:
    """Trigger all registered callbacks for a given event.

    Parameters
    ----------
    registry : HookRegistry or None
        The hook registry to trigger callbacks from, or None.
    event : str
        The name of the event being triggered.
    *args : Any
        Positional arguments forwarded to each callback.
    **kwargs : Any
        Keyword arguments forwarded to each callback.

    Returns
    -------
    list of Any
        List of return values from each executed callback.
    """
    if not registry:
        return []

    results: list[Any] = []
    callbacks = registry.get(event, [])
    for cb in callbacks:
        try:
            results.append(cb(*args, **kwargs))
        except Exception:
            logging.getLogger("gram2email.hooks").exception(
                "Error executing hook callback '%s' for event '%s'",
                getattr(cb, "__name__", str(cb)),
                event,
            )
    return results


def create_logging_hooks(logger: logging.Logger) -> HookRegistry:
    """Create a default set of logging hooks.

    Parameters
    ----------
    logger : logging.Logger
        Logger instance to receive log messages.

    Returns
    -------
    HookRegistry
        Hook registry populated with standard loggers.
    """
    registry = create_hook_registry()

    def log_account_start(account: str) -> None:
        logger.info("Scanning account: @%s", account)

    def log_post_discovered(account: str, post: Any) -> None:
        logger.info(
            "Found new post for @%s [shortcode=%s, date=%s]",
            account,
            getattr(post, "shortcode", ""),
            getattr(post, "date_utc", ""),
        )

    def log_before_send(message: Any, post: Any) -> None:
        logger.debug(
            "Preparing email for post %s to %s",
            getattr(post, "shortcode", ""),
            message.get("To"),
        )

    def log_after_send(post: Any, success: bool) -> None:
        if success:
            logger.info("Successfully emailed post %s", getattr(post, "shortcode", ""))
        else:
            logger.error("Failed to email post %s", getattr(post, "shortcode", ""))

    def log_account_end(account: str, sent_count: int) -> None:
        logger.info("Finished @%s: %d new post(s) emailed", account, sent_count)

    def log_error(context: str, exc: Exception) -> None:
        logger.error("Error during %s: %s", context, exc)

    register_hook(registry, ON_ACCOUNT_START, log_account_start)
    register_hook(registry, ON_POST_DISCOVERED, log_post_discovered)
    register_hook(registry, BEFORE_SEND, log_before_send)
    register_hook(registry, AFTER_SEND, log_after_send)
    register_hook(registry, ON_ACCOUNT_END, log_account_end)
    register_hook(registry, ON_ERROR, log_error)

    return registry
