from app.services.agent import extract_json_object, resolve_model


def test_extract_json_from_fence():
    text = 'Here you go\n```json\n{"tradeSetup": {"action": "BUY"}, "x": 1}\n```\n'
    data = extract_json_object(text)
    assert data is not None
    assert data["tradeSetup"]["action"] == "BUY"


def test_extract_raw_object():
    data = extract_json_object('noise {"tradeSetup": {"action": "SELL"}} trailing')
    assert data["tradeSetup"]["action"] == "SELL"


def test_model_aliases():
    assert resolve_model("sonnet") == "claude-sonnet-4-5"
    assert "haiku" in resolve_model("haiku")
