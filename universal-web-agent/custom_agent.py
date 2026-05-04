import os
import asyncio
import argparse
import google.generativeai as genai
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

# Configuration
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL_NAME = "gemini-1.5-flash" 

async def get_action_from_gemini(page_info, task):
    # Respecting free tier rate limits
    await asyncio.sleep(10)
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt = f"""
    You are a web agent. Your task is: {task}
    Current Page URL: {page_info['url']}
    Current Page Title: {page_info['title']}
    
    Return ONLY the next action in this format: ACTION: ARG1 | ARG2
    Actions: CLICK: text, TYPE: text | selector, GOTO: url, WAIT: 2, DONE: result
    """
    
    response = model.generate_content(prompt)
    return response.text.strip()

async def run_agent(task):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        print(f"\n[Agent] Starting task: {task}")
        await page.goto("https://www.google.com")
        
        for i in range(15):
            url = page.url
            title = await page.title()
            print(f"[Step {i+1}] {title}")
            
            try:
                action_str = await get_action_from_gemini({"url": url, "title": title}, task)
                print(f"[Action] {action_str}")
                
                if "DONE:" in action_str:
                    print(f"\n[Success] {action_str}")
                    break
                
                if "GOTO:" in action_str:
                    await page.goto(action_str.split("GOTO:")[1].strip())
                elif "CLICK:" in action_str:
                    target = action_str.split("CLICK:")[1].strip()
                    await page.click(f"text={target}", timeout=5000)
                elif "TYPE:" in action_str:
                    parts = action_str.split("TYPE:")[1].split("|")
                    await page.fill(parts[1].strip() if len(parts) > 1 else "input", parts[0].strip())
                elif "WAIT:" in action_str:
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"[Error] {e}")
                await asyncio.sleep(2)

        print("\n[System] Finished. Press Enter...")
        input()
        await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=str)
    args = parser.parse_args()
    task = args.task or input("Enter task: ")
    asyncio.run(run_agent(task))
