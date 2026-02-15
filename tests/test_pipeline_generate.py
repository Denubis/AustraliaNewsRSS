"""Tests for australianewsrss.pipeline.generate module."""

from datetime import UTC, datetime

import feedparser
from lxml import etree

from australianewsrss.models import NormalisedArticle, PublisherConfig
from australianewsrss.pipeline.generate import generate_rss

# ---------------------------------------------------------------------------
# Namespace constants (matching those in generate.py)
# ---------------------------------------------------------------------------
ATOM_NS = "http://www.w3.org/2005/Atom"
MEDIA_NS = "http://search.yahoo.com/mrss/"
DC_NS = "http://purl.org/dc/elements/1.1/"

NSMAP = {
    "atom": ATOM_NS,
    "media": MEDIA_NS,
    "dc": DC_NS,
}

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

SELF_URL = "https://example.com/feeds/abc.xml"

NOW = datetime(2026, 2, 14, 12, 0, 0, tzinfo=UTC)
EARLIER = datetime(2026, 2, 14, 10, 0, 0, tzinfo=UTC)


def _make_publisher() -> PublisherConfig:
    return PublisherConfig(
        slug="abc",
        name="ABC News",
        base_url="https://www.abc.net.au",
        seed_urls=("https://www.abc.net.au/news/feed/rss",),
    )


def _make_article_with_image() -> NormalisedArticle:
    return NormalisedArticle(
        canonical_url="https://www.abc.net.au/news/article-1",
        url="https://www.abc.net.au/news/article-1",
        title="Bushfire Warning Issued",
        description="A bushfire warning has been issued for parts of NSW.",
        published=NOW,
        guid="https://www.abc.net.au/news/article-1",
        author="Jane Reporter",
        categories=("bushfires", "nsw"),
        image_url="https://live-production.wcms.abc-cdn.net.au/img.jpg",
    )


def _make_article_without_image() -> NormalisedArticle:
    return NormalisedArticle(
        canonical_url="https://www.abc.net.au/news/article-2",
        url="https://www.abc.net.au/news/article-2",
        title="Budget Update Released",
        description="The federal budget has been updated.",
        published=EARLIER,
        guid="https://www.abc.net.au/news/article-2",
        author=None,
        categories=("politics",),
        image_url=None,
    )


def _make_article_no_published() -> NormalisedArticle:
    return NormalisedArticle(
        canonical_url="https://www.abc.net.au/news/article-3",
        url="https://www.abc.net.au/news/article-3",
        title="Timeless Article",
        description="An article with no published date.",
        published=None,
        guid="https://www.abc.net.au/news/article-3",
    )


def _generate_and_parse_xml(
    articles: list[NormalisedArticle] | None = None,
) -> etree._Element:
    """Generate RSS and parse with lxml, returning the root element."""
    if articles is None:
        articles = [_make_article_with_image(), _make_article_without_image()]
    publisher = _make_publisher()
    xml_str = generate_rss(articles, publisher, SELF_URL)
    return etree.fromstring(xml_str.encode("utf-8"))


# ---------------------------------------------------------------------------
# AC3.1: feedparser round-trip
# ---------------------------------------------------------------------------


class TestFeedparserRoundTrip:
    """AC3.1: generated RSS parses correctly with feedparser."""

    def test_bozo_is_false(self) -> None:
        publisher = _make_publisher()
        articles = [_make_article_with_image(), _make_article_without_image()]
        xml_str = generate_rss(articles, publisher, SELF_URL)

        d = feedparser.parse(xml_str)

        assert d.bozo is False, f"feedparser bozo: {d.bozo_exception}"

    def test_entries_match_input_articles(self) -> None:
        publisher = _make_publisher()
        articles = [_make_article_with_image(), _make_article_without_image()]
        xml_str = generate_rss(articles, publisher, SELF_URL)

        d = feedparser.parse(xml_str)

        assert len(d.entries) == 2
        titles = {e.title for e in d.entries}
        assert "Bushfire Warning Issued" in titles
        assert "Budget Update Released" in titles
        links = {e.link for e in d.entries}
        assert "https://www.abc.net.au/news/article-1" in links
        assert "https://www.abc.net.au/news/article-2" in links


# ---------------------------------------------------------------------------
# AC3.2: required item elements
# ---------------------------------------------------------------------------


class TestRequiredItemElements:
    """AC3.2: each <item> has required child elements."""

    def test_items_have_required_elements(self) -> None:
        root = _generate_and_parse_xml()
        items = root.findall(".//item")
        assert len(items) == 2

        for item in items:
            guid = item.find("guid")
            assert guid is not None and guid.text
            link = item.find("link")
            assert link is not None and link.text
            title = item.find("title")
            assert title is not None and title.text
            desc = item.find("description")
            assert desc is not None and desc.text

    def test_pubdate_present_when_published(self) -> None:
        root = _generate_and_parse_xml([_make_article_with_image()])
        items = root.findall(".//item")
        assert len(items) == 1
        pub_date = items[0].find("pubDate")
        assert pub_date is not None and pub_date.text

    def test_pubdate_absent_when_no_published(self) -> None:
        root = _generate_and_parse_xml([_make_article_no_published()])
        items = root.findall(".//item")
        assert len(items) == 1
        pub_date = items[0].find("pubDate")
        assert pub_date is None

    def test_guid_is_permalink(self) -> None:
        root = _generate_and_parse_xml()
        items = root.findall(".//item")
        for item in items:
            guid = item.find("guid")
            assert guid is not None
            assert guid.get("isPermaLink") == "true"


# ---------------------------------------------------------------------------
# AC3.3: image triple
# ---------------------------------------------------------------------------


class TestImageTriple:
    """AC3.3: media:content, enclosure, webfeedsFeaturedVisual."""

    def test_image_article_has_media_content(self) -> None:
        root = _generate_and_parse_xml([_make_article_with_image()])
        item = root.findall(".//item")[0]
        media_content = item.find(f"{{{MEDIA_NS}}}content")
        assert media_content is not None
        assert (
            media_content.get("url")
            == "https://live-production.wcms.abc-cdn.net.au/img.jpg"
        )
        assert media_content.get("medium") == "image"

    def test_image_article_has_enclosure(self) -> None:
        root = _generate_and_parse_xml([_make_article_with_image()])
        item = root.findall(".//item")[0]
        enclosure = item.find("enclosure")
        assert enclosure is not None
        assert (
            enclosure.get("url")
            == "https://live-production.wcms.abc-cdn.net.au/img.jpg"
        )
        assert enclosure.get("type") == "image/jpeg"

    def test_image_article_has_webfeeds_visual_in_description(self) -> None:
        root = _generate_and_parse_xml([_make_article_with_image()])
        item = root.findall(".//item")[0]
        desc = item.find("description")
        assert desc is not None
        assert desc.text is not None
        assert "webfeedsFeaturedVisual" in desc.text
        assert "https://live-production.wcms.abc-cdn.net.au/img.jpg" in desc.text

    def test_no_image_article_has_no_media_content(self) -> None:
        root = _generate_and_parse_xml([_make_article_without_image()])
        item = root.findall(".//item")[0]
        media_content = item.find(f"{{{MEDIA_NS}}}content")
        assert media_content is None

    def test_no_image_article_has_no_enclosure(self) -> None:
        root = _generate_and_parse_xml([_make_article_without_image()])
        item = root.findall(".//item")[0]
        enclosure = item.find("enclosure")
        assert enclosure is None

    def test_no_image_article_has_no_webfeeds_visual(self) -> None:
        root = _generate_and_parse_xml([_make_article_without_image()])
        item = root.findall(".//item")[0]
        desc = item.find("description")
        assert desc is not None
        assert desc.text is not None
        assert "webfeedsFeaturedVisual" not in desc.text


# ---------------------------------------------------------------------------
# AC3.4: atom:link self
# ---------------------------------------------------------------------------


class TestAtomLinkSelf:
    """AC3.4: atom:link self-reference in channel."""

    def test_atom_link_exists_with_self_rel(self) -> None:
        root = _generate_and_parse_xml()
        channel = root.find("channel")
        assert channel is not None
        atom_link = channel.find(f"{{{ATOM_NS}}}link")
        assert atom_link is not None
        assert atom_link.get("rel") == "self"
        assert atom_link.get("href") == SELF_URL
        assert atom_link.get("type") == "application/rss+xml"


# ---------------------------------------------------------------------------
# AC3.5: channel metadata
# ---------------------------------------------------------------------------


class TestChannelMetadata:
    """AC3.5: generator, copyright, language in channel."""

    def test_generator_contains_project_name(self) -> None:
        root = _generate_and_parse_xml()
        channel = root.find("channel")
        assert channel is not None
        gen = channel.find("generator")
        assert gen is not None
        assert gen.text is not None
        assert "AustraliaNewsRSS" in gen.text

    def test_copyright_contains_publisher_name(self) -> None:
        root = _generate_and_parse_xml()
        channel = root.find("channel")
        assert channel is not None
        copy_el = channel.find("copyright")
        assert copy_el is not None
        assert copy_el.text is not None
        assert "ABC News" in copy_el.text

    def test_language_is_en_au(self) -> None:
        root = _generate_and_parse_xml()
        channel = root.find("channel")
        assert channel is not None
        lang = channel.find("language")
        assert lang is not None
        assert lang.text == "en-AU"

    def test_channel_title_contains_publisher_name(self) -> None:
        root = _generate_and_parse_xml()
        channel = root.find("channel")
        assert channel is not None
        title = channel.find("title")
        assert title is not None
        assert title.text is not None
        assert "ABC News" in title.text

    def test_channel_link_is_base_url(self) -> None:
        root = _generate_and_parse_xml()
        channel = root.find("channel")
        assert channel is not None
        link = channel.find("link")
        assert link is not None
        assert link.text == "https://www.abc.net.au"

    def test_dc_creator_present_when_author(self) -> None:
        root = _generate_and_parse_xml([_make_article_with_image()])
        item = root.findall(".//item")[0]
        creator = item.find(f"{{{DC_NS}}}creator")
        assert creator is not None
        assert creator.text == "Jane Reporter"

    def test_dc_creator_absent_when_no_author(self) -> None:
        root = _generate_and_parse_xml([_make_article_without_image()])
        item = root.findall(".//item")[0]
        creator = item.find(f"{{{DC_NS}}}creator")
        assert creator is None

    def test_categories_rendered(self) -> None:
        root = _generate_and_parse_xml([_make_article_with_image()])
        item = root.findall(".//item")[0]
        cats = item.findall("category")
        cat_texts = {c.text for c in cats}
        assert cat_texts == {"bushfires", "nsw"}
