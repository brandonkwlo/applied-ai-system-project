"""
tests/test_agent_safety.py
Tests for agent safety guards and tool executor functions.
These tests do NOT require a Gemini API key.

Note: the tool executor functions (_tool_edit_task, etc.) return plain dicts.
The _dispatch() wrapper is what serializes them to JSON for the Gemini API.
"""
import json
import pytest

from pawpal_system import Task, Pet, Owner, Scheduler
from agent_system import (
    _tool_edit_task,
    _tool_add_task,
    _tool_remove_task,
    _tool_reschedule_task,
    _tool_generate_plan,
    _tool_get_schedule_state,
    _dispatch,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_scheduler(time_available: int = 180) -> Scheduler:
    owner = Owner(name="Alex", contact_info="alex@test.com", time_available=time_available)
    scheduler = Scheduler(owner=owner)
    owner.scheduler = scheduler
    return scheduler


def add_pet(scheduler: Scheduler, name="Buddy", species="Dog", breed="Golden Retriever",
            age=4, activity_level="medium", health_history=None) -> Pet:
    pet = Pet(
        name=name, age=age, breed=breed, species=species,
        activity_level=activity_level, health_history=health_history or []
    )
    scheduler.owner.add_pet(pet)
    return pet


def add_task(scheduler: Scheduler, pet_name: str, task_name: str,
             category="walk", duration=20, priority=3, must_occur_at="") -> Task:
    task = Task(
        name=task_name, category=category, duration=duration,
        priority=priority, must_occur_at=must_occur_at
    )
    scheduler.add_task(pet_name, task)
    return task


def make_log():
    return []


# ── _tool_edit_task ───────────────────────────────────────────────────────────

def test_edit_task_changes_priority():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Morning Walk")
    s.generate_plan()

    result = _tool_edit_task(s, "Buddy", "Morning Walk", {"priority": 5}, make_log())
    assert result.get("status") == "ok"
    pet = s.owner.get_pet("Buddy")
    task = next(t for t in pet.tasks if t.name == "Morning Walk")
    assert task.priority == 5


def test_edit_task_strips_is_completed():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Morning Walk")
    s.generate_plan()

    log = make_log()
    result = _tool_edit_task(s, "Buddy", "Morning Walk", {"priority": 4, "is_completed": True}, log)
    pet = s.owner.get_pet("Buddy")
    task = next(t for t in pet.tasks if t.name == "Morning Walk")
    # is_completed must never be set by the agent
    assert task.is_completed is False
    if "applied_changes" in result:
        assert "is_completed" not in result["applied_changes"]


def test_edit_task_returns_error_for_unknown_pet():
    s = make_scheduler()
    add_pet(s)
    result = _tool_edit_task(s, "NonExistentPet", "Walk", {"priority": 3}, make_log())
    assert "error" in result


def test_edit_task_returns_error_for_unknown_task():
    s = make_scheduler()
    add_pet(s)
    result = _tool_edit_task(s, "Buddy", "NonExistentTask", {"priority": 3}, make_log())
    assert "error" in result


def test_edit_task_only_is_completed_returns_error():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Morning Walk")
    result = _tool_edit_task(s, "Buddy", "Morning Walk", {"is_completed": True}, make_log())
    assert "error" in result


# ── _tool_add_task ────────────────────────────────────────────────────────────

def test_add_task_increases_task_count():
    s = make_scheduler()
    add_pet(s)
    before = len(s.owner.get_all_tasks())
    result = _tool_add_task(s, "Buddy", "Evening Walk", "walk", 30, 3, make_log())
    assert result.get("status") == "ok"
    assert len(s.owner.get_all_tasks()) == before + 1


def test_add_task_returns_error_for_unknown_pet():
    s = make_scheduler()
    result = _tool_add_task(s, "Ghost", "Walk", "walk", 20, 3, make_log())
    assert "error" in result


def test_add_task_rejects_invalid_category():
    s = make_scheduler()
    add_pet(s)
    result = _tool_add_task(s, "Buddy", "Fly", "flying", 20, 3, make_log())
    assert "error" in result


# ── _tool_remove_task ─────────────────────────────────────────────────────────

def test_remove_task_succeeds_when_safe():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Trick Training", "enrichment", 20, 1)
    s.generate_plan()

    removal_ref = [0]
    result = _tool_remove_task(s, "Buddy", "Trick Training", "low priority", make_log(), removal_ref)
    assert result.get("status") == "ok"
    assert removal_ref[0] == 1


def test_remove_task_blocked_when_last_meds_task():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Daily Medication", "meds", 5, 5)
    s.generate_plan()

    removal_ref = [0]
    result = _tool_remove_task(s, "Buddy", "Daily Medication", "test", make_log(), removal_ref)
    assert "error" in result
    assert "Cannot remove" in result["error"]
    assert removal_ref[0] == 0  # count unchanged


def test_remove_task_blocked_when_last_feeding_task():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Breakfast", "feeding", 10, 5)
    s.generate_plan()

    removal_ref = [0]
    result = _tool_remove_task(s, "Buddy", "Breakfast", "test", make_log(), removal_ref)
    assert "error" in result
    assert removal_ref[0] == 0


def test_remove_meds_allowed_when_second_meds_task_exists():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Morning Meds", "meds", 5, 5)
    add_task(s, "Buddy", "Evening Meds", "meds", 5, 5)
    s.generate_plan()

    removal_ref = [0]
    result = _tool_remove_task(s, "Buddy", "Evening Meds", "duplicate", make_log(), removal_ref)
    assert result.get("status") == "ok"


def test_remove_task_blocked_at_cap():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Trick Training", "enrichment", 20, 1)
    s.generate_plan()

    removal_ref = [2]  # already at cap
    result = _tool_remove_task(s, "Buddy", "Trick Training", "test", make_log(), removal_ref)
    assert "error" in result
    assert "cap" in result["error"].lower()


def test_remove_task_returns_error_for_unknown_task():
    s = make_scheduler()
    add_pet(s)
    removal_ref = [0]
    result = _tool_remove_task(s, "Buddy", "Ghost Task", "test", make_log(), removal_ref)
    assert "error" in result


# ── _tool_reschedule_task ─────────────────────────────────────────────────────

def test_reschedule_task_changes_must_occur_at():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Morning Walk", "walk", 30, 3, must_occur_at="08:00 AM")
    s.generate_plan()

    result = _tool_reschedule_task(s, "Buddy", "Morning Walk", "09:00 AM", "conflict resolution", make_log())
    assert result.get("status") == "ok"
    pet = s.owner.get_pet("Buddy")
    task = next(t for t in pet.tasks if t.name == "Morning Walk")
    assert task.must_occur_at == "09:00 AM"


def test_reschedule_task_empty_time_makes_flexible():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Morning Walk", "walk", 30, 3, must_occur_at="08:00 AM")
    s.generate_plan()

    result = _tool_reschedule_task(s, "Buddy", "Morning Walk", "", "make flexible", make_log())
    assert result.get("status") == "ok"
    pet = s.owner.get_pet("Buddy")
    task = next(t for t in pet.tasks if t.name == "Morning Walk")
    assert task.must_occur_at == ""


# ── _tool_generate_plan ───────────────────────────────────────────────────────

def test_generate_plan_returns_conflict_count():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Walk A", "walk", 20, 3, must_occur_at="08:00 AM")
    add_task(s, "Buddy", "Walk B", "walk", 20, 3, must_occur_at="08:00 AM")

    result = _tool_generate_plan(s, make_log())
    assert "conflict_count" in result
    assert result["conflict_count"] >= 1


def test_generate_plan_logs_entry():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Morning Walk", "walk", 20, 3)
    log = make_log()
    _tool_generate_plan(s, log)
    assert any("[PLAN]" in entry for entry in log)


# ── _tool_get_schedule_state ──────────────────────────────────────────────────

def test_get_schedule_state_returns_conflicts():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Walk A", "walk", 20, 3, must_occur_at="08:00 AM")
    add_task(s, "Buddy", "Walk B", "walk", 20, 3, must_occur_at="08:00 AM")
    s.generate_plan()

    result = _tool_get_schedule_state(s)
    assert "conflicts" in result
    assert len(result["conflicts"]) >= 1


def test_get_schedule_state_includes_pet_profiles():
    s = make_scheduler()
    add_pet(s, name="Luna", species="Cat", breed="Siamese", health_history=["Anxiety"])
    s.generate_plan()

    result = _tool_get_schedule_state(s)
    pets = result.get("pet_profiles", [])
    assert any(p["name"] == "Luna" for p in pets)
    luna = next(p for p in pets if p["name"] == "Luna")
    assert "Anxiety" in luna["health_history"]


def test_get_schedule_state_skipped_tasks_listed():
    s = make_scheduler(time_available=30)
    add_pet(s)
    add_task(s, "Buddy", "Short Walk", "walk", 20, 3)
    add_task(s, "Buddy", "Long Training", "enrichment", 60, 1)
    s.generate_plan()

    result = _tool_get_schedule_state(s)
    skipped_names = [t["task_name"] for t in result.get("skipped_tasks", [])]
    assert "Long Training" in skipped_names


# ── _dispatch serializes to JSON string ───────────────────────────────────────

def test_dispatch_returns_json_string():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Walk", "walk", 20, 3)
    s.generate_plan()

    result_str = _dispatch(
        "get_schedule_state", {}, s, make_log(), [], set(), [0]
    )
    assert isinstance(result_str, str)
    data = json.loads(result_str)
    assert "pet_profiles" in data


def test_dispatch_unknown_tool_returns_error_json():
    s = make_scheduler()
    result_str = _dispatch("nonexistent_tool", {}, s, make_log(), [], set(), [0])
    data = json.loads(result_str)
    assert "error" in data


# ── Action log ────────────────────────────────────────────────────────────────

def test_edit_task_logs_edit_entry():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Morning Walk")
    log = make_log()
    _tool_edit_task(s, "Buddy", "Morning Walk", {"priority": 5}, log)
    assert any("[EDIT]" in entry for entry in log)


def test_add_task_logs_add_entry():
    s = make_scheduler()
    add_pet(s)
    log = make_log()
    _tool_add_task(s, "Buddy", "Evening Walk", "walk", 30, 3, log)
    assert any("[ADD]" in entry for entry in log)


def test_remove_task_logs_remove_entry():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Trick Training", "enrichment", 20, 1)
    add_task(s, "Buddy", "Agility", "enrichment", 30, 2)
    s.generate_plan()
    log = make_log()
    _tool_remove_task(s, "Buddy", "Trick Training", "low priority", log, [0])
    assert any("[REMOVE]" in entry for entry in log)


def test_reschedule_task_logs_entry():
    s = make_scheduler()
    add_pet(s)
    add_task(s, "Buddy", "Walk", must_occur_at="08:00 AM")
    s.generate_plan()
    log = make_log()
    _tool_reschedule_task(s, "Buddy", "Walk", "09:00 AM", "test", log)
    assert any("[RESCHEDULE]" in entry for entry in log)
