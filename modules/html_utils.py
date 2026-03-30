"""HTML utilities: validation, fixing, watermark, extraction."""
import re
from html.parser import HTMLParser
from modules.config import WATERMARK_TEXT, WATERMARK_URL


class HTMLValidator(HTMLParser):
    """Basic HTML structure validator."""
    def __init__(self):
        super().__init__()
        self.has_doctype = False
        self.has_html = False
        self.has_head = False
        self.has_body = False
        self.has_title = False
        self.has_viewport = False
        self.errors: list[str] = []

    def handle_decl(self, decl):
        if "DOCTYPE" in decl.upper():
            self.has_doctype = True

    def handle_starttag(self, tag, attrs):
        if tag == "html": self.has_html = True
        elif tag == "head": self.has_head = True
        elif tag == "body": self.has_body = True
        elif tag == "title": self.has_title = True
        elif tag == "meta":
            for name, value in attrs:
                if name == "name" and value == "viewport":
                    self.has_viewport = True

    def validate(self, html: str) -> list[str]:
        self.errors = []
        self.feed(html)
        if not self.has_doctype: self.errors.append("Missing DOCTYPE")
        if not self.has_html: self.errors.append("Missing <html>")
        if not self.has_head: self.errors.append("Missing <head>")
        if not self.has_body: self.errors.append("Missing <body>")
        if not self.has_title: self.errors.append("Missing <title>")
        if not self.has_viewport: self.errors.append("Missing viewport")
        return self.errors


def extract_html(text: str) -> str:
    """Extract HTML from AI response."""
    if not isinstance(text, str):
        text = str(text)
    match = re.search(r'```(?:html)?\s*\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if text.strip().startswith(('<!DOCTYPE', '<html')):
        return text.strip()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Design</title>
</head>
<body>
{text.strip()}
</body>
</html>"""


def fix_html_issues(html: str) -> str:
    """Auto-fix common HTML issues."""
    if 'viewport' not in html:
        html = html.replace('<head>', '<head>\n<meta name="viewport" content="width=device-width, initial-scale=1.0">', 1)
    if 'charset' not in html:
        html = html.replace('<head>', '<head>\n<meta charset="UTF-8">', 1)
    html = re.sub(r'<img(?![^>]*alt=)([^>]*)>', r'<img\1 alt="Image">', html)
    # Fix mobile overflow
    if 'overflow-x' not in html:
        if '<style>' in html:
            html = html.replace('<style>', '<style>\nhtml, body { overflow-x: hidden; max-width: 100vw; }')
        elif '</head>' in html:
            html = html.replace('</head>', '<style>html, body { overflow-x: hidden; max-width: 100vw; }</style>\n</head>')
    return html


def add_watermark(html: str) -> str:
    """Add small watermark to bottom of page."""
    watermark = f"""
<div style="position:fixed;bottom:8px;right:12px;font-size:11px;color:rgba(128,128,128,0.5);font-family:sans-serif;z-index:9999;pointer-events:none;">
  Made with <a href="{WATERMARK_URL}" style="color:rgba(128,128,128,0.5);text-decoration:none;">{WATERMARK_TEXT}</a>
</div>"""
    html = html.replace('</body>', watermark + '\n</body>')
    return html


def validate_html(html: str) -> list[str]:
    """Validate HTML and return list of issues."""
    validator = HTMLValidator()
    return validator.validate(html)
