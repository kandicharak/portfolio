"""
CrewAI Agents Module
Manages two specialized agents:
- Manager Agent (Cloud): Uses OpenRouter API for software planning
- Coder Agent (Local): Uses LM Studio local LLM for code generation
"""

from typing import Optional
from crewai import Agent, Task, Crew
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class AgentManager:
    """Manages the creation and execution of CrewAI agents."""
    
    def __init__(self):
        # Load environment variables (already loaded by load_dotenv above)
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.lmstudio_base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        
        # Validate required environment variables
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required. Please set it in your .env file.")
    
    def create_manager_agent(self, name: str = "Manager Agent",
                            role: str = "Software Architect",
                            goal: str = "Plan software architecture and design",
                            backstory: Optional[str] = None) -> Agent:
        """
        Creates a Manager agent that uses OpenRouter API.
        
        Args:
            name: Name of the agent
            role: Role description for the agent
            goal: Primary goal of the agent
            backstory: Background context for the agent
            
        Returns:
            Configured CrewAI Agent instance
        """
        # Default backstory if not provided
        if backstory is None:
            backstory = """You are an expert software architect with deep knowledge of system design,
            architecture patterns, and best practices. You excel at breaking down complex problems
            into manageable components and creating detailed technical specifications."""
        
        return Agent(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            llm="openrouter/deepseek/deepseek-chat",
            api_key=self.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            verbose=True,
            allow_delegation=False,
            tools=[]
        )
    
    def create_coder_agent(self, name: str = "Coder Agent",
                          role: str = "Local Developer",
                          goal: str = "Write clean, efficient code based on specifications",
                          backstory: Optional[str] = None) -> Agent:
        """
        Creates a Coder agent that uses LM Studio local LLM via LiteLLM.
        
        Args:
            name: Name of the agent
            role: Role description for the agent
            goal: Primary goal of the agent
            backstory: Background context for the agent
            
        Returns:
            Configured CrewAI Agent instance
        """
        # Default backstory if not provided
        if backstory is None:
            backstory = """You are an expert Python developer with deep knowledge of software engineering
            best practices, clean code principles, and modern development patterns. You excel at
            translating technical specifications into production-ready code."""
        
        return Agent(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            llm="openai/local-model",  # LiteLLM model identifier for local LM Studio
            api_key="lm-studio",  # Special key for LiteLLM/LM Studio integration
            base_url="http://127.0.0.1:1234/v1",  # LM Studio local endpoint
            verbose=True,
            allow_delegation=False,
            llm_kwargs={
                "api_key": "lm-studio",
                "base_url": "http://127.0.0.1:1234/v1"
            }
        )
    
    def create_planning_task(self, manager_agent: Agent, 
                            task_description: str) -> Task:
        """
        Creates a planning task for the Manager agent.
        
        Args:
            manager_agent: The Manager agent instance
            task_description: Description of what needs to be planned
            
        Returns:
            Configured CrewAI Task instance
        """
        return Task(
            description=task_description,
            agent=manager_agent,
            expected_output="Detailed software architecture plan with components, data flow, and implementation strategy",
        )
    
    def create_coding_task(self, coder_agent: Agent,
                          planning_specification: str) -> Task:
        """
        Creates a coding task for the Coder agent.
        
        Args:
            coder_agent: The Coder agent instance
            planning_specification: The architecture plan from Manager
            
        Returns:
            Configured CrewAI Task instance
        """
        return Task(
            description=f"Based on the following specification, write the complete code implementation:\n\n{planning_specification}",
            agent=coder_agent,
            expected_output="Complete, production-ready Python code with proper error handling and documentation",
        )
    
    def create_crew(self, manager_agent: Agent, coder_agent: Agent) -> Crew:
        """
        Creates a Crew with Manager and Coder agents.
        
        Args:
            manager_agent: The Manager agent instance
            coder_agent: The Coder agent instance
            
        Returns:
            Configured CrewAI Crew instance
        """
        return Crew(
            agents=[manager_agent, coder_agent],
            tasks=[],  # Tasks will be added dynamically
            verbose=True,
            process="sequential",  # Manager plans first, then Coder implements
        )


# Global agent manager instance
agent_manager = AgentManager()
