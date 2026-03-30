"""GitHub Pages publishing module."""
import io
import logging
import zipfile

from github import Github, GithubException

from modules.config import GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, PAGES_BASE_URL

logger = logging.getLogger(__name__)


def publish_to_github(html: str, filename: str) -> str:
    """Push HTML to GitHub Pages. Returns public URL."""
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)
    path = f"designs/{filename}.html"

    try:
        contents = repo.get_contents(path, ref=GITHUB_BRANCH)
        repo.update_file(path, f"Update: {filename}", html, contents.sha, branch=GITHUB_BRANCH)
    except GithubException:
        repo.create_file(path, f"Add: {filename}", html, branch=GITHUB_BRANCH)

    return f"{PAGES_BASE_URL}/designs/{filename}.html"


def fetch_from_github(filename: str) -> str | None:
    """Fetch HTML from GitHub Pages."""
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        file = repo.get_contents(f"designs/{filename}.html", ref=GITHUB_BRANCH)
        return file.decoded_content.decode()
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        return None


def create_zip(html: str, filename: str) -> bytes:
    """Create a ZIP with HTML."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{filename}/index.html", html)
    return buf.getvalue()
