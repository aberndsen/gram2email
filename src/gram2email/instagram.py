"""Instagram scraping components and data models.

Provides functional interfaces for querying public Instagram profiles,
extracting post details and media, and downloading images for email inclusion.
"""

import logging
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import instaloader
import requests

logger = logging.getLogger(__name__)


@dataclass
class MediaItem:
    """Represents a single media asset associated with an Instagram post.

    Parameters
    ----------
    url : str
        URL of the media asset.
    media_type : str
        Type of the media ("image" or "video").
    content : bytes or None, default None
        Raw byte payload of the downloaded media file.
    filename : str or None, default None
        Filename associated with the media asset.
    content_type : str, default "image/jpeg"
        MIME type of the media asset.
    cid : str, default ""
        Unique Content-ID string used for inline email embedding.
    """

    url: str
    media_type: str = "image"
    content: bytes | None = None
    filename: str | None = None
    content_type: str = "image/jpeg"
    cid: str = ""


@dataclass
class InstagramPost:
    """Normalized data representation of an Instagram post.

    Parameters
    ----------
    shortcode : str
        Unique shortcode identifying the post.
    url : str
        Full web URL to the post.
    owner_username : str
        Instagram username of the author.
    caption : str
        Text caption accompanying the post.
    date_utc : datetime
        UTC timestamp of post publication.
    media_items : list of MediaItem, default empty list
        Collection of images and video thumbnails for the post.
    is_video : bool, default False
        Whether the post is or contains a primary video.
    likes : int, default 0
        Number of likes recorded on the post.
    comments : int, default 0
        Number of comments recorded on the post.
    """

    shortcode: str
    url: str
    owner_username: str
    caption: str
    date_utc: datetime
    media_items: list[MediaItem] = field(default_factory=list)
    is_video: bool = False
    likes: int = 0
    comments: int = 0


def create_loader(
    user_agent: str | None = None,
    max_connection_attempts: int = 1,
    request_timeout: float = 30.0,
    session_file: str | None = None,
) -> instaloader.Instaloader:
    """Create and configure an Instaloader instance for anonymous scraping.

    Parameters
    ----------
    user_agent : str or None, default None
        Custom HTTP User-Agent string. If None, instaloader defaults are used.
    max_connection_attempts : int, default 1
        Maximum retry attempts for requests.
    request_timeout : float, default 30.0
        Request timeout in seconds.
    session_file : str or None, default None
        Optional path to an existing Instaloader session file.

    Returns
    -------
    instaloader.Instaloader
        Configured Instaloader instance with anonymous read settings.
    """
    from pathlib import Path

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=max_connection_attempts,
        request_timeout=request_timeout,
        fatal_status_codes=[429, 401],
        sleep=False,
        user_agent=user_agent,
    )
    if session_file:
        session_path = Path(session_file).expanduser().resolve()
        if session_path.exists():
            loader.load_session_from_file(session_path.stem, filename=str(session_path))
            logger.debug("Loaded Instagram session from %s", session_path)
        else:
            logger.warning("Session file does not exist: %s", session_path)
    return loader


def download_media_content(
    url: str,
    session: requests.Session | None = None,
    timeout: int = 20,
) -> tuple[bytes | None, str]:
    """Download binary content of a media URL.

    Parameters
    ----------
    url : str
        Web URL pointing to an image or media asset.
    session : requests.Session or None, default None
        HTTP session to use for downloading. If None, requests.get is used.
    timeout : int, default 20
        Request timeout in seconds.

    Returns
    -------
    tuple of (bytes or None, str)
        Downloaded bytes (or None on failure) and the detected MIME content type.
    """
    try:
        req = session.get if session else requests.get
        response = req(url, timeout=timeout)
        response.raise_for_status()
        content = response.content

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        if not content_type or content_type == "application/octet-stream":
            guess, _ = mimetypes.guess_type(url)
            content_type = guess or "image/jpeg"

        return content, content_type
    except Exception as exc:
        logger.warning("Failed to download media from %s: %s", url, exc)
        return None, "image/jpeg"


def extract_media_items(
    post: Any,
    session: requests.Session | None = None,
    download: bool = True,
) -> list[MediaItem]:
    """Extract media assets from an Instaloader Post object.

    Handles single images, carousel/sidecar posts, and video thumbnails.

    Parameters
    ----------
    post : instaloader.Post
        Instaloader post object.
    session : requests.Session or None, default None
        Session used to download binary assets.
    download : bool, default True
        Whether to download the binary media content into memory.

    Returns
    -------
    list of MediaItem
        Extracted media items with URLs, metadata, and optional bytes.
    """
    items: list[MediaItem] = []
    shortcode = getattr(post, "shortcode", "post")

    # Check for carousel / sidecar nodes
    typename = getattr(post, "typename", "")
    if typename == "GraphSidecar":
        try:
            for idx, node in enumerate(post.get_sidecar_nodes()):
                display_url = getattr(node, "display_url", None)
                if not display_url:
                    continue
                is_node_video = getattr(node, "is_video", False)
                cid = f"{shortcode}_img_{idx}"
                filename = f"{shortcode}_{idx}.jpg"
                content = None
                content_type = "image/jpeg"

                if download:
                    content, content_type = download_media_content(display_url, session=session)

                items.append(
                    MediaItem(
                        url=display_url,
                        media_type="video" if is_node_video else "image",
                        content=content,
                        filename=filename,
                        content_type=content_type,
                        cid=cid,
                    )
                )
        except Exception as exc:
            logger.warning(
                "Failed to parse sidecar nodes for post %s: %s",
                shortcode,
                exc,
            )

    # Fallback to single primary image/thumbnail if sidecar extraction didn't yield items
    if not items:
        primary_url = getattr(post, "url", None)
        if primary_url:
            cid = f"{shortcode}_img_0"
            filename = f"{shortcode}_0.jpg"
            content = None
            content_type = "image/jpeg"

            if download:
                content, content_type = download_media_content(primary_url, session=session)

            items.append(
                MediaItem(
                    url=primary_url,
                    media_type="video" if getattr(post, "is_video", False) else "image",
                    content=content,
                    filename=filename,
                    content_type=content_type,
                    cid=cid,
                )
            )

    return items


def fetch_recent_posts(
    account: str,
    max_posts: int = 5,
    loader: instaloader.Instaloader | None = None,
    download_media: bool = True,
) -> list[InstagramPost]:
    """Fetch the most recent posts from a public Instagram account.

    Parameters
    ----------
    account : str
        Public Instagram handle / username without leading '@'.
    max_posts : int, default 5
        Maximum number of recent posts to retrieve.
    loader : instaloader.Instaloader or None, default None
        Instaloader instance to use. If None, a new anonymous loader is created.
    download_media : bool, default True
        Whether to download image assets into memory.

    Returns
    -------
    list of InstagramPost
        Normalized post objects ordered from newest to oldest.

    Raises
    ------
    ValueError
        If the profile does not exist or is private.
    """
    clean_account = account.lstrip("@").strip()
    inst = loader or create_loader()

    logger.debug("Querying profile for @%s", clean_account)
    try:
        profile = instaloader.Profile.from_username(inst.context, clean_account)
    except instaloader.ProfileNotExistsException as exc:
        raise ValueError(f"Instagram account @{clean_account} does not exist.") from exc
    except instaloader.LoginRequiredException as exc:
        raise ValueError(
            f"Instagram account @{clean_account} requires login to view "
            "(profile may be private or rate-limited)."
        ) from exc
    except Exception as exc:
        logger.error("Failed to load profile @%s: %s", clean_account, exc)
        raise

    if profile.is_private:
        raise ValueError(f"Instagram account @{clean_account} is private. Cannot fetch posts anonymously.")

    posts: list[InstagramPost] = []
    session = getattr(inst.context, "_session", None)

    try:
        for idx, post in enumerate(profile.get_posts()):
            if idx >= max_posts:
                break

            shortcode = post.shortcode
            caption = post.caption or ""
            date_utc = post.date_utc
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            is_video = post.is_video

            media_items = extract_media_items(post, session=session, download=download_media)

            posts.append(
                InstagramPost(
                    shortcode=shortcode,
                    url=post_url,
                    owner_username=clean_account,
                    caption=caption,
                    date_utc=date_utc,
                    media_items=media_items,
                    is_video=is_video,
                    likes=post.likes,
                    comments=post.comments,
                )
            )
    except Exception as exc:
        logger.warning(
            "Encountered error while iterating posts for @%s: %s",
            clean_account,
            exc,
        )

    return posts
