import os
import asyncio
import argparse
import sys
import io
from dotenv import load_dotenv

# Force UTF-8 encoding for Windows terminal
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
from langchain_openai import ChatOpenAI
from playwright.async_api import async_playwright

load_dotenv()

# Configuration - LM Studio
USE_LOCAL_LLM = True
MODEL_NAME = "qwen/qwen2.5-coder-14b" 
BASE_URL = "http://localhost:1234/v1"

async def get_action_from_llm(page, task):
    # Get interactive elements
    elements = await page.evaluate("""
        () => {
            const items = [];
            const sel = 'button, input, a, [role="button"]';
            document.querySelectorAll(sel).forEach(el => {
                if (el.offsetWidth > 0 && el.offsetHeight > 0) {
                    items.push({
                        tag: el.tagName,
                        text: el.innerText || el.value || el.placeholder || '',
                        id: el.id,
                        name: el.name,
                        type: el.type
                    });
                }
            });
            return items.slice(0, 100); // Limit to top 100
        }
    """)
    
    elements_str = "\n".join([f"- {e['tag']}: '{e['text']}' (ID: {e['id']}, Name: {e['name']})" for e in elements])

    
    llm = ChatOpenAI(
        base_url=BASE_URL,
        api_key="lm-studio",
        model=MODEL_NAME
    )
    
    # Get some page text for context
    page_text = await page.evaluate("() => document.body.innerText.slice(0, 500)")
    print(f"[Debug] Page Text Preview: {page_text[:100]}...", flush=True)
    print(f"[Debug] Elements found: {len(elements)}", flush=True)
    
    prompt = f"""
    You are a Universal Web Automation Agent (Master Brain).
    Your Goal: {task}
    Current URL: {page.url}
    Current Title: {await page.title()}
    
    PAGE CONTEXT:
    {page_text}
    
    INTERACTIVE ELEMENTS:
    {elements_str}
    
    MASTER RULES:
    1. GMAIL SEARCH: To search in Gmail, use GOTO: https://mail.google.com/mail/u/0/#search/LinkedIn+Job (replace keywords).
    2. LOGIN CHECK: You are LOGGED IN if Title/URL contains 'Inbox', 'Feed', or your email. NEVER return 'WAIT' in these cases.
    3. DATA EXTRACTION: If you see job statuses or counts, report them in DONE.
    4. Return ONLY the next action: CLICK: text, TYPE: text | selector, GOTO: url, DONE: result.
    """




    
    response = llm.invoke(prompt)
    return response.content.strip()

async def run_agent(task):
    async with async_playwright() as p:
        # Use a persistent data directory for logins
        user_data_dir = os.path.join(os.getcwd(), "user_data")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        browser_context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"] # Try to hide bot status
        )
        page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()
        
        print(f"\n[Agent] Starting task: {task}", flush=True)
        # Dynamic starting point
        task_lower = task.lower()
        if "gmail" in task_lower:
            await page.goto("https://mail.google.com")
        elif "linkedin" in task_lower:
            await page.goto("https://www.linkedin.com")
        elif "mindrift" in task_lower:
            await page.goto("https://mindrift.toloka.ai/explore")
        else:
            await page.goto("https://www.google.com")




        
        for i in range(20):
            # Wait for page to be stable
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except: pass
            
            url = page.url
            title = await page.title()
            print(f"\n[Step {i+1}] {title} | URL: {url}", flush=True)
            
            try:
                action_str = await get_action_from_llm(page, task)
                print(f"[Action] {action_str}", flush=True)

                
                if "DONE:" in action_str:
                    print(f"\n[Success] {action_str}", flush=True)
                    break
                
                if "GOTO:" in action_str:
                    await page.goto(action_str.split("GOTO:")[1].strip())
                elif "TYPE:" in action_str:
                    parts = action_str.split("TYPE:")[1].split("|")
                    text = parts[0].strip()
                    selector = parts[1].strip() if len(parts) > 1 else "q" # Default to 'q' for search
                    
                    print(f"[System] Attempting to type '{text}' into '{selector}'...", flush=True)
                    
                    # Try to remove common overlays/popups
                    try:
                        await page.evaluate("""
                            () => {
                                const popups = document.querySelectorAll('iframe, .modal, #fixed-bottom-bar, [role="dialog"]');
                                popups.forEach(p => p.remove());
                            }
                        """)
                    except: pass

                    # Try to find by name or id across any tag
                    found = False
                    for locator in [f"[name='{selector}']", f"#{selector}", selector, "textarea[name='q']", "input[name='q']"]:
                        try:
                            await page.wait_for_selector(locator, timeout=2000)
                            await page.click(locator) # Click first to focus
                            await page.fill(locator, text)
                            found = True
                            print(f"[System] Successfully filled {locator}", flush=True)
                            break
                        except:
                            continue
                    
                    if not found:
                        print(f"[Error] Could not find input for '{selector}'", flush=True)
                            
                elif "CLICK:" in action_str:
                    target = action_str.split("CLICK:")[1].strip().strip("'").strip('"')
                    print(f"[System] Attempting to click '{target}'...", flush=True)
                    try:
                        await page.click(f"text='{target}'", timeout=3000)
                    except:
                        try:
                            await page.click(target, timeout=3000)
                        except:
                            await page.click(f"button:has-text('{target}'), a:has-text('{target}'), [role='button']:has-text('{target}')", timeout=3000)

                
                elif "WAIT:" in action_str:
                    print(f"[System] {action_str}. Waiting 10 seconds for you...", flush=True)
                    await asyncio.sleep(10)

                
                # Press Enter after typing if it looks like a search
                if "TYPE:" in action_str and ("search" in task.lower() or "google" in url):
                    print("[System] Pressing Enter...", flush=True)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(3)

                    
            except Exception as e:
                print(f"[Error] {e}", flush=True)
                await asyncio.sleep(2)

        print("\n[System] Press Enter to close...", flush=True)
        input()
        await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=str)
    args = parser.parse_args()
    task = args.task or input("Enter task: ")
    asyncio.run(run_agent(task))

