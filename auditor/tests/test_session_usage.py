import json
from pathlib import Path

from scripts.session_usage import compare, measure


def _assistant(msg_id: str, ts: str, **usage) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": ts,
            "effort": "medium",
            "message": {"id": msg_id, "model": "claude-opus-5-5", "usage": usage},
        }
    )


def test_measure_claude_code_dedupes_message_ids_and_includes_subagents(tmp_path: Path) -> None:
    usage = {
        "input_tokens": 10,
        "cache_read_input_tokens": 900,
        "cache_creation_input_tokens": 90,
        "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 90},
        "output_tokens": 50,
    }
    session = tmp_path / "abc.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-09-22T10:00:00Z",
                        "message": {"content": "go"},
                    }
                ),
                # Same message logged twice (one line per content block) → counted once.
                _assistant("m1", "2026-09-22T10:00:10Z", **usage),
                _assistant("m1", "2026-09-22T10:00:10Z", **usage),
                _assistant("m2", "2026-09-22T10:10:00Z", **usage),
            ]
        ),
        encoding="utf-8",
    )
    sub = tmp_path / "abc" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-1.jsonl").write_text(_assistant("s1", "2026-09-22T10:05:00Z", **usage))

    measured = measure(session)

    assert measured["format"] == "claude-code"
    assert measured["api_calls"] == 3
    assert measured["user_prompts"] == 1
    assert measured["total_input_tokens"] == 3 * 1000  # input + cache read + cache write
    assert measured["total_cached_input_tokens"] == 3 * 900
    assert measured["total_output_tokens"] == 150
    assert measured["efforts"] == ["medium"]
    assert measured["wall_time_seconds"] == 600

    trace = tmp_path / "audit_trace.json"
    trace.write_text(
        json.dumps(
            {
                "meta": {"model": "claude-opus-5-5", "effort": "high"},
                "summary": {"total_input_tokens": 1500, "total_output_tokens": 150},
            }
        ),
        encoding="utf-8",
    )
    comparison = compare(measured, trace)
    assert comparison["fields"]["total_input_tokens"]["delta_pct"] == -50.0
    assert comparison["declared_effort"] == "high"
