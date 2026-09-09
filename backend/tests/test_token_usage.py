from app.services.token_usage import TokenSlice, UsageTracker, parse_usage


def test_parse_usage_from_messages_object():
    slice = parse_usage(
        {
            "input_tokens": 1200,
            "output_tokens": 340,
            "cache_creation_input_tokens": 80,
            "cache_read_input_tokens": 400,
        }
    )
    assert slice.input_tokens == 1200
    assert slice.output_tokens == 340
    assert slice.cache_creation_input_tokens == 80
    assert slice.cache_read_input_tokens == 400
    assert slice.total_tokens == 2020


def test_parse_usage_from_stream_delta():
    slice = parse_usage(
        {
            "type": "message_delta",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )
    assert slice.input_tokens == 10
    assert slice.output_tokens == 5


def test_parse_nested_cache_creation():
    slice = parse_usage(
        {
            "uncached_input_tokens": 50,
            "output_tokens": 9,
            "cache_creation": {"ephemeral_5m_input_tokens": 20, "ephemeral_1h_input_tokens": 10},
            "cache_read_input_tokens": 100,
        }
    )
    assert slice.input_tokens == 50
    assert slice.cache_creation_input_tokens == 30
    assert slice.cache_read_input_tokens == 100


def test_tracker_accumulates_calls():
    tracker = UsageTracker(run_id="run_1", model="claude-sonnet-4-5")
    tracker.add(TokenSlice(input_tokens=100, output_tokens=20), model="claude-sonnet-4-5")
    tracker.add(TokenSlice(input_tokens=40, output_tokens=10))
    public = tracker.public()
    assert public["inputTokens"] == 140
    assert public["outputTokens"] == 30
    assert public["calls"] == 2
    assert public["runId"] == "run_1"
    assert public["estimatedUsd"] > 0


def test_empty_usage_ignored():
    tracker = UsageTracker(run_id="run_2")
    tracker.add(TokenSlice())
    assert tracker.calls == 0
    assert tracker.public()["totalTokens"] == 0
