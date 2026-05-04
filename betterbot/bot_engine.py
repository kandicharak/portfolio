"""
Autonomous Software Factory - Bot Engine
Uses CrewAI with a Manager Agent (Gemini) and Coder Agent (LM Studio)
to autonomously build software projects.
"""

import os
from pathlib import Path
from crewai import Agent, Task, Crew, Process
from crewai_tools import DirectoryReadTool, FileWriterTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatOllama


# Configuration
BASE_DIR = Path("d:/betterbot")
OUTPUT_DIR = BASE_DIR / "alphabot"
MANAGER_API_KEY = "AIzaSyB2MFFLMEm5W-xfen5s9puCMsG9vXZykow"
CODER_MODEL_NAME = "qwen-2.5-7b"


# Tools for the Coder Agent
directory_read_tool = DirectoryReadTool(directory=str(OUTPUT_DIR))
file_writer_tool = FileWriterTool(base_directory=str(OUTPUT_DIR))


# Manager Agent - Uses Google Gemini
manager_llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=MANAGER_API_KEY,
    temperature=0.7
)

manager_agent = Agent(
    role="Project Manager",
    goal="Orchestrate the autonomous development process and ensure all tasks are completed correctly",
    backstory="""You are an expert project manager who coordinates software development teams. 
    Your job is to break down projects into actionable tasks, assign them to the Coder Agent, 
    and verify that everything is built correctly without needing human intervention.""",
    verbose=True,
    allow_delegation=False,
    tools=[],
    llm=manager_llm
)


# Coder Agent - Uses LM Studio with Qwen model
coder_llm = ChatOllama(
    model=CODER_MODEL_NAME,
    base_url="http://localhost:1234/v1",
    temperature=0.7
)

coder_agent = Agent(
    role="Senior Full-Stack Developer",
    goal="Write clean, production-ready code for the assigned project without asking for clarification",
    backstory="""You are an expert developer who can build complete software applications autonomously. 
    You have access to file system tools and will write all code directly to disk. 
    Do not ask for confirmation - just execute the task completely.""",
    verbose=True,
    allow_delegation=False,
    tools=[directory_read_tool, file_writer_tool],
    llm=coder_llm
)


def create_crew(project_name: str):
    """Create a Crew that builds the specified project autonomously."""
    
    # Task 1: Plan and design the project structure
    planning_task = Task(
        description=f"""You are tasked with building a '{project_name}' application. 
        First, analyze what this project needs and create a complete implementation plan.
        
        Requirements:
        - Design the file structure needed for this project
        - Plan all necessary files (HTML, CSS, JS, config files, etc.)
        - Ensure the code is production-ready and follows best practices
        
        Output your plan clearly so we know what will be built.""",
        expected_output="A detailed implementation plan with file structure and description of each component"
    )
    
    # Task 2: Create all project files
    coding_task = Task(
        description=f"""You are tasked with building a '{project_name}' application. 
        Execute the following steps AUTONOMOUSLY without asking for confirmation:
        
        Step 1: Review the implementation plan
        Step 2: Create all necessary directories and files
        Step 3: Write complete, working code for each file
        
        IMPORTANT RULES:
        - Do NOT ask me to confirm anything before writing code
        - Write ALL files in one go without stopping
        - Use FileWriterTool to create each file directly at d:/alphabot/{project_name}/
        - Make sure the project is complete and functional when done
        
        The final output should be a fully working '{project_name}' application 
        with all files saved to disk.""",
        expected_output="All code files created in d:/alphabot/{project_name}/ directory, ready to use"
    )
    
    crew = Crew(
        agents=[manager_agent, coder_agent],
        tasks=[planning_task, coding_task],
        process=Process.sequential,
        verbose=True,
        memory=True,
        cache_metadata=False
    )
    
    return crew


def main():
    """Main entry point - builds a Professional Portfolio Website."""
    print("=" * 60)
    print("AUTONOMOUS SOFTWARE FACTORY")
    print("=" * 60)
    print(f"Output Directory: {OUTPUT_DIR}")
    print()
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create and execute the crew for Portfolio Website
    project_name = "portfolio-website"
    print(f"Starting autonomous build of: '{project_name}'")
    print("-" * 60)
    
    crew = create_crew(project_name)
    
    try:
        result = crew.kickoff()
        print()
        print("=" * 60)
        print("BUILD COMPLETE!")
        print(f"All files have been saved to: {OUTPUT_DIR / project_name}")
        print("=" * 60)
        
    except Exception as e:
        print(f"Error during build: {e}")
        raise


if __name__ == "__main__":
    main()
