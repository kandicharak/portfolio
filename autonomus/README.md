# 🏢 Autonomous Multi-Agent Coding System
**A collaborative AI workforce that transforms software ideas into full-stack projects.**

## 🌟 Overview
This system leverages a multi-agent orchestration framework to automate the software development lifecycle. By assigning specific roles to different AI models, it can design architecture, generate code, and organize project structures autonomously.

## 🤖 The AI Team
- **Architect Agent (DeepSeek Coder):** Analyzes user requirements and generates a comprehensive project architecture and file structure.
- **Developer Agent (Qwen 2.5):** Implements the logic, creates files, and ensures code quality based on the architect's plan.

## 🚀 Key Features
- **Role-Based Orchestration:** Powered by **CrewAI** for seamless communication between agents.
- **Long-Term Memory:** Integrated with **ChromaDB** (Vector Store) to maintain context and project knowledge.
- **API-First Design:** Built on **FastAPI**, allowing it to be integrated into web dashboards or CLI tools.
- **Dynamic Project Generation:** Capable of creating complete directory structures and implementation files from a single prompt.

## 🛠 Tech Stack
- **Orchestration:** CrewAI, LangChain
- **Backend:** FastAPI, Python
- **Database:** ChromaDB (Vector Search)
- **LLMs:** DeepSeek Coder (OpenRouter), Qwen 2.5 (LM Studio)

## 📂 Architecture
The system follows a strict layered architecture:
1. **Planning Layer:** Requirements analysis and JSON-based architecture generation.
2. **Execution Layer:** File system manipulation and code generation.
3. **Memory Layer:** Context persistence via Vector Embeddings.

---
*Developed by Sumit Singh | AI Automation & Solutions Architect*
