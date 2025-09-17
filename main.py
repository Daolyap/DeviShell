import os
import subprocess
import sys
from typing import List, Dict, Callable, Optional

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

POWERSHELL_EXECUTABLE = "C:\\Program Files\\PowerShell\\7\\pwsh.exe"

style = Style.from_dict(
    {
        "prompt": "bg:#012456 #ffffff bold",
        "prompt.arg": "#b3d7ff",
        "prompt.text": "#ffffff",
    }
)

class DeviShellCompleter(Completer):
    def __init__(self, commands: List[str]):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text
        words = text_before_cursor.split()

        if not text_before_cursor or text_before_cursor[-1].isspace():
            return

        current_word = words[-1]

        if len(words) == 1:
            for command in self.commands:
                if command.lower().startswith(current_word.lower()):
                    yield Completion(command, start_position=-len(current_word))
        else:
            try:
                current_word = os.path.expanduser(current_word)
                path_prefix, partial_name = os.path.split(current_word)
                if not path_prefix:
                    path_prefix = '.'
                
                entries = os.listdir(path_prefix)
                for entry in entries:
                    if entry.lower().startswith(partial_name.lower()):
                        yield Completion(entry, start_position=-len(partial_name))
            except (OSError, IndexError):
                pass

def shell_cd(args: List[str]):
    """Handler for the 'cd' built-in command."""
    path = os.path.expanduser(args[0]) if args else os.path.expanduser("~")
    try:
        os.chdir(path)
    except FileNotFoundError:
        print(f"DeviShell: No such directory: {path}")
    except Exception as e:
        print(f"DeviShell: Error changing directory: {e}")

def shell_exit(args: List[str]):
    """Handler for the 'exit' and 'quit' built-in commands."""
    print("Farewell from DeviShell.")
    sys.exit(0)

BUILTIN_COMMANDS: Dict[str, Callable[[List[str]], None]] = {
    "cd": shell_cd,
    "exit": shell_exit,
    "quit": shell_exit,
}

app = typer.Typer(
    name="DeviShell",
    help="DeviShell: Python-powered commands.",
    no_args_is_help=True,
    add_completion=False
)

@app.command()
def hello(name: Optional[str] = typer.Argument("World", help="The name to greet.")):
    """Greets the user from within Python."""
    print(f"Hello, {name}!")

@app.command()
def goodbye(name: Optional[str] = typer.Argument("World", help="The name to say goodbye to.")):
    """Says goodbye to the user from within Python."""
    print(f"Goodbye, {name}!")

def run_system_command(command: List[str]):
    """Executes an external command using the specified PowerShell executable."""
    if not os.path.exists(POWERSHELL_EXECUTABLE):
        print(f"FATAL ERROR: PowerShell executable not found at '{POWERSHELL_EXECUTABLE}'")
        print("Please correct the POWERSHELL_EXECUTABLE variable in the script.")
        return

    try:
        full_command = [POWERSHELL_EXECUTABLE, "-Command", " ".join(command)]
        subprocess.run(full_command, check=True)
    except FileNotFoundError:
        print(f"DeviShell: Could not find executable at: {POWERSHELL_EXECUTABLE}")
    except subprocess.CalledProcessError:
        pass
    except Exception as e:
        print(f"DeviShell: An unexpected error occurred: {e}")

def execute_command(command: List[str]):
    """Routes a command to built-ins, Typer commands, or the OS."""
    if not command:
        return

    command_name = command[0].lower()
    args = command[1:]

    if command_name in BUILTIN_COMMANDS:
        handler = BUILTIN_COMMANDS[command_name]
        handler(args)
        return

    try:
        if command_name in [cmd.name for cmd in app.registered_commands]:
            app(args=command, standalone_mode=False)
            return
    except (typer.BadParameter, SystemExit):
        return
    except Exception:
        pass

    run_system_command(command)

def get_prompt_text():
    """Generates the text for the shell prompt."""
    cwd = os.getcwd().replace(os.path.expanduser("~"), "~")
    return [("class:prompt", "DeviShell "), ("class:prompt.arg", f"[{cwd}]"), ("class:prompt.text", " > ")]

def main():
    """The main shell loop."""
    typer_commands = [cmd.name for cmd in app.registered_commands if cmd.name]
    builtin_command_names = list(BUILTIN_COMMANDS.keys())
    
    unique_sorted_commands = sorted(list(set(typer_commands + builtin_command_names)))

    history = FileHistory(os.path.expanduser("~/.devishell_history"))
    completer = DeviShellCompleter(unique_sorted_commands)
    session = PromptSession(history=history, completer=completer, style=style)

    print("Welcome to DeviShell Mk VII!")
    print("This is a Python-based shell environment, powered by PowerShell.")

    while True:
        try:
            user_input = session.prompt(get_prompt_text)
            command_parts = user_input.split()
            if command_parts:
                execute_command(command_parts)
        except KeyboardInterrupt:
            print()
            continue
        except EOFError:
            break

if __name__ == "__main__":
    main()