import os
import asyncio
import argparse
import sys
import io
from dotenv import load_dotenv

# Force UTF-8 encoding for Windows terminal
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from browser_use import Agent

# Load environment variables
load_dotenv()

# CONFIGURATION TOGGLE
USE_LOCAL_LLM = True  

# Wrapper to fix browser-use compatibility
class BrowserUseLLM:
    def __init__(self, llm, model_name, provider="openai"):
        self.llm = llm
        self.provider = provider
        self.model = model_name
        self.model_name = model_name
    def __getattr__(self, name):
        return getattr(self.llm, name)

def get_llm():
    if USE_LOCAL_LLM:
        print("\n--- [STATUS] Using Local LLM via LM Studio ---")
        model_name = "qwen/qwen2.5-coder-14b"
        llm = ChatOpenAI(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
            model=model_name 
        )
        return BrowserUseLLM(llm, model_name, "openai")
    else:
        print("\n--- [STATUS] Using Gemini 1.5 Flash (OpenAI-Compatible Mode) ---")
        model_name = "gemini-1.5-flash"
        llm = ChatOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("GOOGLE_API_KEY"),
            model=model_name
        )
        return BrowserUseLLM(llm, model_name, "openai")

async def main():
    parser = argparse.ArgumentParser(description="Universal Web Agent")
    parser.add_argument("--task", type=str, help="The task to perform")
    args = parser.parse_args()

    print("\n" + "="*50)
    print(" UNIVERSAL WEB AGENT - CLONE OF ANTIGRAVITY ")
    print("="*50)
    
    task = args.task or input("\n[Agent] What task should I perform on the web? ")
    
    if not task:
        print("No task provided. Exiting.")
        return

    # Use the stable LLM
    llm = get_llm()

    # Initialize the Agent
    agent = Agent(
        task=task,
        llm=llm,
    )

    print(f"\n[Thinking] Starting task: '{task}'...")
    
    try:
        # Run the agent
        result = await agent.run()
        print(f"\nFINAL SUMMARY:\n{result}")
    except Exception as e:
        print(f"\n[Error] Agent encountered a problem: {e}")
    
    # Keep the browser open so user can see the state
    input("\n[System] Press Enter to close the browser and exit...")

if __name__ == "__main__":
    asyncio.run(main())
