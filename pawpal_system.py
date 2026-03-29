from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Pet:
    name: str
    age: int
    breed: str
    species: str
    activity_level: str
    health_history: list[str] = field(default_factory=list)
    medication_times: list[str] = field(default_factory=list)

    def get_info(self) -> dict:
        pass

    def get_health_needs(self) -> list[str]:
        pass


@dataclass
class Task:
    name: str
    category: str
    duration: int          # in minutes
    priority: int          # higher = more important
    description: str = ""
    scheduled_time: str = ""
    frequency: str = "daily"
    must_occur_at: str = ""

    def get_task_info(self) -> dict:
        pass


@dataclass
class Scheduler:
    owner: Owner
    pet: Pet
    tasks: list[Task] = field(default_factory=list)
    plan: list[tuple[Task, str]] = field(default_factory=list)  # (task, time_slot)

    def add_task(self, _task: Task) -> None:
        pass

    def edit_task(self, _task_name: str, _changes: dict) -> None:
        pass

    def generate_plan(self) -> list[tuple[Task, str]]:
        pass

    def explain_reasoning(self) -> str:
        pass

    def get_owner_info(self) -> dict:
        pass

    def get_pet_info(self) -> dict:
        pass


@dataclass
class Owner:
    name: str
    contact_info: str
    time_available: int    # in minutes per day
    pet: Pet
    preferences: dict = field(default_factory=dict)

    def add_task(self, scheduler: Scheduler, task: Task) -> None:
        pass

    def edit_task(self, scheduler: Scheduler, task_name: str, changes: dict) -> None:
        pass

    def view_plan(self, scheduler: Scheduler) -> list[tuple[Task, str]]:
        pass

    def get_pet_info(self) -> dict:
        pass

    def get_task_info(self, scheduler: Scheduler) -> list[Task]:
        pass
