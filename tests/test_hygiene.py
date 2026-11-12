from datetime import UTC, datetime

from mailforge.config import Settings
from mailforge.hygiene import (
    MAX_BODY_CHARS,
    TRUNC_MARK,
    clean_body,
    filter_reason,
    html_to_text,
    strip_quotes,
)
from mailforge.providers.base import EmailMessage


def msg(**kw):
    d = dict(account_id="a", message_id="1", thread_id="t", sender="Bob <bob@corp.example>",
             subject="Hi", date=datetime.now(UTC), text="hello", html="", headers={})
    d.update(kw)
    return EmailMessage(**d)


S = Settings(ignore_senders=["noreply@*", "*@marketing.*"], vip_domains=["vip.example"])


def test_html_strips_noise():
    h = ("<html><head><title>x</title><style>p{}</style></head><body><script>evil()</script>"
         "<p>Real text</p><img src='http://track/pixel.gif'></body></html>")
    t = html_to_text(h)
    assert "Real text" in t and "evil" not in t and "p{}" not in t and "pixel" not in t


def test_quote_removal():
    body = "Sounds good.\n\nOn Mon, 1 Jan 2026 at 10:00, Alice <a@x.com> wrote:\n> old\n> older\n"
    assert strip_quotes(body).strip() == "Sounds good."
    assert strip_quotes("Yes\n-----Original Message-----\nFrom: x").strip() == "Yes"
    assert strip_quotes("keep\n> quoted\nkeep2") == "keep\nkeep2"


def test_truncation():
    out = clean_body(msg(text="x" * 10_000))
    assert out.endswith(TRUNC_MARK) and len(out) <= MAX_BODY_CHARS + len(TRUNC_MARK) + 1


def test_prefers_plain_over_html():
    assert clean_body(msg(text="plain", html="<p>html</p>")) == "plain"
    assert clean_body(msg(text="", html="<p>html</p>")) == "html"


def test_loop_prevention():
    assert filter_reason(msg(headers={"x-mailforge-report": "true"}), S) == "own-report"
    assert filter_reason(msg(subject="[MailForge] Daily Briefing — 2026-01-01"), S) == "own-report"


def test_noise_headers_and_vip():
    assert filter_reason(msg(headers={"list-unsubscribe": "<x>"}), S) == "list-unsubscribe"
    assert filter_reason(msg(headers={"precedence": "bulk"}), S) == "precedence-bulk"
    assert filter_reason(msg(headers={"auto-submitted": "auto-generated"}), S) == "auto-submitted"
    assert filter_reason(msg(headers={"auto-submitted": "no"}), S) is None
    vip = msg(sender="boss@sub.vip.example", headers={"list-unsubscribe": "<x>"})
    assert filter_reason(vip, S) is None


def test_ignore_senders():
    assert filter_reason(msg(sender="noreply@shop.com"), S) == "ignored-sender"
    assert filter_reason(msg(sender="a@marketing.shop.com"), S) == "ignored-sender"
    assert filter_reason(msg(), S) is None
