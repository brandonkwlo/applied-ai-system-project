from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    name: str
    category: str
    duration: int           # in minutes
    priority: int           # higher = more important
    pet_name: str = ""      # which pet this task belongs to
    description: str = ""
    scheduled_time: str = ""
    frequency: str = "daily"
    must_occur_at: str = ""  # e.g. "08:00 AM", empty means flexible
    is_completed: bool = False

    def get_task_info(self) -> dict:
        """Return all task attributes as a dictionary."""
        return {
            "name": self.name,
            "category": self.category,
            "duration": self.duration,
            "priority": self.priority,
            "pet_name": self.pet_name,
            "description": self.description,
            "scheduled_time": self.scheduled_time,
            "frequency": self.frequency,
            "must_occur_at": self.must_occur_at,
            "is_completed": self.is_completed,
        }

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.is_completed = True


@dataclass
class Pet:
    name: str
    age: int
    breed: str
    species: str
    activity_level: str
    health_history: list[str] = field(default_factory=list)
    medication_times: list[str] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)

    def get_info(self) -> dict:
        """Return pet profile attributes as a dictionary."""
        return {
            "name": self.name,
            "age": self.age,
            "breed": self.breed,
            "species": self.species,
            "activity_level": self.activity_level,
            "health_history": self.health_history,
            "medication_times": self.medication_times,
        }

    def get_health_needs(self) -> list[str]:
        """Return combined health history and medication schedule as a list."""
        needs = list(self.health_history)
        if self.medication_times:
            needs.append(f"Medications at: {', '.join(self.medication_times)}")
        return needs

    def add_task(self, task: Task) -> None:
        """Add a task to this pet and stamp it with the pet's name."""
        task.pet_name = self.name
        self.tasks.append(task)

    def remove_task(self, task_name: str) -> None:
        """Remove a task from this pet by name."""
        self.tasks = [t for t in self.tasks if t.name != task_name]

    def get_tasks(self) -> list[Task]:
        """Return a copy of this pet's task list."""
        return list(self.tasks)


@dataclass
class Owner:
    name: str
    contact_info: str
    time_available: int     # in minutes per day
    pets: list[Pet] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)
    # Linked after Scheduler is created: owner.scheduler = scheduler
    scheduler: Optional[Scheduler] = field(default=None)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner's list of pets."""
        self.pets.append(pet)

    def remove_pet(self, pet_name: str) -> None:
        """Remove a pet from this owner's list by name."""
        self.pets = [p for p in self.pets if p.name != pet_name]

    def get_pet(self, pet_name: str) -> Optional[Pet]:
        """Return the Pet object matching the given name, or None if not found."""
        for pet in self.pets:
            if pet.name == pet_name:
                return pet
        return None

    def add_task(self, pet_name: str, task: Task) -> None:
        """Add a task to the specified pet by name."""
        pet = self.get_pet(pet_name)
        if pet:
            pet.add_task(task)

    def edit_task(self, pet_name: str, task_name: str, changes: dict) -> None:
        """Update fields of a named task belonging to the specified pet."""
        pet = self.get_pet(pet_name)
        if not pet:
            return
        for task in pet.tasks:
            if task.name == task_name:
                for key, value in changes.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                break

    def get_all_tasks(self) -> list[Task]:
        """Return a flat list of all tasks across every pet this owner manages."""
        all_tasks = []
        for pet in self.pets:
            all_tasks.extend(pet.get_tasks())
        return all_tasks

    def view_plan(self) -> list[tuple[Task, str]]:
        """Return the current scheduled plan from the linked scheduler."""
        if self.scheduler:
            return self.scheduler.plan
        return []

    def get_task_info(self) -> list[Task]:
        """Return all tasks across all pets owned by this owner."""
        return self.get_all_tasks()


@dataclass
class Scheduler:
    owner: Owner
    plan: list[tuple[Task, str]] = field(default_factory=list)  # (task, time_slot)

    def get_all_tasks(self) -> list[Task]:
        """Retrieve all tasks across every pet the owner manages."""
        return self.owner.get_all_tasks()

    def add_task(self, pet_name: str, task: Task) -> None:
        """Delegate task addition to the owner for the specified pet."""
        self.owner.add_task(pet_name, task)

    def edit_task(self, pet_name: str, task_name: str, changes: dict) -> None:
        """Delegate task editing to the owner for the specified pet."""
        self.owner.edit_task(pet_name, task_name, changes)

    def generate_plan(self) -> list[tuple[Task, str]]:
        """
        Schedule tasks within owner's available time.
        Fixed tasks (must_occur_at) are placed first at their required time.
        Remaining flexible tasks are sorted by priority and filled sequentially.
        Tasks that exceed remaining time are skipped.
        """
        tasks = self.get_all_tasks()

        fixed = sorted(
            [t for t in tasks if t.must_occur_at],
            key=lambda t: t.must_occur_at
        )
        flexible = sorted(
            [t for t in tasks if not t.must_occur_at],
            key=lambda t: t.priority,
            reverse=True
        )

        remaining = self.owner.time_available
        scheduled: list[tuple[Task, str]] = []

        for task in fixed:
            if task.duration <= remaining:
                scheduled.append((task, task.must_occur_at))
                task.scheduled_time = task.must_occur_at
                remaining -= task.duration

        current_minute = 8 * 60  # flexible tasks begin at 8:00 AM
        for task in flexible:
            if task.duration > remaining:
                continue
            time_slot = self._minutes_to_time(current_minute)
            scheduled.append((task, time_slot))
            task.scheduled_time = time_slot
            current_minute += task.duration
            remaining -= task.duration

        self.plan = scheduled
        return self.plan

    def explain_reasoning(self) -> str:
        """Return a human-readable explanation of the generated plan."""
        if not self.plan:
            return "No plan generated yet. Call generate_plan() first."

        total_scheduled = sum(t.duration for t, _ in self.plan)
        lines = [
            f"Plan for {self.owner.name} | "
            f"{total_scheduled} of {self.owner.time_available} min scheduled "
            f"across {len(self.owner.pets)} pet(s).",
            "",
            "Schedule:"
        ]
        for task, time_slot in self.plan:
            status = "fixed" if task.must_occur_at else f"priority {task.priority}"
            lines.append(
                f"  {time_slot}  {task.name} ({task.pet_name}) "
                f"— {task.duration} min [{status}]"
            )

        skipped = [t for t in self.get_all_tasks() if not t.scheduled_time]
        if skipped:
            lines.append("")
            lines.append("Skipped (insufficient time):")
            for task in skipped:
                lines.append(f"  - {task.name} ({task.pet_name}, {task.duration} min)")

        return "\n".join(lines)

    def _minutes_to_time(self, minutes: int) -> str:
        """Convert an integer minute offset from midnight to a 12-hour time string."""
        hours = (minutes // 60) % 24
        mins = minutes % 60
        period = "AM" if hours < 12 else "PM"
        display_hour = hours % 12 or 12
        return f"{display_hour:02d}:{mins:02d} {period}"
