import streamlit as st
from pawpal_system import Task, Pet, Owner, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# --- Session state initialization ---
# Guard clauses ensure objects are created once per session, not on every rerun.
if "owner" not in st.session_state:
    st.session_state.owner = Owner(name="", contact_info="", time_available=120)

if "scheduler" not in st.session_state:
    st.session_state.scheduler = Scheduler(owner=st.session_state.owner)
    st.session_state.owner.scheduler = st.session_state.scheduler

# Convenience references — use these throughout the rest of the app
owner = st.session_state.owner
scheduler = st.session_state.scheduler

st.title("🐾 PawPal+")

# --- Owner Info ---
st.subheader("Owner Info")
col1, col2, col3 = st.columns(3)
with col1:
    owner.name = st.text_input("Your name", value=owner.name)
with col2:
    owner.contact_info = st.text_input("Contact info", value=owner.contact_info)
with col3:
    owner.time_available = st.number_input(
        "Time available today (min)", min_value=10, max_value=480, value=owner.time_available
    )

st.divider()

# --- Add a Pet ---
st.subheader("Add a Pet")
with st.form("add_pet_form", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        pet_name = st.text_input("Pet name")
        species = st.selectbox("Species", ["Dog", "Cat", "Bird", "Other"])
    with col2:
        breed = st.text_input("Breed")
        age = st.number_input("Age", min_value=0, max_value=30, value=1)
    with col3:
        activity_level = st.selectbox("Activity level", ["low", "medium", "high"])
        health_history = st.text_input("Health notes (comma-separated)")

    submitted = st.form_submit_button("Add Pet")
    if submitted and pet_name:
        health_list = [h.strip() for h in health_history.split(",") if h.strip()]
        new_pet = Pet(
            name=pet_name,
            age=age,
            breed=breed,
            species=species,
            activity_level=activity_level,
            health_history=health_list,
        )
        owner.add_pet(new_pet)
        st.success(f"Added {pet_name}!")

if owner.pets:
    st.write("**Your pets:**")
    for pet in owner.pets:
        st.markdown(f"- **{pet.name}** ({pet.species}, {pet.breed}, age {pet.age}) — activity: {pet.activity_level}")
else:
    st.info("No pets added yet.")

st.divider()

# --- Add a Task ---
st.subheader("Add a Task")

if not owner.pets:
    st.warning("Add a pet first before scheduling tasks.")
else:
    with st.form("add_task_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            task_pet = st.selectbox("For which pet?", [p.name for p in owner.pets])
            task_name = st.text_input("Task name", value="Morning walk")
            category = st.selectbox("Category", ["walk", "feeding", "meds", "grooming", "enrichment", "other"])
        with col2:
            duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
            priority = st.slider("Priority (1 = low, 5 = high)", min_value=1, max_value=5, value=3)
            must_occur_at = st.text_input("Fixed time (e.g. 08:00 AM)", value="")

        description = st.text_input("Description (optional)")
        task_submitted = st.form_submit_button("Add Task")

        if task_submitted and task_name:
            new_task = Task(
                name=task_name,
                category=category,
                duration=int(duration),
                priority=priority,
                description=description,
                must_occur_at=must_occur_at.strip(),
            )
            owner.add_task(task_pet, new_task)
            st.success(f"Added '{task_name}' to {task_pet}!")

    if owner.pets:
        all_tasks = owner.get_all_tasks()
        if all_tasks:
            st.write("**Current tasks:**")
            st.table([
                {
                    "Pet": t.pet_name,
                    "Task": t.name,
                    "Category": t.category,
                    "Duration (min)": t.duration,
                    "Priority": t.priority,
                    "Fixed time": t.must_occur_at or "flexible",
                }
                for t in all_tasks
            ])
        else:
            st.info("No tasks added yet.")

st.divider()

# --- Generate Schedule ---
st.subheader("Generate Schedule")

if st.button("Generate schedule"):
    if not owner.pets or not owner.get_all_tasks():
        st.warning("Add at least one pet and one task first.")
    else:
        scheduler.generate_plan()
        st.success("Schedule generated!")
        st.text(scheduler.explain_reasoning())
