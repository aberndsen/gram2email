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


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_IG_APP_ID = "936619743392459"


def parse_cookie_string(cookie_input: str) -> dict[str, str]:
    """Parse cookie string or raw sessionid into a dictionary of cookie key-values.

    Parameters
    ----------
    cookie_input : str
        Cookie string (e.g., 'sessionid=xxx; ds_user_id=yyy') or standalone sessionid.

    Returns
    -------
    dict of str to str
        Parsed cookies dictionary.
    """
    clean = cookie_input.strip()
    cookies: dict[str, str] = {}
    if "=" in clean:
        for part in clean.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k.strip()] = v.strip().strip('"').strip("'")
    elif clean:
        cookies["sessionid"] = clean
    return cookies


def create_loader(
    user_agent: str | None = None,
    max_connection_attempts: int = 1,
    request_timeout: float = 30.0,
    session_file: str | None = None,
    session_id: str | None = None,
    username: str | None = None,
    password: str | None = None,
    api_key: str | None = None,
    instagram_user: str | None = None,
    interactive: bool = False,
) -> instaloader.Instaloader:
    """Create and configure an Instaloader instance.

    Parameters
    ----------
    user_agent : str or None, default None
        Custom HTTP User-Agent string. If None, a modern browser user-agent is used.
    max_connection_attempts : int, default 1
        Maximum retry attempts for requests.
    request_timeout : float, default 30.0
        Request timeout in seconds.
    session_file : str or None, default None
        Optional path to an existing Instaloader session file or cookie JSON file.
    session_id : str or None, default None
        Optional Instagram session ID cookie or full cookie header string.
    username : str or None, default None
        Instagram account username for direct login or session identification.
    password : str or None, default None
        Instagram account password for login.
    api_key : str or None, default None
        Optional third-party or developer API key.
    instagram_user : str or None, default None
        Optional Instagram username alias (shortcut for username).
    interactive : bool, default False
        Whether to prompt interactively for 2FA codes if required.

    Returns
    -------
    instaloader.Instaloader
        Configured Instaloader instance.
    """
    from pathlib import Path

    effective_ua = user_agent or DEFAULT_USER_AGENT
    effective_user = username or instagram_user

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
        user_agent=effective_ua,
    )

    # Ensure Instagram Web App ID is present for API queries
    loader.context._session.headers["x-ig-app-id"] = DEFAULT_IG_APP_ID

    if api_key and api_key.strip():
        loader.context._session.headers["Authorization"] = f"Bearer {api_key.strip()}"
        loader.context._session.headers["X-API-Key"] = api_key.strip()

    # 1. Apply session_id if provided directly
    if session_id and session_id.strip():
        cookies = parse_cookie_string(session_id)
        loader.context._session.cookies.update(cookies)
        if "csrftoken" in cookies:
            loader.context._session.headers["X-CSRFToken"] = cookies["csrftoken"]
        loader.context.username = effective_user or "authenticated_user"
        logger.debug("Configured Instagram session from session_id cookie")

    # 2. Apply session_file if provided
    if session_file:
        session_path = Path(session_file).expanduser().resolve()
        if session_path.is_file():
            try:
                content = session_path.read_text(encoding="utf-8").strip()
                if content.startswith("{"):
                    import json

                    cookie_data = json.loads(content)
                    if isinstance(cookie_data, dict):
                        loader.context._session.cookies.update(cookie_data)
                        if "csrftoken" in cookie_data:
                            loader.context._session.headers["X-CSRFToken"] = cookie_data["csrftoken"]
                        loader.context.username = effective_user or "authenticated_user"
                        logger.debug("Loaded JSON session cookies from %s", session_path)
                elif "=" in content:
                    cookie_data = parse_cookie_string(content)
                    loader.context._session.cookies.update(cookie_data)
                    loader.context.username = effective_user or "authenticated_user"
                    logger.debug("Loaded text session cookies from %s", session_path)
                else:
                    uname = effective_user or (
                        session_path.name.removeprefix("session-")
                        if session_path.name.startswith("session-")
                        else session_path.stem
                    )
                    loader.load_session_from_file(uname, filename=str(session_path))
                    logger.debug("Loaded Instaloader pickle session from %s", session_path)
            except Exception:
                try:
                    uname = effective_user or (
                        session_path.name.removeprefix("session-")
                        if session_path.name.startswith("session-")
                        else session_path.stem
                    )
                    loader.load_session_from_file(uname, filename=str(session_path))
                    logger.debug("Loaded Instaloader pickle session from %s", session_path)
                except Exception as exc:
                    logger.warning("Failed to load session file %s: %s", session_path, exc)
        else:
            logger.warning("Session file does not exist: %s", session_path)

    # 3. Direct login with username & password if not already authenticated
    if not loader.context.is_logged_in and effective_user and password:
        target_path = (
            Path(session_file).expanduser().resolve()
            if session_file
            else Path(instaloader.instaloader.get_default_session_filename(effective_user))
        )
        if target_path.is_file():
            try:
                loader.load_session_from_file(effective_user, filename=str(target_path))
                logger.debug("Loaded existing cached session from %s", target_path)
            except Exception as exc:
                logger.warning("Cached session %s failed to load (%s); logging in...", target_path, exc)

        if not loader.context.is_logged_in:
            try:
                logger.info("Logging into Instagram as @%s", effective_user)
                loader.login(effective_user, password)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                loader.save_session_to_file(str(target_path))
                logger.info("Successfully logged in and saved session to %s", target_path)
            except instaloader.TwoFactorAuthRequiredException as exc:
                if interactive:
                    code = input(f"Enter Instagram 2FA security code for @{effective_user}: ").strip()
                    loader.two_factor_login(code)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    loader.save_session_to_file(str(target_path))
                    logger.info("Successfully completed 2FA login and saved session to %s", target_path)
                else:
                    raise RuntimeError(
                        f"Instagram 2FA is required for account @{effective_user}. "
                        "Run `gram2email --login` interactively once to authenticate."
                    ) from exc
            except instaloader.BadCredentialsException as exc:
                raise ValueError(f"Invalid Instagram credentials for @{effective_user}.") from exc
            except Exception as exc:
                logger.error("Instagram login failed for @{effective_user}: %s", exc)
                raise

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
        if "429" in str(exc) and not inst.context.is_logged_in:
            logger.error(
                "Instagram blocked unauthenticated access to @%s with HTTP 429 Too Many Requests. "
                "Meta requires an authenticated session to view profile posts. "
                "Please configure 'session_id' or 'session_file' in settings.",
                clean_account,
            )
            raise ValueError(
                f"Instagram blocked anonymous access to @{clean_account} (HTTP 429). "
                "Configure an Instagram session ('session_id' or 'session_file') in settings."
            ) from exc
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
