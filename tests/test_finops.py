import pytest
from mailforge.hygiene import MAX_BODY_CHARS, truncate
from mailforge.llm.anthropic_sdk import (
    Usage,
    cost_usd,
    estimate_tokens,
    make_batches,
    parse_json_array,
)


def test_cost_calculation():
    u = Usage(input=1_000_000, output=1_000_000, cache_read=1_000_000, cache_write=1_000_000)
    # in 1.0 + out 5.0 + read 0.1 + write 1.25
    assert cost_usd("claude-haiku-5-5", u) == pytest.approx(7.35)
    assert cost_usd("claude-haiku-5-5", u, {"claude-haiku-5-5": (2.0, 10.0)}) == pytest.approx(14.7)
    assert cost_usd("unknown-model", Usage(input=1_000_000)) == pytest.approx(3.0)  # pessimistic fallback


def test_batches_cap_items_and_tokens():
    entries = [(f"e{i}", None, "x" * 400) for i in range(40)]  # ~101 tokens each
    b = make_batches(entries)
    assert all(len(x) <= 15 for x in b) and sum(map(len, b)) == 40
    b = make_batches(entries, max_tokens=250)
    assert all(len(x) <= 2 for x in b) and sum(map(len, b)) == 40
    assert make_batches([]) == []


def test_worst_case_batch_far_below_100k():
    worst = 15 * estimate_tokens("x" * (MAX_BODY_CHARS + 400))  # body cap + headers
    assert worst < 100_000


def test_truncate():
    assert truncate("abc") == "abc"
    assert truncate("x" * 4000).endswith("[TRUNCATED]")


def test_parse_json_array_tolerates_fences():
    assert parse_json_array('```json\n[{"id":"e1"}]\n```') == [{"id": "e1"}]
    with pytest.raises(ValueError):
        parse_json_array("no json")
