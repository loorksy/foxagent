from __future__ import annotations

import pytest

from app.services.artifacts import (
    ArtifactStreamParser,
    extract_artifacts,
    is_quick_question,
    should_publish_artifact,
    strip_ant_artifacts,
)
from app.services.agent import SYSTEM_PROMPT


PYTHON_BACKTEST = """Here is the script.

<antArtifact identifier="xau-backtest" type="application/vnd.ant.code" language="python" title="XAU backtest">
import pandas as pd

def backtest(df: pd.DataFrame) -> float:
    signal = df["close"].diff() > 0
    ret = df["close"].pct_change().fillna(0)
    equity = (1 + ret.where(signal.shift(1), 0)).cumprod()
    return float(equity.iloc[-1])

if __name__ == "__main__":
    print("ready")
</antArtifact>
"""

RISK_MATRIX = """Risk sheet attached.

<antArtifact identifier="risk-matrix" type="text/csv" title="Risk matrix">
Setup,R,Session,Outcome
XAU NY FVG,1.6,ny,fail
EUR London OB,2.4,london,win
GBP Asia sweep,1.2,asian,expire
</antArtifact>
"""

QUICK_TREND = "XAUUSD is bullish on H4 after the London sweep; wait for a 15m FVG fill."


def test_protocol_is_in_system_prompt():
    assert "<antArtifact" in SYSTEM_PROMPT
    assert "application/vnd.ant.code" in SYSTEM_PROMPT
    assert "Do NOT create an artifact" in SYSTEM_PROMPT


def test_python_backtest_emits_code_artifact():
    arts = extract_artifacts(PYTHON_BACKTEST)
    assert len(arts) == 1
    assert arts[0]["type"] == "application/vnd.ant.code"
    assert arts[0]["language"] == "python"
    assert "def backtest" in arts[0]["body"]
    assert strip_ant_artifacts(PYTHON_BACKTEST) == "Here is the script."


def test_risk_matrix_emits_spreadsheet_artifact():
    arts = extract_artifacts(RISK_MATRIX)
    assert len(arts) == 1
    assert arts[0]["type"] == "text/csv"
    assert "Setup,R,Session,Outcome" in arts[0]["body"]


def test_quick_trend_question_stays_in_chat():
    question = "What is XAUUSD current trend?"
    assert is_quick_question(question)
    assert not should_publish_artifact(question, QUICK_TREND)
    assert extract_artifacts(QUICK_TREND) == []


@pytest.mark.asyncio
async def test_stream_parser_opens_workspace_for_code():
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    parser = ArtifactStreamParser(
        emit,
        session_id=None,
        agent="TechnicalAgent",
        run_id="run_art",
        user_message="Write a Python backtest script for XAU",
    )
    visible = ""
    for chunk in [PYTHON_BACKTEST[i : i + 17] for i in range(0, len(PYTHON_BACKTEST), 17)]:
        visible += await parser.feed(chunk)
    visible += await parser.flush()
    kinds = [n for n, _ in events]
    assert "agent_artifact_start" in kinds
    assert "agent_artifact_delta" in kinds
    assert "agent_artifact_end" in kinds
    start = next(p for n, p in events if n == "agent_artifact_start")
    assert start["type"] == "application/vnd.ant.code"
    assert start["language"] == "python"
    assert "<antArtifact" not in visible
    assert "Here is the script." in visible


@pytest.mark.asyncio
async def test_stream_parser_sheet_and_quick_suppressed():
    events: list[tuple[str, dict]] = []

    async def emit(name: str, payload: dict) -> None:
        events.append((name, payload))

    sheet = ArtifactStreamParser(
        emit, session_id=None, agent="RiskManagerAgent", run_id="r2", user_message="Make a risk matrix sheet"
    )
    await sheet.ingest_complete(RISK_MATRIX)
    assert any(n == "agent_artifact_start" and p["type"] == "text/csv" for n, p in events)

    events.clear()
    tagged_quick = (
        'XAUUSD is bullish.\n<antArtifact identifier="nope" type="text/markdown" title="Nope">\n'
        + "line\n" * 20
        + "</antArtifact>"
    )
    quiet = ArtifactStreamParser(
        emit,
        session_id=None,
        agent="TechnicalAgent",
        run_id="r3",
        user_message="What is XAUUSD current trend?",
    )
    await quiet.ingest_complete(tagged_quick)
    assert events == []
