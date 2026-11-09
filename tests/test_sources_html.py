from __future__ import annotations

import unittest
from pathlib import Path

from socratic_learn.errors import SourceError
from socratic_learn.sources.html import extract_html
from socratic_learn.sources.normalize import MIN_NON_WHITESPACE_CODE_POINTS

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"


def _pad(html: str, *, target: str = "article") -> str:
    filler = "<p>" + "content " * 40 + "</p>"
    close_tag = f"</{target}>"
    if close_tag in html:
        return html.replace(close_tag, filler + close_tag, 1)
    return html.replace("</body>", filler + "</body>", 1)


class HtmlPrecedenceTests(unittest.TestCase):
  def test_prefers_article_over_main_and_body(self) -> None:
    html = _pad(
      "<html><body><main><p>MAIN ONLY</p></main>"
      "<article><p>ARTICLE WINS with enough words for extraction.</p></article>"
      "</body></html>"
    )
    document = extract_html(html.encode("utf-8"), content_type="text/html", title_hint="hint")
    self.assertIn("ARTICLE WINS", document.sections[0].text)
    self.assertNotIn("MAIN ONLY", document.sections[0].text)

  def test_falls_back_to_main_when_article_empty(self) -> None:
    html = _pad(
        "<html><body><article></article>"
        "<main><p>MAIN CONTENT wins when article is empty.</p></main></body></html>",
        target="main",
    )
    document = extract_html(html.encode("utf-8"), content_type=None, title_hint="hint")
    self.assertIn("MAIN CONTENT", document.sections[0].text)

  def test_falls_back_to_body_when_article_and_main_empty(self) -> None:
    html = _pad(
        "<html><body><article></article><main></main><p>BODY TEXT remains.</p></body></html>",
        target="body",
    )
    document = extract_html(html.encode("utf-8"), content_type=None, title_hint="hint")
    self.assertIn("BODY TEXT", document.sections[0].text)

  def test_skips_under_two_hundred_article_for_meaningful_main(self) -> None:
    html = _pad(
      "<html><body>"
      "<article><p>Short article note only.</p></article>"
      "<main><p>MAIN PREVAILS when article is below the meaningful threshold.</p></main>"
      "</body></html>",
      target="main",
    )
    document = extract_html(html.encode("utf-8"), content_type="text/html", title_hint="hint")
    self.assertIn("MAIN PREVAILS", document.sections[0].text)
    self.assertNotIn("Short article note", document.sections[0].text)


class HtmlExclusionTests(unittest.TestCase):
  def test_excludes_script_style_nav_and_chrome(self) -> None:
    html = _pad(
      "<html><body><article>"
      "<script>window.secret = 'EXECUTED';</script>"
      "<style>.hidden{display:none}</style>"
      "<nav>skip nav</nav><header>skip header</header>"
      "<p>Visible article text with sufficient length for normalization.</p>"
      "<footer>skip footer</footer>"
      "</article></body></html>"
    )
    document = extract_html(html.encode("utf-8"), content_type="text/html", title_hint="hint")
    text = document.sections[0].text
    self.assertIn("Visible article text", text)
    self.assertNotIn("EXECUTED", text)
    self.assertNotIn("skip nav", text)
    self.assertNotIn("skip header", text)
    self.assertNotIn("skip footer", text)


class HtmlBlockOrderTests(unittest.TestCase):
  def test_preserves_heading_paragraph_blockquote_and_list_order(self) -> None:
    raw = (FIXTURES / "article.html").read_bytes()
    document = extract_html(raw, content_type="text/html", title_hint="ignored if title wins")
    text = document.sections[0].text
    heading = text.index("Evidence Overview")
    paragraph = text.index("deterministic extraction")
    quote = text.index("quoted claim")
    first_item = text.index("First list item")
    second_item = text.index("Second list item")
    self.assertLess(heading, paragraph)
    self.assertLess(paragraph, quote)
    self.assertLess(quote, first_item)
    self.assertLess(first_item, second_item)

  def test_committed_article_fixture_is_meaningful(self) -> None:
    raw = (FIXTURES / "article.html").read_bytes()
    document = extract_html(raw, content_type="text/html", title_hint="hint")
    self.assertEqual("text/html", document.media_type)
    non_ws = sum(1 for ch in document.sections[0].text if not ch.isspace())
    self.assertGreaterEqual(non_ws, MIN_NON_WHITESPACE_CODE_POINTS)


class HtmlCharsetTests(unittest.TestCase):
  def test_uses_http_charset_when_valid(self) -> None:
    html = _pad("<html><body><article><p>Caf\xe9 texto portugu\xeas.</p></article></body></html>")
    document = extract_html(
      html.encode("latin-1"),
      content_type="text/html; charset=iso-8859-1",
      title_hint="hint",
    )
    self.assertIn("Café", document.sections[0].text)

  def test_uses_bom_when_http_charset_missing(self) -> None:
    html = _pad("<html><body><article><p>BOM marker text.</p></article></body></html>")
    document = extract_html(html.encode("utf-8-sig"), content_type="text/html", title_hint="hint")
    self.assertIn("BOM marker", document.sections[0].text)

  def test_uses_meta_charset_in_head_prefix(self) -> None:
    html = _pad(
      '<html><head><meta charset="iso-8859-1"></head>'
      "<body><article><p>Meta charset Caf\xe9.</p></article></body></html>"
    )
    document = extract_html(html.encode("latin-1"), content_type="text/html", title_hint="hint")
    self.assertIn("Café", document.sections[0].text)

  def test_uses_meta_http_equiv_content_type_charset(self) -> None:
    html = _pad(
      '<html><head><meta http-equiv="Content-Type" '
      'content="text/html; charset=iso-8859-1"></head>'
      "<body><article><p>Http-equiv Caf\xe9.</p></article></body></html>"
    )
    document = extract_html(html.encode("latin-1"), content_type="text/html", title_hint="hint")
    self.assertIn("Café", document.sections[0].text)

  def test_invalid_meta_charset_label_falls_back_to_utf8(self) -> None:
    html = _pad(
      '<html><head><meta charset="not-a-real-charset"></head>'
      "<body><article><p>Meta invalid UTF-8 café fallback.</p></article></body></html>"
    )
    document = extract_html(html.encode("utf-8"), content_type="text/html", title_hint="hint")
    self.assertIn("café", document.sections[0].text)

  def test_falls_back_to_utf8_replacement_for_invalid_charset_label(self) -> None:
    html = _pad("<html><body><article><p>Fallback UTF-8 text runs here.</p></article></body></html>")
    document = extract_html(
      html.encode("utf-8"),
      content_type="text/html; charset=not-a-real-charset",
      title_hint="hint",
    )
    self.assertIn("Fallback UTF-8", document.sections[0].text)


class HtmlTitleTests(unittest.TestCase):
  def test_prefers_meaningful_title_element_over_hint(self) -> None:
    html = _pad(
      "<html><head><title>Real HTML Title</title></head>"
      "<body><article><p>Title behavior test content with padding words.</p></article></body></html>"
    )
    document = extract_html(html.encode("utf-8"), content_type="text/html", title_hint="Hint Title")
    self.assertEqual("Real HTML Title", document.title)

  def test_uses_title_hint_when_title_element_is_empty(self) -> None:
    html = _pad(
      "<html><head><title>   </title></head>"
      "<body><article><p>Empty title should defer to the hint string.</p></article></body></html>"
    )
    document = extract_html(html.encode("utf-8"), content_type="text/html", title_hint="Hint From Caller")
    self.assertEqual("Hint From Caller", document.title)

  def test_uses_title_hint_when_title_element_is_too_short(self) -> None:
    html = _pad(
      "<html><head><title>ab</title></head>"
      "<body><article><p>Short title element should not override the hint.</p></article></body></html>"
    )
    document = extract_html(html.encode("utf-8"), content_type="text/html", title_hint="Hint From Caller")
    self.assertEqual("Hint From Caller", document.title)


class HtmlRejectionTests(unittest.TestCase):
  def test_rejects_under_two_hundred_characters_with_actionable_error(self) -> None:
    html = "<html><body><article><p>Too short.</p></article></body></html>"
    with self.assertRaises(SourceError) as context:
      extract_html(html.encode("utf-8"), content_type="text/html", title_hint="short")
    message = str(context.exception).lower()
    self.assertIn("200", message)
    self.assertTrue(
      "javascript" in message or "client" in message or "render" in message,
      message,
    )


if __name__ == "__main__":
  unittest.main()
