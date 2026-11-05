"""
Pipeline runs: one run = the whole pipeline (BQ1 + BQ2) on one dataset.

The UI only talks to `registry()` and `current_run()`. The backend is a stub for now:
`runs.json` (committed) lists the runs, and a small local state file remembers runs
removed from the UI. When the per-run pipeline exists (each run in its own S3 prefix
and Athena databases), swap `JsonRunRegistry` for one that reads the real registry
(e.g. a JSON manifest in S3 or an Athena/Glue table) and implements `delete_data`.
Nothing here touches S3 or Athena today.

    from common.runs import current_run
    run = current_run()
    run.db("bq2")   # -> "aml_bq2_curated" for Run 1
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parents[1]           # dashboard/
REGISTRY_FILE = HERE / "runs.json"                    # committed list of runs
STATE_DIR = Path(os.getenv("DASHBOARD_STATE_DIR", HERE / ".state"))  # not committed
STATE_FILE = STATE_DIR / "runs_state.json"
DELETE_LOG = STATE_DIR / "run_deletions.log"


@dataclass(frozen=True)
class Run:
    run_id: str
    name: str                     # dataset name shown in the menu, e.g. "IBM AML HI-Medium"
    created_at: str               # ISO date
    status: str                   # succeeded | running | failed
    databases: dict = field(default_factory=dict)   # {"bq1": ..., "bq2": ..., "clean": ...}
    s3_prefix: str = ""
    row_counts: dict = field(default_factory=dict)
    period: str = ""
    notes: str = ""

    def db(self, key: str, default: str = "") -> str:
        return self.databases.get(key, default)

    @property
    def label(self) -> str:
        return f"{self.name}"

    def __hash__(self):  # lets st.cache_data hash a Run
        return hash(self.run_id)


class JsonRunRegistry:
    """Stub registry: runs.json + a local list of runs hidden from the UI."""

    def __init__(self, registry_file: Path = REGISTRY_FILE, state_file: Path = STATE_FILE):
        self.registry_file, self.state_file = registry_file, state_file

    def _state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (FileNotFoundError, ValueError):
            return {"deleted": []}

    def _save_state(self, state: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2))

    def all_runs(self) -> list[Run]:
        raw = json.loads(self.registry_file.read_text())["runs"]
        return [Run(**r) for r in raw]

    def list_runs(self) -> list[Run]:
        deleted = set(self._state()["deleted"])
        return [r for r in self.all_runs() if r.run_id not in deleted]

    def deleted_runs(self) -> list[Run]:
        deleted = set(self._state()["deleted"])
        return [r for r in self.all_runs() if r.run_id in deleted]

    def get(self, run_id: str) -> Run | None:
        return next((r for r in self.list_runs() if r.run_id == run_id), None)

    def remove(self, run_id: str, who: str = "dashboard user") -> None:
        """Remove a run from the registry (hides it from every page)."""
        state = self._state()
        if run_id not in state["deleted"]:
            state["deleted"].append(run_id)
        self._save_state(state)
        _log(f"removed run {run_id} from the registry ({who})")

    def restore(self, run_id: str) -> None:
        state = self._state()
        state["deleted"] = [r for r in state["deleted"] if r != run_id]
        self._save_state(state)
        _log(f"restored run {run_id} to the registry")

    def delete_data(self, run: Run) -> list[str]:
        """Delete a run's S3 outputs and Athena tables.

        Not wired up yet: the per-run storage does not exist, and Run 1 shares its tables
        with the live dashboard. Returns what *would* be deleted and logs it, so the UI
        flow can be tested end to end without touching AWS.
        """
        planned = self.planned_targets(run)
        _log(f"DRY RUN delete data for {run.run_id}: " + "; ".join(planned))
        return planned

    @staticmethod
    def planned_targets(run: Run) -> list[str]:
        return ([f"s3://{run.s3_prefix}"] if run.s3_prefix else []) + \
               [f"Athena database {d}" for d in run.databases.values()]

    @property
    def can_delete_data(self) -> bool:
        return False


def _log(msg: str) -> None:
    DELETE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DELETE_LOG.open("a") as f:
        f.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC  {msg}\n")


def read_log(n: int = 20) -> list[str]:
    try:
        return DELETE_LOG.read_text().splitlines()[-n:]
    except FileNotFoundError:
        return []


@st.cache_resource
def registry() -> JsonRunRegistry:
    return JsonRunRegistry()


RUN_KEY = "run_id"


def current_run() -> Run | None:
    """The run picked in the header. Falls back to the first run."""
    runs = registry().list_runs()
    if not runs:
        return None
    rid = st.session_state.get(RUN_KEY)
    return next((r for r in runs if r.run_id == rid), runs[0])
