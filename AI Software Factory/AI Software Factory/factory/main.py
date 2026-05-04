import os
import sys
import io

# ── Force UTF-8 for Windows terminal ────────────────────────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from dotenv import load_dotenv

# ── Load .env before anything else ───────────────────────────────────────────
load_dotenv()

# ── Validate OpenRouter key ──────────────────────────────────────────────────
api_key = os.environ.get('OPENROUTER_API_KEY')
if not api_key:
    raise ValueError("Bhai, OPENROUTER_API_KEY terminal ya .env mein nahi mili!")

# ── Debug line ───────────────────────────────────────────────────────────────
print(f"DEBUG: Serper Key starts with: {os.environ.get('SERPER_API_KEY')[:4]}")

# ── Imports ──────────────────────────────────────────────────────────────────
from typing import Optional
from pathlib import Path

from agno.agent import Agent
from agno.team.team import Team
from agno.tools.serper import SerperTools
from agno.tools.file import FileTools
from agno.tools.python import PythonTools
from agno.models.openai import OpenAIChat

# ── Shared LLM (DeepSeek V4 Flash via OpenRouter) ────────────────────────────
deepseek_model = OpenAIChat(
    id="deepseek/deepseek-v4-flash",
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)

# ── Tools ────────────────────────────────────────────────────────────────────
search_tool = SerperTools(api_key=os.environ.get('SERPER_API_KEY'))
file_tools = FileTools()
python_tools = PythonTools()

# ── Agents ───────────────────────────────────────────────────────────────────
manager = Agent(
    name="Manager",
    model=deepseek_model,
    tools=[search_tool, file_tools, python_tools],
    description="You are a senior engineering manager. You decompose user requests into clear subtasks and delegate them to the Worker agent. You review the Worker's output and decide if it is complete or needs revision.",
    markdown=True,
)

worker = Agent(
    name="Worker",
    model=deepseek_model,
    tools=[search_tool, file_tools, python_tools],
    description="You are a senior software engineer. You implement features, write code, create files, and run tests. You report your progress back to the Manager.",
    markdown=True,
)

critic = Agent(
    name="Critic",
    model=deepseek_model,
    tools=[search_tool, file_tools, python_tools],
    description="You are a senior code reviewer. You inspect the Worker's output for bugs, security issues, and best-practice violations. You provide a structured review report.",
    markdown=True,
)

# ── Team ─────────────────────────────────────────────────────────────────────
software_factory = Team(
    name="Software Factory",
    mode="route",
    members=[manager, worker, critic],
    model=deepseek_model,
    tools=[search_tool, file_tools, python_tools],
    markdown=True,
    description="You are a software factory that builds full-stack applications. You plan, implement, and review code before delivering the final product.",
)

# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Software Factory ready. Type 'exit' or 'quit' to stop.\n")

    while True:
        user_input = input("\n[YOU]: ")
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        software_factory.print_response(user_input, stream=True)
