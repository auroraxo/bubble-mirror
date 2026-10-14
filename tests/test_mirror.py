"""Smoke tests for bubble-mirror (stdlib unittest, no network)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bubble_mirror import (  # noqa: E402
    _PageAssets,
    _local_path,
    _norm,
    _rewrite_html,
    _same_origin,
)


class TestUrlHelpers(unittest.TestCase):
    def test_norm_drops_fragment(self):
        self.assertEqual(_norm("https://a.example/x#y"), "https://a.example/x")

    def test_norm_keeps_query(self):
        self.assertEqual(_norm("https://a.example/x?p=1"), "https://a.example/x?p=1")

    def test_same_origin(self):
        self.assertTrue(_same_origin("https://a.example/1", "https://a.example/2"))
        self.assertFalse(_same_origin("https://b.example/1", "https://a.example/2"))
        self.assertFalse(_same_origin("ftp://a.example/1", "https://a.example/2"))


class TestLocalPath(unittest.TestCase):
    def test_root_page(self):
        p = _local_path("https://host.example/", Path("/out"), is_page=True)
        self.assertEqual(p, Path("/out/host.example/index.html"))

    def test_extensionless_page(self):
        p = _local_path("https://host.example/about", Path("/out"), is_page=True)
        self.assertEqual(p, Path("/out/host.example/about.html"))

    def test_asset_with_query_is_distinct(self):
        a = _local_path("https://cdn.example/x.png?v=1", Path("/out"), is_page=False)
        b = _local_path("https://cdn.example/x.png?v=2", Path("/out"), is_page=False)
        self.assertNotEqual(a, b)

    def test_asset_path_keeps_extension(self):
        p = _local_path("https://cdn.example/a/b.css", Path("/out"), is_page=False)
        self.assertEqual(p, Path("/out/cdn.example/a/b.css"))


class TestPageAssets(unittest.TestCase):
    HTML = """
    <a href="/page-two">two</a>
    <a href="https://other.example/x">ext</a>
    <link rel="stylesheet" href="/style.css">
    <link rel="canonical" href="https://host.example/">
    <script src="/app.js"></script>
    <img src="/pic.png" srcset="/pic.png 1x, /pic@2.png 2x">
    <style>.x { background: url("/bg.png"); }</style>
    """

    def parse(self):
        p = _PageAssets("https://host.example/")
        p.feed(self.HTML)
        return p

    def test_page_links_same_origin_only(self):
        p = self.parse()
        self.assertIn("https://host.example/page-two", p.page_links)
        self.assertNotIn("https://other.example/x", p.page_links)

    def test_assets_collected(self):
        p = self.parse()
        self.assertIn("https://host.example/style.css", p.assets)
        self.assertIn("https://host.example/app.js", p.assets)
        self.assertIn("https://host.example/pic.png", p.assets)
        self.assertIn("https://host.example/pic@2.png", p.assets)  # srcset

    def test_canonical_not_an_asset(self):
        p = self.parse()
        self.assertNotIn("https://host.example/", p.assets)

    def test_style_block_urls(self):
        p = self.parse()
        self.assertIn("https://host.example/bg.png", p.assets)


class TestRewrite(unittest.TestCase):
    def test_rewrite_to_relative(self):
        out = Path("/out")
        page_file = out / "host.example" / "index.html"
        page_map = {"https://host.example/two": out / "host.example" / "two.html"}
        asset_map = {"https://host.example/a.js": out / "host.example" / "a.js"}
        html = '<a href="two">x</a><script src="/a.js"></script>'
        r = _rewrite_html(html, "https://host.example/", page_file, page_map, asset_map)
        self.assertIn('href="two.html"', r)
        self.assertIn('src="a.js"', r)

    def test_unmapped_left_absolute(self):
        page_file = Path("/out/host.example/index.html")
        html = '<a href="https://other.example/x">x</a>'
        r = _rewrite_html(html, "https://host.example/", page_file, {}, {})
        self.assertIn("https://other.example/x", r)

    def test_fragment_preserved(self):
        out = Path("/out")
        page_file = out / "host.example" / "index.html"
        page_map = {"https://host.example/two": out / "host.example" / "two.html"}
        r = _rewrite_html('<a href="/two#sec">x</a>', "https://host.example/", page_file, page_map, {})
        self.assertIn('href="two.html#sec"', r)


if __name__ == "__main__":
    unittest.main()
