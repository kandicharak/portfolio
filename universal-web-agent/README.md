# 🤖 Universal Web Automation Agent
**An autonomous AI agent capable of navigating any website to perform complex workflows.**

## 🌟 Overview
The Universal Web Automation Agent is a state-of-the-art autonomous system designed to bridge the gap between Large Language Models (LLMs) and web interfaces. Unlike traditional scrapers, this agent "reasons" through tasks, handling dynamic UIs, logins, and complex multi-step processes like a human would.

## 🚀 Key Features
- **ReAct Reasoning Loop:** Implements a Thought-Action-Observation cycle to handle unexpected UI changes or popups.
- **Persistent Session Support:** Uses Playwright's persistent context to maintain logins for Gmail, LinkedIn, and other platforms.
- **LLM Agnostic:** Compatible with OpenAI (GPT-4), Claude, and local models (Qwen2.5-Coder via LM Studio).
- **Smart Element Selection:** Uses a custom JavaScript injection to identify only the most relevant interactive elements, reducing token costs and increasing accuracy.

## 🛠 Tech Stack
- **Language:** Python
- **Automation:** Playwright (Chromium)
- **Framework:** LangChain
- **Intelligence:** OpenAI API / LM Studio (Local LLM)
- **Environment:** Dotenv for secure credential management

## 📂 Project Structure
- `custom_agent.py`: Core logic for the reasoning loop and element extraction.
- `main.py`: Entry point for starting tasks.
- `user_data/`: Persistent browser data for saved sessions.

## 📋 Example Use Cases
- "Find the latest job invitation emails in my Gmail and summarize them."
- "Search for 'AI Engineer' roles on LinkedIn and track the application status."
- "Navigate to a specific dashboard and extract weekly performance metrics."

---
*Developed by Sumit Singh | AI Automation & Solutions Architect*
