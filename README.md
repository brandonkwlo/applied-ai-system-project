# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Smarter Scheduling

PawPal+ includes three scheduling utilities to help owners manage their daily plan:

- Sort by time — orders all tasks chronologically, correctly handling AM/PM across both pets
- Filter tasks — narrow the task list by pet name, completion status, or both
- Conflict detection — automatically warns when two tasks are scheduled at the same time, grouped by time slot into a single readable message

## Testing PawPal+

Tests are located in tests/test_pawpal.py and cover the following behaviors:

- Task completion status and pet task count
- Schedule generation across multiple pets
- Chronological sort order with correct AM/PM handling (including 12:00 AM/PM edge cases)
- Daily recurrence creating a next-day occurrence via timedelta
- Conflict detection flagging duplicate scheduled times
- Unscheduled recurring tasks being ignored by conflict detection

To run all tests:

```
uv run pytest
```

Confidence Level: 5/5 Stars (All tests passed!)

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.
