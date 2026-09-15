"""Behavioral smoke tests for the deployable NewsFlow OAuth static site."""

from __future__ import annotations

from pathlib import Path
import unittest


SITE_ROOT = Path(__file__).resolve().parents[1] / "oauth-site"


def served_document(route: str) -> str:
    """Return the static document Cloudflare Pages will serve for a route."""

    relative = route.strip("/")
    target = SITE_ROOT / (relative or "index.html")
    if route.endswith("/") and relative:
        target /= "index.html"
    return target.read_text(encoding="utf-8")


class OAuthSiteTests(unittest.TestCase):
    def test_home_page_explains_local_oauth_and_offers_policy_routes(self) -> None:
        """Missing consent navigation would leave OAuth users without disclosures."""

        page = served_document("/")
        self.assertIn("NewsFlow", page)
        self.assertIn("локальн", page.casefold())
        self.assertIn('href="/privacy/"', page)
        self.assertIn('href="/terms/"', page)

    def test_privacy_page_explains_google_data_and_user_controls(self) -> None:
        """A policy must disclose the APIs, local storage and revocation path."""

        page = served_document("/privacy/")
        for required in (
            "YouTube Data API",
            "YouTube Analytics API",
            "локально на компьютере",
            "Google Аккаунте",
            "mariaplusize22@gmail.com",
            'href="/"',
        ):
            self.assertIn(required, page)

    def test_terms_page_names_operator_responsibility_for_youtube_content(self) -> None:
        """Terms must put channel and content responsibility with the operator."""

        page = served_document("/terms/")
        self.assertIn("ответственность", page.casefold())
        self.assertIn("YouTube", page)
        self.assertIn('href="/"', page)

    def test_all_public_documents_have_titles_styles_and_root_navigation(self) -> None:
        """A missing deploy route would make the OAuth branding links unusable."""

        for route in ("/", "/privacy/", "/terms/", "/404.html"):
            page = served_document(route)
            self.assertIn("<title>", page)
            self.assertIn('href="/assets/site.css"', page)
        self.assertIn('href="/"', served_document("/404.html"))


if __name__ == "__main__":
    unittest.main()
