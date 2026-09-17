"""Tests for functional lifecycle hooks."""

import logging

from gram2email.hooks import (
    AFTER_SEND,
    ON_ACCOUNT_START,
    ON_POST_DISCOVERED,
    create_hook_registry,
    create_logging_hooks,
    register_hook,
    trigger_hook,
)


def test_create_and_trigger_hooks():
    registry = create_hook_registry()
    calls = []

    def on_start(account: str):
        calls.append(f"start:{account}")

    register_hook(registry, ON_ACCOUNT_START, on_start)
    trigger_hook(registry, ON_ACCOUNT_START, "natgeo")

    assert calls == ["start:natgeo"]


def test_trigger_empty_or_none():
    assert trigger_hook(None, "anything") == []
    registry = create_hook_registry()
    assert trigger_hook(registry, "unregistered_event") == []


def test_hook_exception_isolation():
    registry = create_hook_registry()
    executed = []

    def failing_hook(*args, **kwargs):
        raise RuntimeError("Hook crashed")

    def successful_hook(*args, **kwargs):
        executed.append(True)

    register_hook(registry, ON_POST_DISCOVERED, failing_hook)
    register_hook(registry, ON_POST_DISCOVERED, successful_hook)

    # Should not raise exception, and subsequent hook should still execute
    trigger_hook(registry, ON_POST_DISCOVERED, "account", "post")
    assert executed == [True]


def test_create_logging_hooks():
    logger = logging.getLogger("test_logger")
    registry = create_logging_hooks(logger)
    assert ON_ACCOUNT_START in registry
    assert ON_POST_DISCOVERED in registry
    assert AFTER_SEND in registry
    assert len(registry[ON_ACCOUNT_START]) > 0
