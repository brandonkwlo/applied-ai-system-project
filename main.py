from pawpal_system import Owner, Pet, Task, Scheduler


# --- Pets ---
buddy = Pet(
    name="Buddy",
    age=4,
    breed="Golden Retriever",
    species="Dog",
    activity_level="high",
    health_history=["Hip dysplasia (mild)"],
    medication_times=["08:00 AM"],
)

luna = Pet(
    name="Luna",
    age=2,
    breed="Domestic Shorthair",
    species="Cat",
    activity_level="medium",
)

# --- Owner ---
alex = Owner(
    name="Alex",
    contact_info="alex@email.com",
    time_available=180,  # 3 hours
    pets=[buddy, luna],
)

# --- Scheduler ---
scheduler = Scheduler(owner=alex)
alex.scheduler = scheduler

# --- Tasks for Buddy ---
alex.add_task("Buddy", Task(
    name="Morning Walk",
    category="walk",
    duration=30,
    priority=3,
    description="30-minute neighborhood walk",
    must_occur_at="07:00 AM",
))

alex.add_task("Buddy", Task(
    name="Hip Medication",
    category="meds",
    duration=5,
    priority=5,
    description="Daily joint supplement with food",
    must_occur_at="08:00 AM",
))

alex.add_task("Buddy", Task(
    name="Feeding",
    category="feeding",
    duration=10,
    priority=4,
    description="Morning kibble",
))

# --- Tasks for Luna ---
alex.add_task("Luna", Task(
    name="Feeding",
    category="feeding",
    duration=5,
    priority=4,
    description="Wet food serving",
))

alex.add_task("Luna", Task(
    name="Enrichment Play",
    category="enrichment",
    duration=20,
    priority=2,
    description="Feather wand and puzzle toy",
))

# --- Out-of-order tasks to test sorting and filtering ---
alex.add_task("Luna", Task(
    name="Evening Grooming",
    category="grooming",
    duration=15,
    priority=3,
    description="Brush coat",
    must_occur_at="06:00 PM",
))

alex.add_task("Buddy", Task(
    name="Afternoon Walk",
    category="walk",
    duration=20,
    priority=2,
    description="Short afternoon stroll",
    must_occur_at="03:00 PM",
))

alex.add_task("Buddy", Task(
    name="Teeth Brushing",
    category="grooming",
    duration=10,
    priority=1,
    description="Weekly dental care",
    must_occur_at="09:00 AM",
))

# --- Intentional conflict: two tasks at the same time ---
alex.add_task("Luna", Task(
    name="Vet Check-In",
    category="other",
    duration=20,
    priority=5,
    description="Quick morning vet call",
    must_occur_at="07:00 AM",   # same time as Buddy's Morning Walk
))

# Mark one task complete to test completion filter
buddy.tasks[0].mark_complete()  # Morning Walk -> completed

# --- Generate and print plan ---
scheduler.generate_plan()

print("=" * 40)
print("        Today's Schedule")
print("=" * 40)
print(scheduler.explain_reasoning())
print("=" * 40)

# --- Conflict detection ---
print("\n--- detect_conflicts() ---")
conflicts = scheduler.detect_conflicts()
if conflicts:
    for warning in conflicts:
        print(f"  WARNING: {warning}")
else:
    print("  No conflicts detected.")

# --- Test sort_by_time ---
print("\n--- sort_by_time() ---")
for task in scheduler.sort_by_time():
    print(f"  {task.scheduled_time or 'unscheduled':12}  {task.name:20} ({task.pet_name})")

# --- Test filter_tasks ---
print("\n--- filter_tasks(pet_name='Buddy') ---")
for task in scheduler.filter_tasks(pet_name="Buddy"):
    print(f"  {task.name:20} completed={task.is_completed}")

print("\n--- filter_tasks(completed=False) ---")
for task in scheduler.filter_tasks(completed=False):
    print(f"  {task.name:20} ({task.pet_name})")

print("\n--- filter_tasks(completed=True) ---")
for task in scheduler.filter_tasks(completed=True):
    print(f"  {task.name:20} ({task.pet_name})")
