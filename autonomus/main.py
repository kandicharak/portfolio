"""
Autonomous Coding Process - Main Entry Point
Uses CrewAI to orchestrate DeepSeek Coder (Architect) and Local Qwen 3.5 (Coder) agents
to generate a complete project from a software idea.
"""

# Fix Windows console encoding for UTF-8 output
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import re
import shutil
from pathlib import Path
from crewai import Agent, Task, Crew, Process

# Force LiteLLM to use local LM Studio for all OpenAI-compatible requests
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1234/v1"
os.environ["OPENAI_API_KEY"] = "lm-studio"

from agents import AgentManager


class ProjectGenerator:
    """Generates complete projects using autonomous AI agents."""
    
    def __init__(self, output_dir: str = "generated_project"):
        """
        Initialize the project generator.
        
        Args:
            output_dir: Directory where generated project will be saved
        """
        self.output_dir = Path(output_dir)
        self.agent_manager = AgentManager()
        
    def _setup_output_directory(self):
        """Create and clean output directory if it exists."""
        # Remove existing directory to start fresh
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        
        # Create new directory structure
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "core").mkdir(exist_ok=True)
        
    def _generate_architecture_plan(self, software_idea: str) -> str:
        """
        Generate architecture plan using DeepSeek Coder via OpenRouter.
        
        Args:
            software_idea: Description of the software to build
            
        Returns:
            Architecture plan as a string
        """
        manager_agent = self.agent_manager.create_manager_agent(
            name="Architect Agent",
            role="Software Architect - DeepSeek Coder",
            goal=f"Create architecture for: {software_idea}",
            backstory="Expert software architect. Create concise plan with folder structure, dependencies, modules, and file breakdown."
        )
        
        planning_task = Task(
            description=f"""Create architecture plan for: {software_idea}

Output:
1. Folder structure (tree format)
2. Python files needed
3. Key classes/functions
4. Implementation steps

Be concise and specific about filenames.""",
            expected_output="Architecture plan with folder structure and file list",
            agent=manager_agent
        )
        
        crew = Crew(
            agents=[manager_agent],
            tasks=[planning_task],
            agent_manager=self.agent_manager,
            process=Process.sequential,
            verbose=True
        )
        
        result = crew.kickoff()
        return str(result)
    
    def _generate_code(self, architecture_plan: str) -> None:
        """
        Generate code implementation using Local Qwen 3.5 via LM Studio.
        
        Args:
            architecture_plan: The architecture plan from the Architect agent
        """
        coder_agent = self.agent_manager.create_coder_agent(
            name="Coder Agent",
            role="Python Developer - Local Qwen 3.5",
            goal="Write Python code based on specifications",
            backstory="Expert Python developer. Write clean, complete files with type hints and docstrings. Follow PEP 8."
        )
        
        coding_task = Task(
            description=f"""Write ALL Python files from this plan:

{architecture_plan}

Requirements:
- Complete files (not snippets)
- Type hints and docstrings
- PEP 8 style
- Save to generated_project/ directory""",
            agent=coder_agent,
            expected_output="List of all files created with full content"
        )
        
        crew = Crew(
            agents=[coder_agent],
            tasks=[coding_task],
            process=Process.sequential,
            verbose=True
        )
        
        result = crew.kickoff()
        
        # Save the generated code to files
        self._save_generated_code(str(result.raw))
    
    def _write_file(self, filepath: str, content_lines: list) -> None:
        """
        Write file content to disk with proper directory creation.
        
        Args:
            filepath: Relative path from output_dir (e.g., "core/utils.py")
            content_lines: List of lines to write
        """
        full_path = self.output_dir / filepath
        
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file with UTF-8 encoding
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content_lines))
        
        print(f'[OK] Saved: {full_path}')
    
    def _save_generated_code(self, code_output: str) -> None:
        """
        Parse and save generated code to appropriate files using robust regex-based parsing.
        
        Args:
            code_output: The code generation output from the Coder agent
        """
        # Debug: Print full raw output BEFORE any processing
        print(f'RAW OUTPUT: {code_output}')
        
        files_created = []
        current_file = None
        current_content = []
        
        # State machine flags
        in_code_block = False
        expecting_filename = True
        
        lines = code_output.split('\n')
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines when expecting filename
            if not stripped and expecting_filename:
                continue
            
            # Detect markdown code block start with optional language specifier
            code_block_start_match = re.match(r'^```(?:python|py)?\s*$', stripped, re.IGNORECASE)
            if code_block_start_match:
                # Save previous file if exists
                if current_file and current_content:
                    self._write_file(current_file, current_content)
                    files_created.append(str(self.output_dir / current_file))
                
                in_code_block = True
                expecting_filename = False
                continue
            
            # Detect markdown code block end
            if re.match(r'^```$', stripped):
                in_code_block = False
                expecting_filename = True
                continue
            
            # Only process lines inside code blocks
            if not in_code_block:
                continue
            
            # Skip empty lines inside code block
            if not stripped:
                continue
            
            # Detect filename declaration at start of line (path pattern)
            # ONLY matches lines starting with "File:" or "FILE:" (case-insensitive)
            # This prevents false positives from keywords like "raise", "file", etc.
            filename_pattern = re.match(r'^\s*(?:File|FILE):\s*([a-zA-Z0-9_]+(?:/[a-zA-Z0-9_]+)*)\s*$', stripped, re.IGNORECASE)
            if filename_pattern:
                # Save previous file if exists
                if current_file and current_content:
                    self._write_file(current_file, current_content)
                    files_created.append(str(self.output_dir / current_file))
                
                # Start new file
                current_file = filename_pattern.group(1)
                current_content = []
                expecting_filename = False
                continue
            
            # Add line to current file content
            current_content.append(stripped)
        
        # Save last file
        if current_file and current_content:
            self._write_file(current_file, current_content)
            files_created.append(str(self.output_dir / current_file))
        
        # Existence assertion: Verify files were actually created
        if not files_created:
            files_in_dir = list(self.output_dir.glob('*'))
            print(f'EXISTENCE ASSERTION CHECK: Directory contents = {files_in_dir}')
            
            if not files_in_dir:
                print('CRITICAL ERROR: FILE NOT SAVED - No files found in output directory')
                print(f'Directory listing: {os.listdir(self.output_dir)}')
                
                # Fallback: Save raw output to success.txt
                print('FALLBACK: Saving raw output to success.txt')
                with open(self.output_dir / 'success.txt', 'w', encoding='utf-8') as f:
                    f.write(code_output)
                files_created.append(str(self.output_dir / 'success.txt'))
        
        # Final assertion: Confirm at least one file exists
        final_check = list(self.output_dir.glob('*'))
        if not final_check:
            raise RuntimeError('FATAL: No files created in output directory after all parsing attempts')
    
    def generate_project(self, software_idea: str) -> Path:
        """
        Main method to generate a complete project from a software idea.
        
        Args:
            software_idea: Description of the software to build
            
        Returns:
            Path to the generated project directory
        """
        print("=" * 60)
        print("AUTONOMOUS CODING PROCESS STARTED")
        print("=" * 60)
        print(f"\nSoftware Idea: {software_idea}\n")
        
        # Setup output directory
        self._setup_output_directory()
        print(f"Output directory: {self.output_dir.absolute()}\n")
        
        # Step 1: Generate architecture plan
        print("-" * 60)
        print("STEP 1: Generating Architecture Plan (DeepSeek Coder via OpenRouter)")
        print("-" * 60)
        architecture_plan = self._generate_architecture_plan(software_idea)
        
        # Step 2: Generate code
        print("\n" + "-" * 60)
        print("STEP 2: Generating Code (Local Qwen 3.5 via LM Studio)")
        print("-" * 60)
        self._generate_code(architecture_plan)
        
        print("\n" + "=" * 60)
        print("AUTONOMOUS CODING PROCESS COMPLETED")
        print("=" * 60)
        print(f"\nProject generated at: {self.output_dir.absolute()}")
        
        return self.output_dir


def main():
    """Main entry point for the autonomous coding process."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Autonomous Coding Process - Generate projects from ideas"
    )
    parser.add_argument(
        "idea",
        nargs="?",
        help="Software idea to generate (e.g., 'A todo list app with SQLite backend')"
    )
    parser.add_argument(
        "-o", "--output",
        default="generated_project",
        help="Output directory for generated project (default: generated_project)"
    )
    
    args = parser.parse_args()
    
    # If no idea provided, show usage
    if not args.idea:
        print("Usage: python main.py <software_idea>")
        print("\nExample:")
        print("  python main.py 'A task management app with user authentication'")
        return
    
    # Generate the project
    generator = ProjectGenerator(output_dir=args.output)
    project_path = generator.generate_project(args.idea)
    
    print(f"\n[OK] Project ready at: {project_path}")


if __name__ == "__main__":
    main()
