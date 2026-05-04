# Memory Documentation

## Overview

This document describes the memory architecture of the Autonomous Coding System, including how agents store, retrieve, and utilize information throughout their workflow.

## Memory Types

### 1. Short-Term Memory (Context Window)
- **Purpose**: Immediate conversation context for each agent
- **Managed by**: CrewAI framework
- **Content**: Current task instructions, previous messages in the conversation
- **Limitations**: Bounded by LLM context window size

### 2. Long-Term Memory (Vector Store)
- **Purpose**: Persistent knowledge storage across sessions
- **Technology**: ChromaDB (local vector database)
- **Location**: Configurable via `core/config.py` (`CHROMA_DB_PATH`)
- **Content**:
  - Project specifications and requirements
  - Architecture decisions and rationale
  - Code patterns and best practices
  - User preferences and feedback

### 3. Task Memory (Workflow State)
- **Purpose**: Track progress through multi-step workflows
- **Managed by**: AgentManager in `agents.py`
- **Content**:
  - Current task status (pending, in-progress, completed)
  - Dependencies between tasks
  - Output artifacts from previous steps

## Memory Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Memory System                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌──────────────────────────────┐   │
│  │ Short-Term      │    │     Long-Term                │   │
│  │ Memory          │◄──►│     Memory (ChromaDB)        │   │
│  │ (Context)       │    │                              │   │
│  └─────────────────┘    └──────────────────────────────┘   │
│         ▲                        │                          │
│         │                        ▼                          │
│         │            ┌──────────────────────────────┐      │
│         └──────────► │     Task Memory              │      │
│                      │   (Workflow State)           │      │
│                      └──────────────────────────────┘      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Memory Operations

### Write Operations

#### 1. Storing Project Specifications
- **Trigger**: After Architect Agent completes analysis
- **Content**: Software requirements, features, constraints
- **Format**: JSON with structured fields
- **Purpose**: Enable Developer Agent to understand project scope

#### 2. Storing Architecture Decisions
- **Trigger**: When Architect Agent makes significant decisions
- **Content**: Decision rationale, alternatives considered, trade-offs
- **Format**: Markdown documentation + vector embedding
- **Purpose**: Maintain architectural consistency

#### 3. Storing Code Patterns
- **Trigger**: After Developer Agent generates code files
- **Content**: Reusable patterns, conventions, best practices
- **Format**: Code snippets with metadata
- **Purpose**: Improve future code generation quality

### Read Operations

#### 1. Retrieving Project Context
- **Trigger**: Before generating new code
- **Query**: "Project requirements and specifications"
- **Result**: Relevant project documents from vector store
- **Usage**: Inform code generation decisions

#### 2. Retrieving Architecture Information
- **Trigger**: When resolving ambiguities or conflicts
- **Query**: "Architecture decisions related to [topic]"
- **Result**: Architectural documentation and rationale
- **Usage**: Ensure consistency with design decisions

#### 3. Retrieving Task State
- **Trigger**: At workflow checkpoints
- **Query**: Current task status and dependencies
- **Result**: Workflow progress information
- **Usage**: Determine next action in pipeline

## Memory Management

### ChromaDB Configuration

```python
# Location: core/config.py
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
```

### Collection Schema

| Collection Name | Description | Embedding Model |
|-----------------|-------------|-----------------|
| `project_specs` | Project requirements and specifications | text-embedding-3-small |
| `architecture` | Architecture decisions and documentation | text-embedding-3-small |
| `code_patterns` | Reusable code patterns and conventions | text-embedding-3-small |

### Memory Cleanup

- **Periodic Cleanup**: Remove outdated or irrelevant entries
- **Session-Based**: Clear memory between independent projects
- **Size Limits**: Enforce maximum storage size to prevent bloat

## Agent-Specific Memory

### Architect Agent Memory

**Retrieves:**
- User's software idea and requirements
- Previous architecture decisions (for consistency)
- Best practices for the target technology stack

**Stores:**
- Complete architecture plan
- File structure design
- Technology choices and rationale

### Developer Agent Memory

**Retrieves:**
- Architecture plan from Architect Agent
- Project specifications
- Relevant code patterns from vector store
- Previous code generation results (for consistency)

**Stores:**
- Generated code files
- Implementation decisions
- Code quality metrics

## Memory Access Patterns

```python
# Example: Retrieving project context for code generation
def get_project_context(project_id):
    """Retrieve all relevant memory for a project"""
    context = {
        "specifications": vector_store.query("project_specs", project_id),
        "architecture": vector_store.query("architecture", project_id),
        "patterns": vector_store.query("code_patterns", project_id)
    }
    return context

# Example: Storing architecture decision
def store_architecture_decision(decision):
    """Store an architecture decision in memory"""
    document = {
        "id": generate_uuid(),
        "content": decision.to_markdown(),
        "metadata": {
            "decision_type": decision.type,
            "timestamp": datetime.now().isoformat(),
            "agent": "architect"
        }
    }
    vector_store.add("architecture", document)
```

## Memory Best Practices

1. **Structured Storage**: Use consistent schemas for all stored data
2. **Rich Metadata**: Include timestamps, sources, and relevance scores
3. **Embedding Quality**: Use high-quality embeddings for accurate retrieval
4. **Access Logging**: Track memory access patterns for optimization
5. **Privacy**: Sensitive information should be encrypted or excluded

## Future Enhancements

- [ ] Implement hierarchical memory organization
- [ ] Add memory compression and deduplication
- [ ] Support multi-modal memory (code + diagrams)
- [ ] Add memory versioning and rollback
- [ ] Implement cross-project knowledge sharing
