from datetime import date, timedelta
from pawpal_system import Owner, Pet, Task, Scheduler


def make_scheduler(*pets, time_available=180):
    """Helper: build an Owner + Scheduler wired together with the given pets."""
    owner = Owner(name="Alex", contact_info="alex@email.com", time_available=time_available, pets=list(pets))
    scheduler = Scheduler(owner=owner)
    owner.scheduler = scheduler
    return owner, scheduler


def test_mark_complete_changes_status():
    task = Task(name="Morning Walk", category="walk", duration=30, priority=3)
    assert task.is_completed is False
    task.mark_complete()
    assert task.is_completed is True


def test_add_task_increases_pet_task_count():
    pet = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    assert len(pet.tasks) == 0
    pet.add_task(Task(name="Feeding", category="feeding", duration=10, priority=4))
    assert len(pet.tasks) == 1


def test_schedule_generation_with_two_pets():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    luna = Pet(name="Luna", age=2, breed="Domestic Shorthair", species="Cat", activity_level="medium")

    alex = Owner(name="Alex", contact_info="alex@email.com", time_available=180, pets=[buddy, luna])
    scheduler = Scheduler(owner=alex)
    alex.scheduler = scheduler

    alex.add_task("Buddy", Task(
        name="Morning Walk", category="walk", duration=30, priority=3, must_occur_at="07:00 AM"
    ))
    alex.add_task("Buddy", Task(
        name="Hip Medication", category="meds", duration=5, priority=5, must_occur_at="08:00 AM"
    ))
    alex.add_task("Luna", Task(
        name="Enrichment Play", category="enrichment", duration=20, priority=2
    ))

    plan = scheduler.generate_plan()

    print("\n" + "=" * 40)
    print("        Today's Schedule")
    print("=" * 40)
    print(scheduler.explain_reasoning())
    print("=" * 40)

    assert len(plan) == 3
    scheduled_names = [task.name for task, _ in plan]
    assert "Morning Walk" in scheduled_names
    assert "Hip Medication" in scheduled_names
    assert "Enrichment Play" in scheduled_names


# --- Sorting correctness ---

def test_sort_by_time_returns_chronological_order():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    owner, scheduler = make_scheduler(buddy)

    owner.add_task("Buddy", Task(name="Afternoon Walk", category="walk", duration=20, priority=2, must_occur_at="03:00 PM"))
    owner.add_task("Buddy", Task(name="Hip Medication", category="meds", duration=5, priority=5, must_occur_at="08:00 AM"))
    owner.add_task("Buddy", Task(name="Morning Walk", category="walk", duration=30, priority=3, must_occur_at="07:00 AM"))
    owner.add_task("Buddy", Task(name="Evening Feeding", category="feeding", duration=10, priority=4, must_occur_at="06:00 PM"))

    scheduler.generate_plan()
    sorted_tasks = scheduler.sort_by_time()
    times = [t.scheduled_time for t in sorted_tasks]

    assert times == sorted(times, key=scheduler._time_to_minutes)


# --- Recurrence logic ---

def test_daily_task_creates_next_day_occurrence():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    owner, scheduler = make_scheduler(buddy)

    today = date.today()
    owner.add_task("Buddy", Task(name="Morning Walk", category="walk", duration=30, priority=3, frequency="daily"))

    next_task = scheduler.complete_task("Buddy", "Morning Walk")

    assert next_task is not None
    assert next_task.due_date == today + timedelta(days=1)
    assert next_task.is_completed is False
    assert len(buddy.tasks) == 2  # original + new occurrence


# --- Conflict detection ---

def test_detect_conflicts_flags_duplicate_times():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    luna = Pet(name="Luna", age=2, breed="Domestic Shorthair", species="Cat", activity_level="medium")
    owner, scheduler = make_scheduler(buddy, luna)

    owner.add_task("Buddy", Task(name="Morning Walk", category="walk", duration=30, priority=3, must_occur_at="07:00 AM"))
    owner.add_task("Luna", Task(name="Vet Check-In", category="other", duration=20, priority=5, must_occur_at="07:00 AM"))

    scheduler.generate_plan()
    conflicts = scheduler.detect_conflicts()

    assert len(conflicts) == 1
    assert "07:00 AM" in conflicts[0]
    assert "Morning Walk" in conflicts[0]
    assert "Vet Check-In" in conflicts[0]


# --- 12:00 AM / 12:00 PM edge cases ---

def test_time_to_minutes_noon():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    _, scheduler = make_scheduler(buddy)
    # 12:00 PM (noon) should be 720 minutes from midnight, not 0
    assert scheduler._time_to_minutes("12:00 PM") == 720

def test_time_to_minutes_midnight():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    _, scheduler = make_scheduler(buddy)
    # 12:00 AM (midnight) should be 0 minutes from midnight, not 720
    assert scheduler._time_to_minutes("12:00 AM") == 0

def test_noon_sorts_after_morning():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    owner, scheduler = make_scheduler(buddy)

    owner.add_task("Buddy", Task(name="Noon Feeding", category="feeding", duration=10, priority=4, must_occur_at="12:00 PM"))
    owner.add_task("Buddy", Task(name="Morning Walk", category="walk", duration=30, priority=3, must_occur_at="08:00 AM"))

    scheduler.generate_plan()
    sorted_tasks = scheduler.sort_by_time()
    names = [t.name for t in sorted_tasks]

    assert names.index("Morning Walk") < names.index("Noon Feeding")


# --- Completing the same task twice ---

def test_complete_task_twice_does_not_create_duplicate():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    owner, scheduler = make_scheduler(buddy)

    owner.add_task("Buddy", Task(name="Morning Walk", category="walk", duration=30, priority=3, frequency="once"))

    scheduler.complete_task("Buddy", "Morning Walk")   # completes the task, no next occurrence (frequency="once")
    result = scheduler.complete_task("Buddy", "Morning Walk")  # already completed — guard should skip it

    assert result is None  # second call returns None, nothing to complete
    assert len(buddy.tasks) == 1  # no new task added
    assert buddy.tasks[0].is_completed is True


# --- Recurring task ignored by conflict detection ---

def test_detect_conflicts_ignores_unscheduled_recurring_task():
    buddy = Pet(name="Buddy", age=4, breed="Golden Retriever", species="Dog", activity_level="high")
    owner, scheduler = make_scheduler(buddy)

    owner.add_task("Buddy", Task(name="Morning Walk", category="walk", duration=30, priority=3,
                                 must_occur_at="07:00 AM", frequency="daily"))

    scheduler.generate_plan()
    scheduler.complete_task("Buddy", "Morning Walk")  # adds next occurrence with no scheduled_time

    conflicts = scheduler.detect_conflicts()
    assert len(conflicts) == 0  # new unscheduled occurrence must not trigger a false conflict
