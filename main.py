import os
import subprocess
import sys
import socket
import http.server
import socketserver
import threading
import secrets
import string
from typing import List, Dict, Callable, Optional
from datetime import datetime

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
import git

POWERSHELL_EXECUTABLE = "C:\\Program Files\\PowerShell\\7\\pwsh.exe"
console = Console()

PROMPT_CACHE = {
    "cwd": None,
    "venv": "",
    "git_status": "",
    "git_dirty": False,
}

style = Style.from_dict({
    "prompt.main": "bg:#012456 #ffffff bold",
    "prompt.venv": "bg:#012456 #b3d7ff",
    "prompt.git": "bg:#012456 #ccff99",
    "prompt.git.dirty": "bg:#012456 #ffcc66",
    "prompt.path": "bg:#012456 #80dfff",
    "prompt.time": "bg:#012456 #666666",
    "prompt.text": "#ffffff"
})

def echo_success(message: str): console.print(f"[bold green]✔[/bold green] {message}")
def echo_error(message: str): console.print(f"[bold red]✖[/bold red] {message}")
def echo_warning(message: str): console.print(f"[bold yellow]⚠[/bold yellow] {message}")
def echo_info(message: str): console.print(f"[bold blue]ℹ[/bold blue] {message}")

def update_prompt_cache():
    PROMPT_CACHE['cwd'] = os.getcwd()
    venv = os.environ.get("VIRTUAL_ENV")
    PROMPT_CACHE['venv'] = f"({os.path.basename(venv)}) " if venv else ""
    try:
        repo = git.Repo(search_parent_directories=True)
        branch = repo.active_branch.name
        is_dirty = repo.is_dirty()
        PROMPT_CACHE['git_status'] = f"git:({branch})"
        PROMPT_CACHE['git_dirty'] = is_dirty
    except (git.InvalidGitRepositoryError, TypeError):
        PROMPT_CACHE['git_status'] = ""
        PROMPT_CACHE['git_dirty'] = False

def get_prompt_parts():
    parts = [("class:prompt.main", " DeviShell ")]
    if PROMPT_CACHE['venv']:
        parts.append(("class:prompt.venv", PROMPT_CACHE['venv']))
    cwd_display = PROMPT_CACHE['cwd'].replace(os.path.expanduser("~"), "~")
    parts.append(("class:prompt.path", f"[{cwd_display}] "))
    if PROMPT_CACHE['git_status']:
        style_class = "class:prompt.git.dirty" if PROMPT_CACHE['git_dirty'] else "class:prompt.git"
        git_display = f"{PROMPT_CACHE['git_status']}{'*' if PROMPT_CACHE['git_dirty'] else ''} "
        parts.append((style_class, git_display))
    time_str = datetime.now().strftime('%H:%M:%S')
    parts.append(("class:prompt.time", f"[{time_str}]"))
    parts.append(("class:prompt.text", " > "))
    return parts

class DeviShellCompleter(Completer):
    def __init__(self, commands: List[str]):
        self.commands = commands
    def get_completions(self, document, complete_event):
        text_before_cursor, words = document.text, document.text.split()
        if not text_before_cursor or text_before_cursor[-1].isspace(): return
        current_word = words[-1]
        if len(words) == 1:
            for command in self.commands:
                if command.lower().startswith(current_word.lower()): yield Completion(command, start_position=-len(current_word))
        else:
            try:
                current_word = os.path.expanduser(current_word)
                path_prefix, partial_name = os.path.split(current_word)
                if not path_prefix: path_prefix = '.'
                for entry in os.listdir(path_prefix):
                    if entry.lower().startswith(partial_name.lower()): yield Completion(entry, start_position=-len(partial_name))
            except (OSError, IndexError): pass

def shell_cd(args: List[str]):
    path = os.path.expanduser(args[0]) if args else os.path.expanduser("~")
    try: os.chdir(path)
    except FileNotFoundError: echo_error(f"No such directory: {path}")
    except Exception as e: echo_error(f"Error changing directory: {e}")

def shell_exit(args: List[str]):
    console.print("[bold cyan]Farewell from DeviShell.[/bold cyan]")
    sys.exit(0)

BUILTIN_COMMANDS: Dict[str, Callable[[List[str]], None]] = {"cd": shell_cd, "exit": shell_exit, "quit": shell_exit}

app = typer.Typer(name="DeviShell", no_args_is_help=True, add_completion=False)

@app.command()
def search(term: str, path: str = typer.Option(".", "-p")):
    echo_info(f"Searching for '[bold white]{term}[/bold white]' in '{os.path.abspath(path)}'...")
    match_count = 0
    for root, dirs, files in os.walk(path):
        for name in files + dirs:
            if term.lower() in name.lower():
                console.print(f"[green]{os.path.join(root, name)}[/green]")
                match_count += 1
    echo_info(f"Found {match_count} match(es).")

@app.command()
def tree(path: str = typer.Argument("."), max_depth: int = typer.Option(3, "-d")):
    console.print(f"🌳 [bold green]{os.path.abspath(path)}[/bold green]")
    for root, dirs, files in os.walk(path):
        level = root.replace(path, '').count(os.sep)
        if level >= max_depth: dirs[:] = []
        indent = ' ' * 4 * (level)
        for d in sorted(dirs): console.print(f'{indent} L 📁 [cyan]{d}[/cyan]')
        for f in sorted(files): console.print(f'{indent} L 📄 {f}')

@app.command()
def mkcd(name: str):
    try:
        os.makedirs(name, exist_ok=True)
        shell_cd([name])
        echo_success(f"Created and entered directory: {os.path.abspath(name)}")
    except OSError as e: echo_error(f"Could not create directory. {e}")

@app.command()
def serve(port: int = 8000, path: str = typer.Option(".", "-d")):
    class DirectoryHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs): super().__init__(*args, directory=os.path.abspath(path), **kwargs)
    httpd = socketserver.TCPServer(("", port), DirectoryHandler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    echo_success(f"Serving directory '{os.path.abspath(path)}' at http://localhost:{port}")
    console.print("[yellow]Press Ctrl+C to stop the server.[/yellow]")
    try:
        while server_thread.is_alive(): server_thread.join(1)
    except KeyboardInterrupt:
        httpd.shutdown()
        echo_warning("\nWeb server stopped.")

@app.command()
def pwgen(length: int = typer.Option(16, "-l"), count: int = typer.Option(1, "-c")):
    alphabet = string.ascii_letters + string.digits + string.punctuation
    console.print("[bold magenta]Generated Passwords:[/bold magenta]")
    for _ in range(count):
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        console.print(f"  - {password}")
        
@app.command()
def myip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        echo_info(f"Your local IP is: [bold white]{ip}[/bold white]")
    except Exception: echo_error("Could not determine local IP address.")

def run_system_command(command: List[str]):
    if not os.path.exists(POWERSHELL_EXECUTABLE):
        echo_error(f"PowerShell executable not found at '{POWERSHELL_EXECUTABLE}'")
        return
    try:
        full_command = [POWERSHELL_EXECUTABLE, "-Command", " ".join(command)]
        subprocess.run(full_command, check=True)
    except subprocess.CalledProcessError:
        echo_error(f"Command failed with a non-zero exit code: '{' '.join(command)}'")
    except Exception as e:
        echo_error(f"An unexpected error occurred: {e}")

def execute_command(command: List[str]):
    if not command: return
    command_name, args = command[0].lower(), command[1:]
    if command_name in BUILTIN_COMMANDS:
        BUILTIN_COMMANDS[command_name](args)
        return
    try:
        if command_name in [cmd.name for cmd in app.registered_commands]:
            app(args=command, standalone_mode=False)
            return
    except (typer.BadParameter, SystemExit): return
    except Exception: pass
    run_system_command(command)

def main():
    console.print("Welcome to [bold]DeviShell Mk XII[/bold]: The 'Syntax-Correct' Release!")
    update_prompt_cache()
    typer_commands = [cmd.name for cmd in app.registered_commands if cmd.name]
    builtin_command_names = list(BUILTIN_COMMANDS.keys())
    unique_sorted_commands = sorted(list(set(typer_commands + builtin_command_names)))
    history = FileHistory(os.path.expanduser("~/.devishell_history"))
    completer = DeviShellCompleter(unique_sorted_commands)
    session = PromptSession(history=history, completer=completer, style=style)

    while True:
        try:
            user_input = session.prompt(get_prompt_parts)
            command_parts = user_input.split()
            if command_parts:
                execute_command(command_parts)
                current_cwd = os.getcwd()
                if PROMPT_CACHE['cwd'] != current_cwd:
                    update_prompt_cache()
        except KeyboardInterrupt: print()
        except EOFError: break

if __name__ == "__main__":
    main()