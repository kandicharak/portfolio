import os
import sys
from dotenv import load_dotenv
from agno.agent import Agent
from agno.team.team import Team
from agno.tools.serper import SerperTools
from agno.tools.file import FileTools
from agno.tools.python import PythonTools
from agno.models.openai import OpenAIChat

# ── UTF-8 Safety ──────────────────────────────────────────────────────────────
# Force UTF-8 encoding for stdout/stderr to prevent UnicodeEncodeErrors
if sys.stdout.encoding is None or sys.stdout.encoding.upper() not in ("UTF-8", "UTF8"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding is None or sys.stderr.encoding.upper() not in ("UTF-8", "UTF8"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

# ── Models ────────────────────────────────────────────────────────────────────
# Hybrid: DeepSeek (cloud) for Architect/Critic, Qwen (local) for Worker
deepseek = OpenAIChat(
    id="deepseek/deepseek-v4-flash",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)
qwen_local = OpenAIChat(
    id="qwen/qwen3.5-9b",
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
)

# ── Architect Agent ───────────────────────────────────────────────────────────
# Senior Solutions Architect: designs architecture and creates master_plan.md
architect = Agent(
    name="Architect",
    model=deepseek,
    tools=[FileTools()],
    description=(
        "Senior Solutions Architect. Your ONLY job is to take the user's request, "
        "design a robust software architecture, and break it down into small, logical, "
        "sequential steps. Save this exact step-by-step breakdown into a file named "
        "master_plan.md. Do NOT write the actual application code."
    ),
    markdown=True,
    memory=True,
)

# ── Worker Agent ──────────────────────────────────────────────────────────────
# Implementer: reads master_plan.md, implements one step at a time, tests, and moves on
worker = Agent(
    name="Worker",
    model=qwen_local,
    tools=[FileTools(), PythonTools(), SerperTools()],
    description=(
        "You are the Implementer. Your job is to read master_plan.md. "
        "Pick the first uncompleted step, write the code, and MUST test it using "
        "PythonTools. Once the Critic approves, mark the step as [DONE] in "
        "master_plan.md and move to the next step."
    ),
    markdown=True,
    memory=True,
)

# ── Critic Agent ──────────────────────────────────────────────────────────────
# Gatekeeper: reviews Worker's implementation, rejects with fixes or approves
critic = Agent(
    name="Critic",
    model=deepseek,
    description=(
        "You are the Gatekeeper. Review the Worker's implementation for the current "
        "step. If it has bugs or fails tests, reject it with exact fixes. If it is "
        "perfect, give a strict 'APPROVED' so the Worker can move to the next step."
    ),
    markdown=True,
    memory=True,
)

# ── Team: Software Factory ────────────────────────────────────────────────────
# Strict Agile workflow: Architect plans → Worker implements → Critic approves
software_factory = Team(
    name="Software Factory",
    mode="route",
    members=[architect, worker, critic],
    model=deepseek,
    max_steps=40,  # Allow enough iterations for multi-step projects
    instructions=[
        # ── Phase 1: Planning ────────────────────────────────────────────────
        "You are the Manager of the Software Factory. Your job is to enforce a "
        "strict 3-phase Agile workflow. Follow these phases in order:",
        "",
        "PHASE 1 – PLANNING:",
        "  Instruct the Architect to analyze the user's request, design a robust "
        "software architecture, and break it down into small, logical, sequential "
        "steps. The Architect MUST save this breakdown as a numbered list in a file "
        "named master_plan.md using FileTools. The Architect must NOT write any "
        "application code.",
        "",
        "PHASE 2 – EXECUTION LOOP:",
        "  Repeat the following sub-steps until all steps in master_plan.md are completed:",
        "",
        "  STEP A – READ PLAN:",
        "    Instruct the Worker to read master_plan.md and identify the first "
        "    uncompleted step (a step NOT marked [DONE]).",
        "",
        "  STEP B – IMPLEMENT & TEST:",
        "    Instruct the Worker to implement ONLY that single step and write the "
        "    code to disk via FileTools. The Worker MUST then test the implementation "
        "    using PythonTools and capture the full output (stdout + stderr).",
        "",
        "  STEP C – CRITIC REVIEW:",
        "    Pass the implementation AND the test output to the Critic for review. "
        "    The Critic must check for bugs, logic errors, and test failures.",
        "",
        "  STEP D – FIX IF NEEDED:",
        "    If the Critic finds issues OR the test output shows errors, send the "
        "    Critic's feedback (with exact fixes) back to the Worker. The Worker MUST "
        "    apply the fixes and re-run tests. Repeat steps B → C → D until the Critic "
        "    gives a strict 'APPROVED'.",
        "",
        "  STEP E – MARK COMPLETE:",
        "    Once the Critic approves (✅), instruct the Worker to update master_plan.md "
        "    by marking the current step as [DONE] and then move to the next uncompleted step.",
        "",
        "PHASE 3 – COMPLETION:",
        "  Stop only when ALL steps in master_plan.md are marked [DONE] and verified. "
        "  Confirm the final project is complete.",
        "",
        # ── Autonomy Rules ──────────────────────────────────────────────────
        "AUTONOMY RULES:",
        "- NEVER ask the human for input. You have all the tools you need.",
        "- NEVER stop on the first error. Always route errors back to the Worker for fixes.",
        "- The Worker MUST use PythonTools to run code – do not rely on manual execution.",
        "- If a library is missing, instruct the Worker to install it via pip.",
        "- Keep iterating until all steps are done. max_steps=40 gives you room.",
    ],
    markdown=True,
)

# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    software_factory.print_response(
        "Build a simple python calculator and save to calc.py",
        stream=True,
    )
