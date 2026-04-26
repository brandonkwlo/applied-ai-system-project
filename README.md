# PawPal+

An AI Pet Care Planning Streamlit app that takes care of planning the day for your pet. It also includes a chatbot to search that caters to the specified healthcare for the pet based on its age, species, health records, etc.

Loom Presentation Link [here](https://www.loom.com/share/8d0d0c5253794399ac75ef62a092622b)

<a href="screenshot.png" target="_blank"><img src='/assets/screenshot.png' title='PawPal App' width='' alt='PawPal App' class='center-block' /></a>

# Original Design

**PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet. The app generates a daily plan with pet care tasks that meet the constraints such as time availability, priority and owner preference.

# Architecture Overview

PawPal+'s AI Optimizer is a RAG-augmented agentic system layered on top of the existing pet scheduling app without touching its core logic.

<a href="Pet Care Task Optimization-2026-04-24-011837.png" target="_blank"><img src='/assets/Pet Care Task Optimization-2026-04-24-011837.png' title='PawPal App' width='' alt='PawPal App' class='center-block' /></a>

For a full breakdown of how the system works, its data sources, evaluation results, and limitations, see [MODEL_CARD.md](MODEL_CARD.md).

# Setup

1. Get a Free Groq API Key

- Go to console.groq.com and sign in
- Click API Keys → Create API Key
- Copy the key — you'll need it in Step 4

2. Install Python and uv
   This project uses Python 3.12+ and the uv package manager.

If you don't have uv installed:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Install Dependencies

```
uv add groq scikit-learn python-dotenv
```

groq — official Groq Python SDK (uses llama-3.3-70b-versatile)

scikit-learn — powers TF-IDF retrieval for the knowledge base

python-dotenv — loads your API key from the .env file

4. Set Your API Key

```
echo "GROQ_API_KEY=your-key-here" > .env
```

Replace your-key-here with the key from Step 1. This file is gitignored and never committed.

5. Run the App

```
uv run streamlit run app.py
```

Your browser opens at http://localhost:8501.

6. Try the AI Optimizer

- Add a pet — name, species, breed, age, activity level, health notes (e.g. Arthritis)
- Add tasks — pin two tasks to the same time (e.g. both at 08:00 AM) to create a conflict
- Generate Schedule — see the initial plan and flagged conflicts
- Run AI Optimizer — wait ~10–20 seconds for the agent loop
- Review before/after metrics, the action log, and which knowledge articles were used

7. Run the Tests

```
uv run pytest tests/test_pawpal.py -v
```

All 17 existing tests should pass — the AI features don't touch core scheduling logic.

# Sample Interactions

## Interaction 1 — Resolving a Scheduling Conflict for an Arthritic Dog

User setup:

- Pet: Buddy, Golden Retriever, age 8, activity level: low, health notes: "Arthritis"
- Tasks: "Morning Walk" pinned at 08:00 AM (30 min) and "Joint Supplement" pinned at 08:00 AM (10 min)
- User clicks Run AI Optimizer

<a href="interaction1.png" target="_blank"><img src='/assets/interaction1.png' title='PawPal App' width='' alt='PawPal App' class='center-block' /></a>

## Interaction 2 — Adding Missing Enrichment for an Anxious Indoor Cat

User setup:

- Pet: Luna, Cat, age 3, activity level: high, health notes: "Indoor only, stress-related over-grooming"
- Tasks: "Morning Feeding" (flexible), "Evening Feeding" (flexible), "Vet Medication" at 07:00 AM

<a href="interaction2.png" target="_blank"><img src='/assets/interaction2.png' title='PawPal App' width='' alt='PawPal App' class='center-block' /></a>

## Interaction 3 — Prioritizing Within a Tight Time Budget

User setup:

- Owner: 90 minutes available
- Pet: Max, Dog, age 5, on daily medication
- Tasks: "Medication" priority 5 at 08:00 AM (5 min), "Morning Walk" priority 4 (45 min), "Grooming" priority 2 (30 min), "Trick Training" priority 1 (30 min), "Nail Trim" priority 2 (20 min)
- Total task time: 130 min — exceeds 90 min budget

<a href="interaction3.png" target="_blank"><img src='/assets/interaction3.png' title='PawPal App' width='' alt='PawPal App' class='center-block' /></a>

# Design Decisions

## Why Groq instead of a paid API

Groq's free tier makes the project accessible to anyone with an account. For a scheduling assistant that runs a handful of tool calls per session, the free tier is more than sufficient. The trade-off is vendor lock-in to Groq's hosted inference, but the OpenAI-compatible API makes migration to another provider straightforward.

## Why TF-IDF instead of a vector database

A production RAG system would use embeddings and a vector store like ChromaDB or Pinecone. For this project, TF-IDF via scikit-learn fits in one file, requires no external service, and is fast enough for a 39-chunk corpus. The trade-off is lower semantic recall — TF-IDF matches on words, not meaning, so a query like "my dog can't move well" won't retrieve "arthritis" chunks as reliably as embeddings would. The tag-overlap bonus compensates for this with short queries.

## Why RAG lives inside the agent as a tool, not as a separate Q&A panel

Separating them into two UI features would have the agent making decisions based purely on its training data while the user gets knowledge in a separate panel they'd have to manually act on. Wiring retrieval directly into the agent's tool set means the agent cites knowledge when it makes changes — the log shows exactly which articles informed each decision, making the system more transparent and trustworthy.

## Why mutations happen in-place on session state objects

Streamlit re-runs the entire script on every interaction. Copying the owner/scheduler, modifying the copy, and writing it back would require careful state synchronization. Since owner and scheduler are already stored in st.session_state as object references, the agent's tool executors can mutate them directly — the updated schedule is automatically reflected in the UI on the next render with no extra bookkeeping.

## Why Python-level safety guards instead of relying only on the prompt

Prompt instructions can be ignored or misinterpreted — especially in multi-step tool calling where the model's attention is split across a long context. Hard-coded checks in the tool executor functions (e.g., refusing to delete the last medication task) are unconditional and cannot be bypassed by any model behavior. The prompt is a first line of defense; the Python code is the guarantee.

# What this project says about me as an AI engineer

This project demonstrates my ability to design AI systems that are reliable by construction, not just by luck. Rather than treating AI as a black box that generates code to paste in, I made deliberate architectural decisions — separating the retrieval layer from the agent, enforcing safety constraints in Python rather than trusting the prompt alone, and building an evaluation harness that measures behavior on predefined scenarios. I also learned to evaluate AI assistance critically: when it suggested a deprecated SDK, I caught it, investigated the root cause, and updated the system. That combination — knowing when to trust AI-generated output and when to question it — is what I take away from this project as an AI engineer.
