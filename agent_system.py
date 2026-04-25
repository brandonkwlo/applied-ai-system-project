"""
agent_system.py
Gemini-powered agentic schedule optimizer for PawPal+.

Public entry point:
    run_agent(scheduler: Scheduler) -> AgentResult
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types
from dotenv import load_dotenv

from pawpal_system import Scheduler, Task
from rag_system import get_retriever, KnowledgeChunk

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────

MODEL = "gemini-2.0-flash"
MAX_ITERATIONS = 7   # counts only mutation batches; search calls are free
MAX_REMOVALS = 2

SYSTEM_PROMPT = """You are PawPal+'s AI Schedule Optimizer. Your job is to improve a pet owner's daily care schedule by resolving conflicts, ensuring skipped high-priority tasks get scheduled, and grounding every health-related decision in the pet care knowledge base.

## Process
1. Call get_schedule_state first to understand the full schedule, conflicts, skipped tasks, and pet profiles.
2. SEARCH BEFORE ACTING: Before adding or editing any task related to a pet's health condition, chronic illness, medication, breed-specific need, or life stage, call search_pet_care_knowledge with a specific query. Use what you find to justify the change.
3. Fix problems using the mutation tools: reschedule_task for conflicts, edit_task for adjustments, add_task for genuine care gaps, remove_task only as a last resort.
4. Call generate_plan after each batch of mutations to verify improvement.
5. Stop when conflicts are resolved and high-priority tasks are scheduled, or when no further improvement is possible.

## Hard Constraints
- Never remove the last meds task for any pet.
- Never remove the last feeding task for any pet.
- Never remove more than 2 tasks total in one run.
- Never change is_completed on any task.
- Always prefer reschedule_task over remove_task to resolve conflicts.
- Keep changes minimal — only fix what is broken.

## Final Output
End with a concise bullet-point summary of what you changed and why. For health-informed changes, cite the knowledge article that guided the decision. Finish with: Confidence: X/5 (1=low, 5=high) based on how complete the pet profile information was."""

# ── AgentResult ───────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    success: bool
    summary: str
    action_log: list[str]
    retrieved_chunk_titles: list[str]
    before_conflict_count: int
    after_conflict_count: int
    before_skipped_count: int
    after_skipped_count: int
    iterations_used: int
    error: str | None = None


# ── Tool schemas ──────────────────────────────────────────────────────────────

def _build_tools() -> list[types.Tool]:
    FD = types.FunctionDeclaration
    S = types.Schema
    T = types.Type

    def obj(**props: types.Schema) -> types.Schema:
        return S(type=T.OBJECT, properties=props)

    def str_prop(desc: str) -> types.Schema:
        return S(type=T.STRING, description=desc)

    def int_prop(desc: str) -> types.Schema:
        return S(type=T.INTEGER, description=desc)

    declarations = [
        FD(
            name="get_schedule_state",
            description=(
                "Read the complete current schedule: the generated plan, all conflicts, "
                "skipped tasks, and each pet's profile including health history and medication times. "
                "Always call this first before making any changes."
            ),
            parameters=obj(),
        ),
        FD(
            name="search_pet_care_knowledge",
            description=(
                "Search the curated pet care knowledge base for evidence-based guidance. "
                "ALWAYS call this before adding or editing any task related to a health condition, "
                "medication, breed-specific care, chronic illness, or life stage. "
                "Returns the top 4 most relevant knowledge chunks. "
                "Search calls do not count toward the iteration limit."
            ),
            parameters=obj(
                query=str_prop(
                    "Natural-language question to search. Be specific — include species, "
                    "life stage, and condition (e.g. 'senior dog arthritis joint supplement timing')."
                )
            ),
        ),
        FD(
            name="edit_task",
            description=(
                "Modify fields of an existing task. Use to change priority, duration, "
                "must_occur_at, category, description, or frequency. "
                "Do NOT change is_completed or task name."
            ),
            parameters=obj(
                pet_name=str_prop("Exact name of the pet who owns the task."),
                task_name=str_prop("Exact name of the task to edit."),
                changes=S(
                    type=T.OBJECT,
                    description=(
                        "Fields to update. Allowed: priority (int 1-5), duration (int minutes), "
                        "must_occur_at (str 'HH:MM AM/PM' or '' for flexible), "
                        "category (walk/feeding/meds/grooming/enrichment/other), "
                        "description (str), frequency (daily/weekly/once)."
                    ),
                ),
            ),
        ),
        FD(
            name="add_task",
            description=(
                "Add a new task to a pet's schedule. Only use when a genuine care gap exists. "
                "For health-related tasks, call search_pet_care_knowledge first."
            ),
            parameters=obj(
                pet_name=str_prop("Exact name of the pet to add the task to."),
                task_name=str_prop("Short descriptive name for the task."),
                category=str_prop("One of: walk, feeding, meds, grooming, enrichment, other."),
                duration=int_prop("Duration in minutes (1-240)."),
                priority=int_prop("Priority 1 (low) to 5 (high)."),
                description=str_prop("Optional description."),
                must_occur_at=str_prop("Fixed time 'HH:MM AM/PM', or '' for flexible."),
                frequency=str_prop("One of: daily, weekly, once."),
            ),
        ),
        FD(
            name="remove_task",
            description=(
                "Remove a task from a pet's schedule. Subject to safety guards: "
                "cannot remove the last meds or feeding task for any pet, "
                "and at most 2 removals allowed per run. Prefer reschedule_task over this."
            ),
            parameters=obj(
                pet_name=str_prop("Exact name of the pet who owns the task."),
                task_name=str_prop("Exact name of the task to remove."),
                reason=str_prop("Required: why this task is being removed."),
            ),
        ),
        FD(
            name="reschedule_task",
            description=(
                "Change the fixed time (must_occur_at) of a task to resolve a conflict. "
                "Preferred over remove_task for conflict resolution. "
                "Pass '' as new_time to make the task flexible."
            ),
            parameters=obj(
                pet_name=str_prop("Exact name of the pet who owns the task."),
                task_name=str_prop("Exact name of the task to reschedule."),
                new_time=str_prop("New time 'HH:MM AM/PM', or '' for flexible."),
                reason=str_prop("Why this time change resolves the issue."),
            ),
        ),
        FD(
            name="generate_plan",
            description=(
                "Regenerate the schedule after mutations. Call this after a batch of changes "
                "to see updated conflict count and skipped tasks. "
                "Call at most once per iteration batch."
            ),
            parameters=obj(),
        ),
    ]
    return [types.Tool(function_declarations=declarations)]


# ── Tool executors ────────────────────────────────────────────────────────────

def _tool_get_schedule_state(scheduler: Scheduler) -> dict:
    owner = scheduler.owner
    plan_items = [
        {
            "task_name": t.name,
            "pet_name": t.pet_name,
            "category": t.category,
            "duration_min": t.duration,
            "priority": t.priority,
            "time_slot": ts,
            "is_fixed": bool(t.must_occur_at),
            "must_occur_at": t.must_occur_at,
            "is_completed": t.is_completed,
        }
        for t, ts in scheduler.plan
    ]
    all_tasks = owner.get_all_tasks()
    scheduled_keys = {(t.pet_name, t.name) for t, _ in scheduler.plan}
    skipped = [
        {"task_name": t.name, "pet_name": t.pet_name, "duration_min": t.duration, "priority": t.priority}
        for t in all_tasks
        if (t.pet_name, t.name) not in scheduled_keys and not t.is_completed
    ]
    pets = [
        {
            "name": p.name,
            "species": p.species,
            "breed": p.breed,
            "age": p.age,
            "activity_level": p.activity_level,
            "health_history": p.health_history,
            "medication_times": p.medication_times,
        }
        for p in owner.pets
    ]
    return {
        "owner_name": owner.name,
        "time_available_min": owner.time_available,
        "total_scheduled_min": sum(t.duration for t, _ in scheduler.plan),
        "plan": plan_items,
        "conflicts": scheduler.detect_conflicts(),
        "skipped_tasks": skipped,
        "pet_profiles": pets,
    }


def _tool_search_knowledge(
    query: str,
    action_log: list[str],
    retrieved_titles: list[str],
    seen_titles: set[str],
) -> dict:
    retriever = get_retriever()
    chunks: list[KnowledgeChunk] = retriever.retrieve(query, top_k=4)
    titles_found = [c.title for c in chunks]
    action_log.append(
        f"[KB SEARCH] query='{query}' → " + ", ".join(f'"{t}"' for t in titles_found)
    )
    for title in titles_found:
        if title not in seen_titles:
            seen_titles.add(title)
            retrieved_titles.append(title)
    return {
        "query": query,
        "results": [
            {"title": c.title, "tags": c.tags, "relevance_score": round(c.score, 4), "content": c.content}
            for c in chunks
        ],
    }


def _tool_edit_task(
    scheduler: Scheduler,
    pet_name: str,
    task_name: str,
    changes: dict,
    action_log: list[str],
) -> dict:
    changes = {k: v for k, v in changes.items() if k != "is_completed"}
    if not changes:
        return {"error": "No valid fields to change (is_completed is read-only)."}
    pet = scheduler.owner.get_pet(pet_name)
    if pet is None:
        return {"error": f"Pet '{pet_name}' not found."}
    task = next((t for t in pet.tasks if t.name == task_name), None)
    if task is None:
        return {"error": f"Task '{task_name}' not found for {pet_name}."}
    scheduler.edit_task(pet_name, task_name, changes)
    action_log.append(f"[EDIT] {pet_name} / '{task_name}': {changes}")
    return {"status": "ok", "applied_changes": changes}


def _tool_add_task(
    scheduler: Scheduler,
    pet_name: str,
    task_name: str,
    category: str,
    duration: int,
    priority: int,
    action_log: list[str],
    description: str = "",
    must_occur_at: str = "",
    frequency: str = "daily",
) -> dict:
    if scheduler.owner.get_pet(pet_name) is None:
        return {"error": f"Pet '{pet_name}' not found."}
    valid_cats = {"walk", "feeding", "meds", "grooming", "enrichment", "other"}
    if category not in valid_cats:
        return {"error": f"Invalid category '{category}'. Must be one of {sorted(valid_cats)}."}
    new_task = Task(
        name=task_name,
        category=category,
        duration=int(duration),
        priority=int(priority),
        description=description,
        must_occur_at=must_occur_at or "",
        frequency=frequency or "daily",
    )
    scheduler.add_task(pet_name, new_task)
    action_log.append(
        f"[ADD] {pet_name} / '{task_name}' "
        f"(cat={category}, {duration}min, priority={priority}, "
        f"fixed='{must_occur_at or 'flexible'}')"
    )
    return {"status": "ok", "task_name": task_name, "pet_name": pet_name}


def _tool_remove_task(
    scheduler: Scheduler,
    pet_name: str,
    task_name: str,
    reason: str,
    action_log: list[str],
    removal_count_ref: list[int],
) -> dict:
    if removal_count_ref[0] >= MAX_REMOVALS:
        return {"error": f"Removal cap of {MAX_REMOVALS} reached. Cannot remove '{task_name}'."}
    pet = scheduler.owner.get_pet(pet_name)
    if pet is None:
        return {"error": f"Pet '{pet_name}' not found."}
    task = next((t for t in pet.tasks if t.name == task_name), None)
    if task is None:
        return {"error": f"Task '{task_name}' not found for {pet_name}."}
    if task.category in ("meds", "feeding"):
        same_cat = [t for t in pet.tasks if t.category == task.category]
        if len(same_cat) <= 1:
            return {"error": f"Cannot remove '{task_name}' — it is the only {task.category} task for {pet_name}."}
    pet.remove_task(task_name)
    removal_count_ref[0] += 1
    action_log.append(f"[REMOVE] {pet_name} / '{task_name}' — {reason}")
    return {"status": "ok"}


def _tool_reschedule_task(
    scheduler: Scheduler,
    pet_name: str,
    task_name: str,
    new_time: str,
    reason: str,
    action_log: list[str],
) -> dict:
    pet = scheduler.owner.get_pet(pet_name)
    if pet is None:
        return {"error": f"Pet '{pet_name}' not found."}
    task = next((t for t in pet.tasks if t.name == task_name), None)
    if task is None:
        return {"error": f"Task '{task_name}' not found for {pet_name}."}
    scheduler.edit_task(pet_name, task_name, {"must_occur_at": new_time or ""})
    label = new_time if new_time else "flexible"
    action_log.append(f"[RESCHEDULE] {pet_name} / '{task_name}' → {label} — {reason}")
    return {"status": "ok", "new_time": new_time}


def _tool_generate_plan(scheduler: Scheduler, action_log: list[str]) -> dict:
    scheduler.generate_plan()
    conflicts = scheduler.detect_conflicts()
    all_tasks = scheduler.owner.get_all_tasks()
    scheduled_keys = {(t.pet_name, t.name) for t, _ in scheduler.plan}
    skipped = [t for t in all_tasks if (t.pet_name, t.name) not in scheduled_keys and not t.is_completed]
    action_log.append(
        f"[PLAN] Regenerated — {len(conflicts)} conflict(s), {len(skipped)} skipped"
    )
    return {
        "status": "ok",
        "scheduled_count": len(scheduler.plan),
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "skipped_count": len(skipped),
    }


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _dispatch(
    name: str,
    args: dict,
    scheduler: Scheduler,
    action_log: list[str],
    retrieved_titles: list[str],
    seen_titles: set[str],
    removal_count_ref: list[int],
) -> str:
    try:
        if name == "get_schedule_state":
            result = _tool_get_schedule_state(scheduler)
        elif name == "search_pet_care_knowledge":
            result = _tool_search_knowledge(
                args.get("query", ""), action_log, retrieved_titles, seen_titles
            )
        elif name == "edit_task":
            result = _tool_edit_task(
                scheduler,
                args.get("pet_name", ""),
                args.get("task_name", ""),
                dict(args.get("changes", {})),
                action_log,
            )
        elif name == "add_task":
            result = _tool_add_task(
                scheduler,
                args.get("pet_name", ""),
                args.get("task_name", ""),
                args.get("category", "other"),
                int(args.get("duration", 15)),
                int(args.get("priority", 3)),
                action_log,
                description=args.get("description", ""),
                must_occur_at=args.get("must_occur_at", ""),
                frequency=args.get("frequency", "daily"),
            )
        elif name == "remove_task":
            result = _tool_remove_task(
                scheduler,
                args.get("pet_name", ""),
                args.get("task_name", ""),
                args.get("reason", ""),
                action_log,
                removal_count_ref,
            )
        elif name == "reschedule_task":
            result = _tool_reschedule_task(
                scheduler,
                args.get("pet_name", ""),
                args.get("task_name", ""),
                args.get("new_time", ""),
                args.get("reason", ""),
                action_log,
            )
        elif name == "generate_plan":
            result = _tool_generate_plan(scheduler, action_log)
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        result = {"error": str(exc)}
        action_log.append(f"[ERROR] {name}: {exc}")
    return json.dumps(result)


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_agent(scheduler: Scheduler) -> AgentResult:
    """
    Run the agentic optimization loop.
    Mutates scheduler (and its owner's pets/tasks) in place.
    Reads GEMINI_API_KEY from environment (loaded via dotenv).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return AgentResult(
            success=False,
            summary="",
            action_log=[],
            retrieved_chunk_titles=[],
            before_conflict_count=0,
            after_conflict_count=0,
            before_skipped_count=0,
            after_skipped_count=0,
            iterations_used=0,
            error="GEMINI_API_KEY not set. Add it to your .env file.",
        )

    if not scheduler.owner.get_all_tasks():
        return AgentResult(
            success=False,
            summary="",
            action_log=[],
            retrieved_chunk_titles=[],
            before_conflict_count=0,
            after_conflict_count=0,
            before_skipped_count=0,
            after_skipped_count=0,
            iterations_used=0,
            error="No tasks found. Add tasks before running the optimizer.",
        )

    client = genai.Client(api_key=api_key)
    tools = _build_tools()

    # Capture before-state
    scheduler.generate_plan()
    before_conflicts = scheduler.detect_conflicts()
    all_tasks_before = scheduler.owner.get_all_tasks()
    sched_keys_before = {(t.pet_name, t.name) for t, _ in scheduler.plan}
    before_skipped = [
        t for t in all_tasks_before
        if (t.pet_name, t.name) not in sched_keys_before and not t.is_completed
    ]

    action_log: list[str] = []
    retrieved_titles: list[str] = []
    seen_titles: set[str] = set()
    removal_count_ref = [0]
    iteration_count = 0
    final_summary = ""

    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=tools,
        ),
    )

    mutation_tools = {"edit_task", "add_task", "remove_task", "reschedule_task", "generate_plan"}

    try:
        response = chat.send_message(
            "Please analyze and optimize my pet care schedule. "
            "Start by calling get_schedule_state to understand the current situation."
        )

        while iteration_count < MAX_ITERATIONS:
            # Collect function calls from this response
            function_calls = response.function_calls or []

            if not function_calls:
                # No more tool calls — extract final text
                if response.text:
                    final_summary = response.text
                break

            has_mutation = any(fc.name in mutation_tools for fc in function_calls)

            # Execute all function calls and collect responses
            tool_response_parts = []
            for fc in function_calls:
                result_str = _dispatch(
                    name=fc.name,
                    args=dict(fc.args),
                    scheduler=scheduler,
                    action_log=action_log,
                    retrieved_titles=retrieved_titles,
                    seen_titles=seen_titles,
                    removal_count_ref=removal_count_ref,
                )
                tool_response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=fc.id,
                            name=fc.name,
                            response={"result": result_str},
                        )
                    )
                )

            response = chat.send_message(tool_response_parts)

            if has_mutation:
                iteration_count += 1

    except Exception as exc:
        scheduler.generate_plan()
        return AgentResult(
            success=False,
            summary="",
            action_log=action_log,
            retrieved_chunk_titles=retrieved_titles,
            before_conflict_count=len(before_conflicts),
            after_conflict_count=len(scheduler.detect_conflicts()),
            before_skipped_count=len(before_skipped),
            after_skipped_count=0,
            iterations_used=iteration_count,
            error=str(exc),
        )

    # Final plan refresh
    scheduler.generate_plan()
    after_conflicts = scheduler.detect_conflicts()
    all_tasks_after = scheduler.owner.get_all_tasks()
    sched_keys_after = {(t.pet_name, t.name) for t, _ in scheduler.plan}
    after_skipped = [
        t for t in all_tasks_after
        if (t.pet_name, t.name) not in sched_keys_after and not t.is_completed
    ]

    return AgentResult(
        success=True,
        summary=final_summary,
        action_log=action_log,
        retrieved_chunk_titles=retrieved_titles,
        before_conflict_count=len(before_conflicts),
        after_conflict_count=len(after_conflicts),
        before_skipped_count=len(before_skipped),
        after_skipped_count=len(after_skipped),
        iterations_used=iteration_count,
    )
