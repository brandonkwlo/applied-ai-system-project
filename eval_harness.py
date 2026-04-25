"""
eval_harness.py
Evaluation harness for PawPal+ AI system.

Two modes:
  --dry-run (default)  Tests tool executor safety guards. No API key required.
  --live               Runs the full agent loop via Gemini API.

Usage:
  uv run python eval_harness.py
  uv run python eval_harness.py --live
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

from pawpal_system import Owner, Pet, Task, Scheduler
from agent_system import (
    _tool_edit_task,
    _tool_add_task,
    _tool_remove_task,
    _tool_reschedule_task,
    _tool_generate_plan,
    run_agent,
    AgentResult,
)

load_dotenv()


# ── Shared setup helpers ───────────────────────────────────────────────────────

def _make_scheduler(time_available: int = 180) -> Scheduler:
    owner = Owner(name="Eval", contact_info="eval@test.com", time_available=time_available)
    scheduler = Scheduler(owner=owner)
    owner.scheduler = scheduler
    return scheduler


def _add_pet(scheduler: Scheduler, name: str, species: str = "Dog",
             breed: str = "Mixed", age: int = 4, activity_level: str = "medium",
             health_history: list[str] | None = None) -> Pet:
    pet = Pet(
        name=name, age=age, breed=breed, species=species,
        activity_level=activity_level, health_history=health_history or [],
    )
    scheduler.owner.add_pet(pet)
    return pet


def _add_task(scheduler: Scheduler, pet_name: str, task_name: str,
              category: str = "walk", duration: int = 20, priority: int = 3,
              must_occur_at: str = "") -> Task:
    task = Task(
        name=task_name, category=category, duration=duration,
        priority=priority, must_occur_at=must_occur_at,
    )
    scheduler.add_task(pet_name, task)
    return task


# ── ScenarioResult ─────────────────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    name: str
    checks: list[tuple[str, bool]] = field(default_factory=list)

    @property
    def checks_passed(self) -> int:
        return sum(1 for _, ok in self.checks)

    @property
    def checks_total(self) -> int:
        return len(self.checks)

    @property
    def passed(self) -> bool:
        return self.checks_total > 0 and all(ok for _, ok in self.checks)

    def check(self, label: str, ok: bool) -> None:
        self.checks.append((label, ok))


# ── Dry-run scenarios (no API key) ────────────────────────────────────────────

def dry_reschedule_resolves_conflict() -> ScenarioResult:
    r = ScenarioResult("Reschedule resolves a time conflict")
    s = _make_scheduler()
    _add_pet(s, "Buddy", health_history=["Arthritis"])
    _add_task(s, "Buddy", "Morning Walk", duration=30, must_occur_at="08:00 AM")
    _add_task(s, "Buddy", "Joint Supplement", category="meds", duration=10,
              priority=5, must_occur_at="08:00 AM")
    s.generate_plan()

    log: list[str] = []
    res = _tool_reschedule_task(s, "Buddy", "Joint Supplement", "08:30 AM",
                                "conflict with Morning Walk", log)
    r.check("reschedule returns ok", res.get("status") == "ok")
    pet = s.owner.get_pet("Buddy")
    task = next(t for t in pet.tasks if t.name == "Joint Supplement")
    r.check("must_occur_at updated", task.must_occur_at == "08:30 AM")
    r.check("[RESCHEDULE] logged", any("[RESCHEDULE]" in e for e in log))
    return r


def dry_last_meds_protected() -> ScenarioResult:
    r = ScenarioResult("Last meds task cannot be removed")
    s = _make_scheduler()
    _add_pet(s, "Buddy")
    _add_task(s, "Buddy", "Daily Medication", category="meds", priority=5)
    s.generate_plan()

    log: list[str] = []
    res = _tool_remove_task(s, "Buddy", "Daily Medication", "test", log, [0])
    r.check("remove returns error", "error" in res)
    r.check("error says Cannot remove", "Cannot remove" in res.get("error", ""))
    still_has_task = any(t.name == "Daily Medication" for t in s.owner.get_pet("Buddy").tasks)
    r.check("task still exists", still_has_task)
    return r


def dry_is_completed_stripped() -> ScenarioResult:
    r = ScenarioResult("is_completed is stripped from edit_task")
    s = _make_scheduler()
    _add_pet(s, "Buddy")
    _add_task(s, "Buddy", "Morning Walk")
    s.generate_plan()

    log: list[str] = []
    res = _tool_edit_task(s, "Buddy", "Morning Walk",
                          {"priority": 4, "is_completed": True}, log)
    r.check("edit returns ok", res.get("status") == "ok")
    task = next(t for t in s.owner.get_pet("Buddy").tasks if t.name == "Morning Walk")
    r.check("priority updated", task.priority == 4)
    r.check("is_completed still False", task.is_completed is False)
    return r


def dry_removal_cap_enforced() -> ScenarioResult:
    r = ScenarioResult("Removal cap blocks excess deletions")
    s = _make_scheduler()
    _add_pet(s, "Buddy")
    _add_task(s, "Buddy", "Trick Training", category="enrichment", priority=1)
    s.generate_plan()

    log: list[str] = []
    removal_ref = [2]   # already at cap
    res = _tool_remove_task(s, "Buddy", "Trick Training", "low priority", log, removal_ref)
    r.check("remove returns error", "error" in res)
    r.check("error mentions cap", "cap" in res.get("error", "").lower())
    r.check("removal_ref unchanged", removal_ref[0] == 2)
    return r


def dry_add_task_works() -> ScenarioResult:
    r = ScenarioResult("Add task increases task count")
    s = _make_scheduler()
    _add_pet(s, "Buddy")
    before = len(s.owner.get_all_tasks())

    log: list[str] = []
    res = _tool_add_task(s, "Buddy", "Evening Walk", "walk", 30, 3, log)
    r.check("add returns ok", res.get("status") == "ok")
    r.check("task count increased", len(s.owner.get_all_tasks()) == before + 1)
    r.check("[ADD] logged", any("[ADD]" in e for e in log))
    return r


DRY_SCENARIOS = [
    dry_reschedule_resolves_conflict,
    dry_last_meds_protected,
    dry_is_completed_stripped,
    dry_removal_cap_enforced,
    dry_add_task_works,
]


# ── Live scenarios (requires GEMINI_API_KEY) ───────────────────────────────────

def _run_agent_safe(scheduler: Scheduler) -> AgentResult | None:
    try:
        return run_agent(scheduler)
    except Exception as exc:
        return AgentResult(
            success=False, summary="", action_log=[], retrieved_chunk_titles=[],
            before_conflict_count=0, after_conflict_count=0,
            before_skipped_count=0, after_skipped_count=0,
            iterations_used=0, error=str(exc),
        )


def live_conflict_resolution() -> ScenarioResult:
    r = ScenarioResult("Conflict Resolution — arthritic dog")
    s = _make_scheduler()
    _add_pet(s, "Buddy", breed="Golden Retriever", age=8,
             health_history=["Arthritis"])
    _add_task(s, "Buddy", "Morning Walk", duration=30, priority=4,
              must_occur_at="08:00 AM")
    _add_task(s, "Buddy", "Joint Supplement", category="meds", duration=10,
              priority=5, must_occur_at="08:00 AM")

    ar = _run_agent_safe(s)
    if ar is None:
        r.check("agent completed", False)
        return r
    r.check("agent succeeded", ar.success)
    r.check("conflicts resolved (after == 0)", ar.after_conflict_count == 0)
    r.check("KB was searched", any("[KB SEARCH]" in e for e in ar.action_log))
    r.check("action_log non-empty", len(ar.action_log) > 0)
    return r


def live_missing_enrichment() -> ScenarioResult:
    r = ScenarioResult("Missing Enrichment — anxious indoor cat")
    s = _make_scheduler()
    _add_pet(s, "Luna", species="Cat", breed="Siamese", age=3,
             activity_level="high",
             health_history=["Indoor only", "stress-related over-grooming"])
    _add_task(s, "Luna", "Morning Feeding", category="feeding", duration=10, priority=5)
    _add_task(s, "Luna", "Evening Feeding", category="feeding", duration=10, priority=5)

    ar = _run_agent_safe(s)
    if ar is None:
        r.check("agent completed", False)
        return r
    r.check("agent succeeded", ar.success)
    r.check("task added ([ADD] in log)", any("[ADD]" in e for e in ar.action_log))
    r.check("KB was searched", any("[KB SEARCH]" in e for e in ar.action_log))
    return r


def live_tight_budget() -> ScenarioResult:
    r = ScenarioResult("Tight Time Budget — 130 min tasks vs 90 min available")
    s = _make_scheduler(time_available=90)
    _add_pet(s, "Max")
    _add_task(s, "Max", "Medication", category="meds", duration=5, priority=5,
              must_occur_at="08:00 AM")
    _add_task(s, "Max", "Morning Walk", duration=45, priority=4)
    _add_task(s, "Max", "Grooming", category="grooming", duration=30, priority=2)
    _add_task(s, "Max", "Trick Training", category="enrichment", duration=30, priority=1)
    _add_task(s, "Max", "Nail Trim", category="grooming", duration=20, priority=2)

    ar = _run_agent_safe(s)
    if ar is None:
        r.check("agent completed", False)
        return r
    r.check("agent succeeded", ar.success)
    r.check("skipped tasks not increased", ar.after_skipped_count <= ar.before_skipped_count)
    # Priority-5 medication must stay scheduled
    scheduled_names = {t.name for t, _ in s.plan}
    r.check("Medication (priority 5) still scheduled", "Medication" in scheduled_names)
    return r


def live_no_issues() -> ScenarioResult:
    r = ScenarioResult("No Issues — healthy dog, nothing to fix")
    s = _make_scheduler()
    _add_pet(s, "Rex", breed="Labrador")
    _add_task(s, "Rex", "Morning Walk", duration=30, priority=4)
    _add_task(s, "Rex", "Feeding", category="feeding", duration=10, priority=5)
    _add_task(s, "Rex", "Play Time", category="enrichment", duration=20, priority=3)

    ar = _run_agent_safe(s)
    if ar is None:
        r.check("agent completed", False)
        return r
    r.check("agent succeeded", ar.success)
    r.check("no conflicts after run", ar.after_conflict_count == 0)
    r.check("no tasks removed", not any("[REMOVE]" in e for e in ar.action_log))
    return r


LIVE_SCENARIOS = [
    live_conflict_resolution,
    live_missing_enrichment,
    live_tight_budget,
    live_no_issues,
]


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_harness(live: bool) -> int:
    print("=" * 48)
    print("PawPal+ Evaluation Harness")
    print("=" * 48)

    if live:
        print("[LIVE] Running full Gemini agent loop")
        scenarios = LIVE_SCENARIOS
    else:
        print("[DRY RUN] No API calls — testing tool executors")
        scenarios = DRY_SCENARIOS

    print()

    all_results: list[ScenarioResult] = []
    for i, fn in enumerate(scenarios, 1):
        result = fn()
        print(f"Scenario {i}: {result.name}")
        for label, ok in result.checks:
            sym = "✓" if ok else "✗"
            print(f"  {sym} {label}")
        status = "PASS" if result.passed else "FAIL"
        print(f"  {status} ({result.checks_passed}/{result.checks_total})")
        print()
        all_results.append(result)

    total_checks = sum(r.checks_total for r in all_results)
    total_passed = sum(r.checks_passed for r in all_results)
    scenarios_passed = sum(1 for r in all_results if r.passed)
    pct = (100 * total_passed // total_checks) if total_checks else 0

    print("=" * 48)
    print(f"TOTAL: {total_passed}/{total_checks} checks passed ({pct}%)")
    print(f"       {scenarios_passed}/{len(all_results)} scenarios PASS")
    print("=" * 48)

    return 0 if all_results and all(r.passed for r in all_results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="PawPal+ AI evaluation harness")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run full agent loop via Gemini API (requires GEMINI_API_KEY in .env).",
    )
    args = parser.parse_args()
    sys.exit(run_harness(live=args.live))


if __name__ == "__main__":
    main()
