# Autonomous Software Factory - Architecture

## Target & Goal
Build a fully autonomous software factory in `d:/alphabot` using CrewAI that can:
1. Accept a project name as input
2. Collaborate between agents to build complete projects
3. Save all code files directly without user intervention

## System Components

### 1. Manager Agent (bot_engine.py)
- **LLM**: Google Gemini API (`AIzaSyB2MFFLMEm5W-xfen5s9puCMsG9vXZykow`)
- **Role**: Orchestrates the crew, breaks down tasks, coordinates agents
- **Responsibilities**:
  - Parse project requirements
  - Generate task breakdown for Coder Agent
  - Monitor execution progress

### 2. Coder Agent
- **LLM**: LM Studio (`http://localhost:1234/v1`) with `qwen-2.5-7b` model
- **Tools**: 
  - `FileWriterTool` - Write files to disk
  - `DirectoryReadTool` - Read directory structure
- **Responsibilities**:
  - Generate code for all project files
  - Create HTML/CSS/JS files autonomously
  - Save files directly to project folder

## Project Structure
```
d:/alphabot/
├── .gitignore
├── ARCHITECTURE.md
├── MEMORY.md
├── TODO.md
├── bot_engine.py          # Main entry point with CrewAI setup
├── venv/                  # Python virtual environment
└── projects/              # Generated project outputs
    └── <project_name>/
        ├── index.html
        ├── style.css
        └── ...
```

## Execution Flow
1. User provides project name (e.g., "Professional Portfolio Website")
2. Manager Agent receives input and creates task plan
3. Coder Agent executes tasks using available tools
4. All files saved directly to `d:/alphabot/<project_name>/`
5. Process completes without user intervention

## Dependencies
- Python 3.12+
- crewai
- crewai[tools]
- langchain-google-genai
