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

# --- Generate and print plan ---
scheduler.generate_plan()

print("=" * 40)
print("        Today's Schedule")
print("=" * 40)
print(scheduler.explain_reasoning())
print("=" * 40)
