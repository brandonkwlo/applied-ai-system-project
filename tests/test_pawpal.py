from pawpal_system import Owner, Pet, Task, Scheduler


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
