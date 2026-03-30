"""Tests for image module."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.images import get_theme_keywords, get_image_urls, build_images_prompt_section


class TestKeywords:
    def test_coffee(self):
        keywords = get_theme_keywords("Лендинг для кофейни")
        assert "coffee" in keywords

    def test_church(self):
        keywords = get_theme_keywords("Сайт для веры и молитвы")
        assert "church" in keywords

    def test_tech(self):
        keywords = get_theme_keywords("Landing для IT стартапа")
        assert "technology" in keywords

    def test_default(self):
        keywords = get_theme_keywords("Something random")
        assert "business" in keywords


class TestImageUrls:
    def test_returns_correct_count(self):
        urls = get_image_urls("кофейня", count=3)
        assert len(urls) == 3

    def test_urls_are_loremflickr(self):
        urls = get_image_urls("кофейня")
        for url in urls:
            assert "loremflickr.com" in url

    def test_urls_are_unique(self):
        urls = get_image_urls("кофейня", count=5)
        # Lock parameter should make them unique
        assert len(set(urls)) == len(urls)

    def test_different_sizes(self):
        urls = get_image_urls("кофейня", count=5)
        sizes = set()
        for url in urls:
            parts = url.split("/")
            if len(parts) >= 5:
                sizes.add(f"{parts[3]}x{parts[4]}")
        assert len(sizes) > 1


class TestBuildPromptSection:
    def test_returns_string(self):
        result = build_images_prompt_section("кофейня")
        assert isinstance(result, str)

    def test_contains_urls(self):
        result = build_images_prompt_section("кофейня")
        assert "loremflickr.com" in result

    def test_contains_dashes(self):
        result = build_images_prompt_section("кофейня")
        assert "- " in result
