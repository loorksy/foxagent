"""Sandboxed executor for operator-written Python strategy code.

Security model (agreed mitigation of the old "never eval" rule): user code is
NEVER eval'd or exec'd inside the server process. It only runs inside a
short-lived ``python -I`` (isolated mode) subprocess with:

- ``resource.setrlimit`` caps on CPU time (~10s) and address space (~512MB),
- a builtins whitelist (no ``open``, ``eval``, ``exec``, ``compile``, ...),
- ``__import__`` replaced by an allowlist (math, statistics, json only),
- dangerous modules (os, socket, subprocess, ...) poisoned in ``sys.modules``,
- a hard wall-clock kill from the parent (~20s).

The whole candle series is processed in ONE subprocess call: the wrapper reads
JSON ``{code, candles, params}`` from stdin, calls ``on_bar(ctx)`` for every
bar, and prints a JSON result to stdout. One process per backtest, not per bar.

Contract for user code::

    def on_bar(ctx):
        # ctx.candles: list of dicts (timestamp/open/high/low/close/volume)
        #              up to and including the current bar
        # ctx.i:       current bar index
        # ctx.params:  dict of extra parameters
        return None  # or:
        return {"action": "BUY" | "SELL", "entry": float, "stopLoss": float,
                "tp1": float, "tp2": float | None, "note": str}
"""

from __future__ import annotations

import ast
import json
import signal
import subprocess
import sys
from typing import Any

MAX_CODE_CHARS = 20_000
DEFAULT_CPU_SECONDS = 10
DEFAULT_MEMORY_MB = 512
DEFAULT_WALL_SECONDS = 20

# Runs inside `python -I -c` with JSON {code, candles, params, cpu_seconds,
# memory_mb} on stdin. Prints one JSON object {ok, signals?, error?} to stdout.
_WRAPPER = r"""
import builtins as _builtins
import json as _json
import sys as _sys

_payload = _json.loads(_sys.stdin.read())

try:
    import resource as _resource

    _cpu = int(_payload.get("cpu_seconds") or 10)
    _mem = int(_payload.get("memory_mb") or 512) * 1024 * 1024
    _resource.setrlimit(_resource.RLIMIT_CPU, (_cpu, _cpu + 1))
    try:
        _resource.setrlimit(_resource.RLIMIT_AS, (_mem, _mem))
    except (ValueError, OSError):
        pass
except ImportError:
    pass

def _fail(message):
    _sys.stdout.write(_json.dumps({"ok": False, "error": str(message)[:500]}))
    _sys.stdout.flush()
    raise SystemExit(0)

import math as _math
import statistics as _statistics

_ALLOWED_MODULES = {"math": _math, "statistics": _statistics, "json": _json}

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level == 0 and name in _ALLOWED_MODULES:
        return _ALLOWED_MODULES[name]
    raise ImportError("import of %r is not allowed (allowed: math, statistics, json)" % name)

_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
    "float", "frozenset", "hash", "int", "isinstance", "issubclass", "iter",
    "len", "list", "map", "max", "min", "next", "pow", "range", "repr",
    "reversed", "round", "set", "slice", "sorted", "str", "sum", "tuple",
    "zip", "True", "False", "None", "__build_class__",
    "ArithmeticError", "AttributeError", "BaseException", "Exception",
    "IndexError", "KeyError", "LookupError", "NotImplementedError",
    "OverflowError", "RuntimeError", "StopIteration", "TypeError",
    "ValueError", "ZeroDivisionError",
)
_safe_builtins = {n: getattr(_builtins, n) for n in _SAFE_BUILTIN_NAMES if hasattr(_builtins, n)}
_safe_builtins["__import__"] = _safe_import

for _blocked in (
    "os", "socket", "subprocess", "shutil", "ctypes", "pathlib",
    "multiprocessing", "threading", "importlib", "signal", "http", "urllib",
):
    _sys.modules[_blocked] = None

class _CandleView:
    # Read-only window over the shared candle list: bars [0, n).
    __slots__ = ("_data", "_n")

    def __init__(self, data, n):
        self._data = data
        self._n = n

    def __len__(self):
        return self._n

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            start, stop, step = idx.indices(self._n)
            return self._data[start:stop:step]
        if idx < 0:
            idx += self._n
        if idx < 0 or idx >= self._n:
            raise IndexError("candle index out of range")
        return self._data[idx]

    def __iter__(self):
        for k in range(self._n):
            yield self._data[k]

class _Ctx:
    __slots__ = ("candles", "i", "params")

    def __init__(self, candles, i, params):
        self.candles = candles
        self.i = i
        self.params = params

_code = str(_payload.get("code") or "")
_candles = list(_payload.get("candles") or [])
_params = dict(_payload.get("params") or {})

_globals = {"__builtins__": _safe_builtins, "__name__": "strategy", "math": _math, "statistics": _statistics}
try:
    exec(compile(_code, "<strategy>", "exec"), _globals)
except BaseException as exc:
    _fail("strategy code failed to load: %s: %s" % (type(exc).__name__, exc))

_on_bar = _globals.get("on_bar")
if not callable(_on_bar):
    _fail("strategy code must define a function on_bar(ctx)")

_signals = []
for _i in range(len(_candles)):
    _ctx = _Ctx(_CandleView(_candles, _i + 1), _i, _params)
    try:
        _out = _on_bar(_ctx)
    except BaseException as exc:
        _fail("on_bar raised at bar %d: %s: %s" % (_i, type(exc).__name__, exc))
    if _out is None:
        continue
    if not isinstance(_out, dict):
        _fail("on_bar must return None or a dict (bar %d)" % _i)
    _action = str(_out.get("action") or "").upper()
    if _action not in ("BUY", "SELL"):
        _fail("signal action must be BUY or SELL (bar %d)" % _i)
    try:
        _entry = float(_out["entry"])
        _stop = float(_out["stopLoss"])
        _tp1 = float(_out["tp1"])
        _tp2 = None if _out.get("tp2") is None else float(_out["tp2"])
    except (KeyError, TypeError, ValueError):
        _fail("signal requires numeric entry/stopLoss/tp1 (bar %d)" % _i)
    _signals.append({
        "index": _i,
        "action": _action,
        "entry": _entry,
        "stopLoss": _stop,
        "tp1": _tp1,
        "tp2": _tp2,
        "note": str(_out.get("note") or "")[:200],
    })

_sys.stdout.write(_json.dumps({"ok": True, "signals": _signals}))
_sys.stdout.flush()
"""


def lint_code(code: str) -> dict[str, Any]:
    """Static syntax check only — never executes anything."""
    text = str(code or "")
    if not text.strip():
        return {"ok": False, "error": "code is empty"}
    if len(text) > MAX_CODE_CHARS:
        return {"ok": False, "error": f"code exceeds {MAX_CODE_CHARS} characters"}
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {"ok": False, "error": f"syntax error at line {exc.lineno}: {exc.msg}"}
    has_on_bar = any(isinstance(node, ast.FunctionDef) and node.name == "on_bar" for node in tree.body)
    if not has_on_bar:
        return {"ok": False, "error": "code must define a top-level (non-async) function on_bar(ctx)"}
    return {"ok": True}


def run_code_backtest(
    code: str,
    candles: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    *,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    memory_mb: int = DEFAULT_MEMORY_MB,
    wall_seconds: int = DEFAULT_WALL_SECONDS,
) -> dict[str, Any]:
    """Run ``on_bar`` over the whole series in one isolated subprocess."""
    lint = lint_code(code)
    if not lint.get("ok"):
        return {"ok": False, "signals": [], "error": lint.get("error")}
    payload = {
        "code": code,
        "candles": candles,
        "params": dict(params or {}),
        "cpu_seconds": int(cpu_seconds),
        "memory_mb": int(memory_mb),
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", _WRAPPER],
            input=json.dumps(payload, default=str).encode(),
            capture_output=True,
            timeout=max(1, int(wall_seconds)),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "signals": [], "error": f"wall-clock timeout after {wall_seconds}s — code killed"}
    except OSError as exc:
        return {"ok": False, "signals": [], "error": f"sandbox spawn failed: {exc}"}
    if proc.returncode < 0:
        sig = -proc.returncode
        if sig in (int(signal.SIGXCPU), int(signal.SIGKILL)):
            return {"ok": False, "signals": [], "error": f"CPU/memory limit exceeded — code killed (signal {sig})"}
        return {"ok": False, "signals": [], "error": f"sandbox killed by signal {sig}"}
    try:
        result = json.loads(proc.stdout.decode() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        tail = proc.stderr.decode(errors="replace")[-300:]
        return {"ok": False, "signals": [], "error": f"sandbox produced no result (exit {proc.returncode}): {tail}"}
    if not isinstance(result, dict) or "ok" not in result:
        return {"ok": False, "signals": [], "error": "sandbox produced a malformed result"}
    if not result.get("ok"):
        return {"ok": False, "signals": [], "error": str(result.get("error") or "strategy code failed")}
    return {"ok": True, "signals": list(result.get("signals") or [])}


def run_code_on_window(
    code: str,
    candles: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    *,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    memory_mb: int = DEFAULT_MEMORY_MB,
    wall_seconds: int = DEFAULT_WALL_SECONDS,
) -> dict[str, Any] | None:
    """Live-scan helper: return the signal fired on the LAST bar, or None."""
    if not candles:
        return None
    result = run_code_backtest(
        code,
        candles,
        params,
        cpu_seconds=cpu_seconds,
        memory_mb=memory_mb,
        wall_seconds=wall_seconds,
    )
    if not result.get("ok"):
        return None
    last = len(candles) - 1
    for sig in reversed(result.get("signals") or []):
        if int(sig.get("index", -1)) == last:
            return sig
    return None
