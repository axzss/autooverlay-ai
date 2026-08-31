"""Persistent high-water marks for the kill-switch.

Why this exists: Alpaca exposes ``equity`` and ``last_equity`` — today and
yesterday. Neither is a high-water mark. Every attempt to synthesise a peak from
a single account snapshot has failed the same way:

- ``peak_equity = account["equity"]``           -> peak == equity, drawdown 0.00%
- ``peak_equity = max(equity, last_equity)``    -> a two-day window; a slow bleed
                                                   never registers

A drawdown check needs memory. This module is that memory: the smallest possible
slice of the W1 state ledger, tracking the running maximum of NAV and of overlay
collateral across cycles.

Deliberately JSON, not SQLite. The full ledger (cycle_run, directive,
exit_event) is a larger piece of work; this file exists so the kill-switch stops
being blind in the meantime, and its shape is compatible with being folded into
the SQLite store later.

Storage: ``docs/.cache/peak_equity.json`` (gitignored), atomic write, ``/tmp``
fallback when the repo path is read-only. Every read reports whether the value
was *tracked* or *absent*, because "no high-water mark" must never be presented
as "no drawdown".
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PEAK_PATH = _REPO_ROOT / "docs" / ".cache" / "peak_equity.json"
FALLBACK_PEAK_PATH = Path(tempfile.gettempdir()) / "autooverlay_peak_equity.json"

#: Env override for the store location. Tests set this so a run never inherits a
#: mark left behind by a demo — a stored peak of 100k against a 47k mock account
#: would halt the mock cycle and make the suite depend on run history.
PEAK_PATH_ENV = "AUTOOVERLAY_PEAK_PATH"

DEFAULT_ACCOUNT = "default"



@dataclass(frozen=True)
class PeakRecord:
    """A high-water mark plus provenance.

    ``tracked`` is the field that matters. When False the caller must not treat
    a 0% drawdown as evidence of health — it is evidence of ignorance.
    """

    nav_peak: Optional[float]
    overlay_peak: Optional[float]
    tracked: bool
    source: str  # "store" | "seeded" | "absent"


class PeakStore:
    """Running maxima of NAV and overlay collateral, persisted across restarts."""

    def __init__(self, path: Optional[Path | str] = None):
        if path is not None:
            self.path = Path(path)
        else:
            env_path = os.environ.get(PEAK_PATH_ENV)
            self.path = Path(env_path) if env_path else DEFAULT_PEAK_PATH
        self._degraded_to_fallback = False


    # -- io ---------------------------------------------------------------- #

    def _load(self) -> dict:
        for candidate in self._candidate_paths():
            try:
                if candidate.is_file():
                    data = json.loads(candidate.read_text())
                    if isinstance(data, dict):
                        return data
            except (OSError, ValueError):
                continue  # unreadable or malformed — treat as absent
        return {}

    def _candidate_paths(self) -> list[Path]:
        if self.path == DEFAULT_PEAK_PATH:
            return [self.path, FALLBACK_PEAK_PATH]
        return [self.path]

    def _write(self, data: dict) -> None:
        for candidate in self._candidate_paths():
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                tmp = candidate.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
                os.replace(tmp, candidate)
                self._degraded_to_fallback = candidate is not self.path
                return
            except OSError:
                continue
        # Both paths unwritable: the cycle still runs, the peak just does not
        # persist. Silence here is acceptable only because `tracked` already
        # tells the kill-switch the mark is untrustworthy.

    # -- api --------------------------------------------------------------- #

    def read(self, account_id: str = DEFAULT_ACCOUNT) -> PeakRecord:
        entry = self._load().get(account_id)
        if not isinstance(entry, dict):
            return PeakRecord(None, None, False, "absent")
        nav = _finite(entry.get("nav_peak"))
        overlay = _finite(entry.get("overlay_peak"))
        if nav is None and overlay is None:
            return PeakRecord(None, None, False, "absent")
        return PeakRecord(nav, overlay, True, "store")

    def observe(
        self,
        equity: Optional[float],
        overlay_collateral: Optional[float] = None,
        account_id: str = DEFAULT_ACCOUNT,
    ) -> PeakRecord:
        """Record an observation and return the resulting high-water marks.

        The first observation for an account establishes the mark rather than
        reporting a drawdown against it — a fresh install has no history, and
        inventing one would be worse than admitting the gap. That first record
        is returned with ``tracked=False`` and ``source="seeded"``.
        """
        data = self._load()
        entry = data.get(account_id)
        entry = dict(entry) if isinstance(entry, dict) else {}
        had_history = bool(_finite(entry.get("nav_peak")) is not None
                           or _finite(entry.get("overlay_peak")) is not None)

        eq = _finite(equity)
        ov = _finite(overlay_collateral)

        nav_peak = _max_optional(_finite(entry.get("nav_peak")), eq)
        overlay_peak = _max_optional(_finite(entry.get("overlay_peak")), ov)

        if nav_peak is not None:
            entry["nav_peak"] = nav_peak
        if overlay_peak is not None:
            entry["overlay_peak"] = overlay_peak

        if entry:
            data[account_id] = entry
            self._write(data)

        return PeakRecord(
            nav_peak,
            overlay_peak,
            tracked=had_history,
            source="store" if had_history else "seeded",
        )

    def reset(self, account_id: Optional[str] = None) -> None:
        """Clear stored marks. Used by tests and by a deliberate operator reset."""
        if account_id is None:
            data: dict = {}
        else:
            data = self._load()
            data.pop(account_id, None)
        self._write(data)


def _finite(value) -> Optional[float]:
    import math

    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _max_optional(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)
