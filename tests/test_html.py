"""Tests for HTML utilities."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.html_utils import extract_html, fix_html_issues, add_watermark, validate_html, HTMLValidator


class TestExtractHtml:
    def test_raw_html(self):
        text = "<!DOCTYPE html><html><body>Hello</body></html>"
        result = extract_html(text)
        assert "<!DOCTYPE html>" in result

    def test_markdown_block(self):
        text = 'Some text\n```html\n<!DOCTYPE html><html><body>Hello</body></html>\n```\nMore text'
        result = extract_html(text)
        assert "<!DOCTYPE html>" in result
        assert "```" not in result

    def test_plain_text(self):
        text = "<h1>Hello</h1><p>World</p>"
        result = extract_html(text)
        assert "<!DOCTYPE html>" in result
        assert "<h1>Hello</h1>" in result

    def test_non_string(self):
        result = extract_html(123)
        assert "<!DOCTYPE html>" in result


class TestFixHtml:
    def test_adds_viewport(self):
        html = "<!DOCTYPE html><html><head><title>Test</title></head><body></body></html>"
        result = fix_html_issues(html)
        assert "viewport" in result

    def test_adds_charset(self):
        html = "<!DOCTYPE html><html><head><title>Test</title></head><body></body></html>"
        result = fix_html_issues(html)
        assert "charset" in result

    def test_adds_alt_to_images(self):
        html = '<img src="test.jpg">'
        result = fix_html_issues(html)
        assert 'alt=' in result

    def test_adds_overflow_x(self):
        html = "<!DOCTYPE html><html><head><style>body { color: red; }</style></head><body></body></html>"
        result = fix_html_issues(html)
        assert "overflow-x" in result


class TestWatermark:
    def test_adds_watermark(self):
        html = "<!DOCTYPE html><html><body>Content</body></html>"
        result = add_watermark(html)
        assert "Made with" in result
        assert "LandingAI" in result


class TestValidator:
    def test_valid_html(self):
        html = '<!DOCTYPE html><html><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body></body></html>'
        errors = validate_html(html)
        assert len(errors) == 0

    def test_missing_doctype(self):
        html = '<html><head><title>Test</title><meta name="viewport" content="width=device-width"></head><body></body></html>'
        errors = validate_html(html)
        assert "Missing DOCTYPE" in errors

    def test_missing_viewport(self):
        html = '<!DOCTYPE html><html><head><title>Test</title></head><body></body></html>'
        errors = validate_html(html)
        assert "Missing viewport" in errors
