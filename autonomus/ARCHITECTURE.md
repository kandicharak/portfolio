# Architecture Documentation

## System Overview

This document describes the architecture of the Autonomous Coding System, a multi-agent AI system designed to generate complete software projects from user ideas.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User Input Layer                          │
│              (Software Idea Description)                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Planning & Design Layer                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Architect Agent (DeepSeek Coder)         │   │
│  │  - Analyzes software requirements                     │   │
│  │  - Generates project architecture                     │   │
│  │  - Creates file structure plan                        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Code Generation Layer                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Developer Agent (Qwen 3.5)               │   │
│  │  - Generates code files based on architecture         │   │
│  │  - Creates project structure                          │   │
│  │  - Implements features                                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Output Layer                               │
│              Complete Generated Project                      │
└─────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. AgentManager (Core)
- **Location**: `agents.py`
- **Responsibility**: Orchestrates the multi-agent workflow
- **Agents Managed**:
  - Architect Agent: Generates project architecture and file structure
  - Developer Agent: Implements code based on architecture plan

### 2. ProjectGenerator (Core)
- **Location**: `main.py`
- **Responsibility**: Main entry point for autonomous coding process
- **Methods**:
  - `_setup_output_directory()`: Creates output directory for generated project
  - `_generate_architecture_plan()`: Calls Architect Agent via OpenRouter API
  - `_generate_code()`: Calls Developer Agent via LM Studio API
  - `generate_project()`: Main method that orchestrates the entire process

### 3. Configuration Layer
- **Location**: `core/config.py`
- **Responsibility**: Centralized configuration management
- **Features**:
  - Environment variable loading from `.env` file
  - Database path configuration (ChromaDB)
  - Logging configuration
  - Application settings (debug mode, allowed hosts)

### 4. Application Layer
- **Location**: `app.py`
- **Responsibility**: FastAPI application setup
- **Features**:
  - API endpoint definitions
  - Request/response handling
  - Integration with agent system

## Data Flow

1. **Input**: User provides software idea via CLI or API
2. **Planning**: Architect Agent analyzes requirements and generates architecture plan (JSON format)
3. **Generation**: Developer Agent reads architecture plan and generates code files
4. **Output**: Complete project structure saved to output directory

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Orchestration | CrewAI | Multi-agent workflow management |
| LLM (Planning) | DeepSeek Coder (via OpenRouter) | Architecture generation |
| LLM (Coding) | Qwen 3.5 (via LM Studio) | Code generation |
| Vector Store | ChromaDB | Knowledge storage |
| API Framework | FastAPI | RESTful API endpoints |
| Configuration | Python-dotenv | Environment variable management |

## File Structure

```
autonomus/
├── agents.py              # Multi-agent orchestration
├── main.py                # Main entry point
├── app.py                 # FastAPI application
├── core/
│   └── config.py          # Configuration management
├── .env                   # Environment variables
├── .env.example           # Environment template
├── ARCHITECTURE.md        # This file
├── MEMORY.md              # Agent memory documentation
└── TODO.md                # Task tracking
```

## API Endpoints

### POST `/generate`
- **Description**: Generate a complete project from a software idea
- **Request Body**:
  ```json
  {
    "software_idea": "string description of the software"
  }
  ```
- **Response**: Path to generated project directory

## Security Considerations

1. API keys are loaded from `.env` file (not hardcoded)
2. Environment variables support different environments (development, staging, production)
3. LangChain tracing enabled for debugging and monitoring
4. Allowed hosts configuration prevents CORS attacks in production

## Future Enhancements

- [ ] Add unit tests for agent interactions
- [ ] Implement error handling and retry logic
- [ ] Add project validation step before output
- [ ] Support multiple output formats (ZIP, Git repo)
- [ ] Add user feedback loop for code improvements
