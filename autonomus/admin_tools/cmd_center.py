import subprocess
import sys


def run_command(command):
    """Run a command in the terminal."""
    print(f"\n[CMD_CENTER] Executing: {command}")
    subprocess.run(command, shell=True)


def main():
    """Main function - takes command line arguments and executes them."""
    if len(sys.argv) < 2:
        print("=" * 50)
        print("       LEVEL 8: THE MASTER DASHBOARD")
        print("=" * 50)
        print("\nUsage: python cmd_center.py <command>")
        print("\nAvailable commands:")
        print("  - status   : Run analyzer.py")
        print("  - clock    : Start clock/index.html")
        print("  - media    : Start auto_video_concept.html")
        print("  - notes    : Run note_app/app.py")
        print("  - notify   : Run notifier/dispatcher.py (generate urgent alerts)")
        print("  - train    : Run trainer/learning_engine.py (auto-train AI)")
        print("=" * 50)
        return

    command = sys.argv[1].lower()

    if command == 'status':
        run_command('python d:/autonomus/generated_project/analyzer/analyzer.py')

    elif command == 'clock':
        try:
            import os
            if os.path.exists('d:/autonomus/generated_project/clock/index.html'):
                run_command('start d:/autonomus/generated_project/clock/index.html')
            elif os.path.exists('d:/autonomus/generated_project/web_clock/index.html'):
                run_command('start d:/autonomus/generated_project/web_clock/index.html')
            else:
                print("[CMD_CENTER] Clock file not found!")
        except Exception as e:
            print(f"[CMD_CENTER] Error: {e}")

    elif command == 'media':
        run_command('start d:/autonomus/generated_project/media_engine/auto_video_concept.html')

    elif command == 'notes':
        run_command('python d:/autonomus/generated_project/note_app/app.py')

    elif command == 'notify':
        run_command('python d:/autonomus/generated_project/notifier/dispatcher.py')

    elif command == 'train':
        run_command('python d:/autonomus/generated_project/trainer/learning_engine.py')

    else:
        print(f"[CMD_CENTER] Unknown command: {command}")
        print("Type 'python cmd_center.py' without arguments to see available commands.")


if __name__ == "__main__":
    main()
