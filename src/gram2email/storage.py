"""State storage and persistence for tracking processed Instagram posts.

Provides functional interfaces for loading and saving seen post shortcodes
to prevent duplicate email deliveries across scheduled cron runs.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_seen_posts(path: Path | str) -> set[str]:
    """Load the set of previously seen post shortcodes from a JSON file.

    Parameters
    ----------
    path : Path or str
        Path to the JSON state persistence file.

    Returns
    -------
    set of str
        Set of post shortcodes that have already been processed.
        Returns an empty set if the file does not exist or cannot be parsed.

    Notes
    -----
    The storage format is a JSON object with a ``"seen_posts"`` array or
    a top-level list of shortcode strings.
    """
    state_file = Path(path)
    if not state_file.exists():
        logger.debug("State file %s does not exist; starting with empty set", state_file)
        return set()

    try:
        content = state_file.read_text(encoding="utf-8").strip()
        if not content:
            return set()
        data = json.loads(content)
        if isinstance(data, list):
            return set(data)
        if isinstance(data, dict) and "seen_posts" in data:
            return set(data["seen_posts"])
        logger.warning(
            "State file %s has unrecognized format; returning empty set",
            state_file,
        )
        return set()
    except Exception as exc:
        logger.warning(
            "Failed to load state file %s: %s; starting with empty set",
            state_file,
            exc,
        )
        return set()


def save_seen_posts(path: Path | str, seen_shortcodes: set[str]) -> None:
    """Save the set of seen post shortcodes to a JSON file.

    Parameters
    ----------
    path : Path or str
        Destination path for the state persistence file.
    seen_shortcodes : set of str
        Set of post shortcodes to persist.

    Notes
    -----
    Creates parent directories if they do not exist. Writes atomically
    by writing to a temporary file then renaming.
    """
    state_file = Path(path)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "seen_posts": sorted(seen_shortcodes),
        "count": len(seen_shortcodes),
    }

    temp_file = state_file.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_file.replace(state_file)
    logger.debug("Saved %d seen posts to %s", len(seen_shortcodes), state_file)


def is_post_seen(seen_shortcodes: set[str], shortcode: str) -> bool:
    """Check if a post shortcode has already been processed.

    Parameters
    ----------
    seen_shortcodes : set of str
        Set of known shortcodes.
    shortcode : str
        Shortcode identifier to verify.

    Returns
    -------
    bool
        True if the shortcode is in the set, False otherwise.
    """
    return shortcode in seen_shortcodes


def mark_post_seen(seen_shortcodes: set[str], shortcode: str) -> set[str]:
    """Return a new set containing the updated shortcodes including the new one.

    Parameters
    ----------
    seen_shortcodes : set of str
        Existing set of known shortcodes.
    shortcode : str
        Shortcode identifier to add.

    Returns
    -------
    set of str
        New set with the shortcode included.
    """
    return seen_shortcodes | {shortcode}
