from urlextract import URLExtract
from bs4 import BeautifulSoup
import requests
import structlog
import discord
from linkpreview import LinkPreview, Link, LinkGrabber
from services.discord.chat.llm import MediaContent

logger = structlog.get_logger(__name__)
extractor = URLExtract()
grabber = LinkGrabber(
    initial_timeout=20,
    maxsize=1048576,
    receive_timeout=10,
    chunk_size=1024,
)


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    # Remove extra whitespace and normalize spaces
    return " ".join(text.split())


def fetch_url(url: str, max_length: int = 1000) -> str:
    """Retrieve and process the content of a URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text(separator=" ", strip=True)[:max_length]
    except Exception as e:
        logger.exception("Error fetching URL", exc_info=e)
        return ""


def fetch_preview_image(url: str) -> MediaContent | None:
    content, url = grabber.get_content(url, headers="chrome")
    link = Link(url, content)
    preview = LinkPreview(link)
    if not preview.absolute_image:
        return None
    logger.info(
        f"Preview image found for URL: {url} Absolute Image: {preview.absolute_image}"
    )
    return MediaContent(
        url=str(preview.absolute_image),
        mime_type="image/png",
    )


def url_context(message_content: str) -> tuple[str, list[MediaContent]]:
    """Extract URLs and retrieve their content."""
    urls = extractor.find_urls(message_content)
    if not urls:
        return ""
    context: list[str] = []
    attachments: list[MediaContent] = []
    for url in urls:
        context.append(f"URL: {url} Content: {fetch_url(url, 2500)}")
        if attachment := fetch_preview_image(url):
            attachments.append(attachment)
    return (
        "Extracted information from URLs in message:\n" + "\n".join(context),
        # attachments,
        [],
    )
