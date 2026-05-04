import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    model="qwen/qwen2.5-coder-14b"
)

print("Testing LLM connection...")
try:
    response = llm.invoke("Hi, are you working?")
    print(f"Response: {response.content}")
except Exception as e:
    print(f"Error: {e}")
