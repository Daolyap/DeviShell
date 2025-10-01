import os
import subprocess
import sys
import socket
import http.server
import socketserver
import threading
import secrets
import string
import json
import shutil
import psutil
import platform
import importlib.util
from pathlib import Path
from typing import List, Dict, Callable, Optional, Any
from datetime import datetime
from collections import deque

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import PygmentsLexer
from pygments.lexers.shell import BashLexer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, TextColumn
import git

POWERSHELL_EXECUTABLE = "C:\\Program Files\\PowerShell\\7\\pwsh.exe"
console = Console()
CONFIG_DIR = Path.home() / ".devishell"
CONFIG_FILE = CONFIG_DIR / "config.json"
BOOKMARKS_FILE = CONFIG_DIR / "bookmarks.json"
ALIASES_FILE = CONFIG_DIR / "aliases.json"
PLUGINS_DIR = CONFIG_DIR / "plugins"
HISTORY_FILE = CONFIG_DIR / "history"
STARTUP_SCRIPT = CONFIG_DIR / "startup.dsh"

PROMPT_CACHE = {
    "cwd": None,
    "venv": "",
    "git_status": "",
    "git_dirty": False,
    "git_ahead": 0,
    "git_behind": 0,
}

# Default configuration
DEFAULT_CONFIG = {
    "theme": "default",
    "show_time": True,
    "show_git": True,
    "show_venv": True,
    "max_path_length": 50,
    "history_size": 10000,
    "prompt_char": ">",
    "powershell_path": "C:\\Program Files\\PowerShell\\7\\pwsh.exe",
}

# Theme definitions
THEMES = {
    "default": {
        "prompt.main": "bg:#012456 #ffffff bold",
        "prompt.venv": "bg:#012456 #b3d7ff",
        "prompt.git": "bg:#012456 #ccff99",
        "prompt.git.dirty": "bg:#012456 #ffcc66",
        "prompt.path": "bg:#012456 #80dfff",
        "prompt.time": "bg:#012456 #666666",
        "prompt.text": "#ffffff"
    },
    "dark": {
        "prompt.main": "bg:#1a1a1a #00ff00 bold",
        "prompt.venv": "bg:#1a1a1a #00cccc",
        "prompt.git": "bg:#1a1a1a #ffff00",
        "prompt.git.dirty": "bg:#1a1a1a #ff6600",
        "prompt.path": "bg:#1a1a1a #00aaff",
        "prompt.time": "bg:#1a1a1a #888888",
        "prompt.text": "#00ff00"
    },
    "matrix": {
        "prompt.main": "bg:#000000 #00ff00 bold",
        "prompt.venv": "bg:#000000 #00ff00",
        "prompt.git": "bg:#000000 #00ff00",
        "prompt.git.dirty": "bg:#000000 #ffff00",
        "prompt.path": "bg:#000000 #00cc00",
        "prompt.time": "bg:#000000 #008800",
        "prompt.text": "#00ff00"
    },
    "ocean": {
        "prompt.main": "bg:#001f3f #ffffff bold",
        "prompt.venv": "bg:#001f3f #7fdbff",
        "prompt.git": "bg:#001f3f #39cccc",
        "prompt.git.dirty": "bg:#001f3f #ff851b",
        "prompt.path": "bg:#001f3f #0074d9",
        "prompt.time": "bg:#001f3f #85144b",
        "prompt.text": "#ffffff"
    },
    "sunset": {
        "prompt.main": "bg:#2c1810 #ffdd57 bold",
        "prompt.venv": "bg:#2c1810 #ff6b6b",
        "prompt.git": "bg:#2c1810 #4ecdc4",
        "prompt.git.dirty": "bg:#2c1810 #ff6348",
        "prompt.path": "bg:#2c1810 #ff9ff3",
        "prompt.time": "bg:#2c1810 #a29bfe",
        "prompt.text": "#ffdd57"
    }
}

# Global state
config = {}
bookmarks = {}
aliases = {}
command_history = deque(maxlen=100)
loaded_plugins = {}

def ensure_config_dir():
    """Ensure configuration directory and files exist"""
    CONFIG_DIR.mkdir(exist_ok=True)
    PLUGINS_DIR.mkdir(exist_ok=True)

    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)

    if not BOOKMARKS_FILE.exists():
        with open(BOOKMARKS_FILE, 'w') as f:
            json.dump({}, f)

    if not ALIASES_FILE.exists():
        with open(ALIASES_FILE, 'w') as f:
            json.dump({}, f)

def load_config():
    """Load configuration from file"""
    global config
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = {**DEFAULT_CONFIG, **json.load(f)}
    except Exception as e:
        echo_error(f"Failed to load config: {e}")
        config = DEFAULT_CONFIG.copy()

def save_config(cfg: Dict):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        echo_error(f"Failed to save config: {e}")

def load_bookmarks():
    """Load bookmarks from file"""
    global bookmarks
    try:
        with open(BOOKMARKS_FILE, 'r') as f:
            bookmarks = json.load(f)
    except Exception as e:
        echo_error(f"Failed to load bookmarks: {e}")
        bookmarks = {}

def save_bookmarks():
    """Save bookmarks to file"""
    try:
        with open(BOOKMARKS_FILE, 'w') as f:
            json.dump(bookmarks, f, indent=2)
    except Exception as e:
        echo_error(f"Failed to save bookmarks: {e}")

def load_aliases():
    """Load aliases from file"""
    global aliases
    try:
        with open(ALIASES_FILE, 'r') as f:
            aliases = json.load(f)
    except Exception as e:
        echo_error(f"Failed to load aliases: {e}")
        aliases = {}

def save_aliases():
    """Save aliases to file"""
    try:
        with open(ALIASES_FILE, 'w') as f:
            json.dump(aliases, f, indent=2)
    except Exception as e:
        echo_error(f"Failed to save aliases: {e}")

def load_plugins():
    """Load plugins from plugins directory"""
    global loaded_plugins
    if not PLUGINS_DIR.exists():
        return

    for plugin_file in PLUGINS_DIR.glob("*.py"):
        try:
            spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, 'register'):
                    loaded_plugins[plugin_file.stem] = module
                    echo_success(f"Loaded plugin: {plugin_file.stem}")
        except Exception as e:
            echo_error(f"Failed to load plugin {plugin_file.stem}: {e}")

def get_style():
    """Get current theme style"""
    theme_name = config.get("theme", "default")
    theme = THEMES.get(theme_name, THEMES["default"])
    return Style.from_dict(theme)

def echo_success(message: str):
    console.print(f"[bold green]✔[/bold green] {message}")

def echo_error(message: str):
    console.print(f"[bold red]✖[/bold red] {message}")

def echo_warning(message: str):
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")

def echo_info(message: str):
    console.print(f"[bold blue]ℹ[/bold blue] {message}")

def update_prompt_cache():
    """Update cached prompt information"""
    PROMPT_CACHE['cwd'] = os.getcwd()

    # Virtual environment
    venv = os.environ.get("VIRTUAL_ENV")
    PROMPT_CACHE['venv'] = f"({os.path.basename(venv)}) " if venv else ""

    # Git status
    if config.get("show_git", True):
        try:
            repo = git.Repo(search_parent_directories=True)
            branch = repo.active_branch.name
            is_dirty = repo.is_dirty()

            # Check ahead/behind
            try:
                ahead_behind = repo.iter_commits(f'origin/{branch}..{branch}')
                PROMPT_CACHE['git_ahead'] = sum(1 for _ in ahead_behind)
                ahead_behind = repo.iter_commits(f'{branch}..origin/{branch}')
                PROMPT_CACHE['git_behind'] = sum(1 for _ in ahead_behind)
            except:
                PROMPT_CACHE['git_ahead'] = 0
                PROMPT_CACHE['git_behind'] = 0

            PROMPT_CACHE['git_status'] = f"git:({branch})"
            PROMPT_CACHE['git_dirty'] = is_dirty
        except (git.InvalidGitRepositoryError, TypeError):
            PROMPT_CACHE['git_status'] = ""
            PROMPT_CACHE['git_dirty'] = False
            PROMPT_CACHE['git_ahead'] = 0
            PROMPT_CACHE['git_behind'] = 0

def get_prompt_parts():
    """Generate prompt parts for display"""
    parts = [("class:prompt.main", " DeviShell ")]

    # Virtual environment
    if config.get("show_venv", True) and PROMPT_CACHE['venv']:
        parts.append(("class:prompt.venv", PROMPT_CACHE['venv']))

    # Current directory
    cwd_display = PROMPT_CACHE['cwd'].replace(os.path.expanduser("~"), "~")
    max_length = config.get("max_path_length", 50)
    if len(cwd_display) > max_length:
        cwd_display = "..." + cwd_display[-(max_length-3):]
    parts.append(("class:prompt.path", f"[{cwd_display}] "))

    # Git status
    if config.get("show_git", True) and PROMPT_CACHE['git_status']:
        style_class = "class:prompt.git.dirty" if PROMPT_CACHE['git_dirty'] else "class:prompt.git"
        git_display = PROMPT_CACHE['git_status']

        if PROMPT_CACHE['git_dirty']:
            git_display += "*"
        if PROMPT_CACHE['git_ahead'] > 0:
            git_display += f"↑{PROMPT_CACHE['git_ahead']}"
        if PROMPT_CACHE['git_behind'] > 0:
            git_display += f"↓{PROMPT_CACHE['git_behind']}"

        git_display += " "
        parts.append((style_class, git_display))

    # Time
    if config.get("show_time", True):
        time_str = datetime.now().strftime('%H:%M:%S')
        parts.append(("class:prompt.time", f"[{time_str}]"))

    # Prompt character
    prompt_char = config.get("prompt_char", ">")
    parts.append(("class:prompt.text", f" {prompt_char} "))

    return parts

class DeviShellCompleter(Completer):
    """Enhanced command completer"""
    def __init__(self, commands: List[str]):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text
        words = text_before_cursor.split()

        if not text_before_cursor or text_before_cursor[-1].isspace():
            return

        current_word = words[-1] if words else ""

        # Complete commands
        if len(words) == 1:
            for command in self.commands:
                if command.lower().startswith(current_word.lower()):
                    yield Completion(command, start_position=-len(current_word))

            # Complete aliases
            for alias_name in aliases.keys():
                if alias_name.lower().startswith(current_word.lower()):
                    yield Completion(alias_name, start_position=-len(current_word), display=f"{alias_name} (alias)")

            # Complete bookmarks with @
            if current_word.startswith("@"):
                bookmark_search = current_word[1:]
                for bookmark_name in bookmarks.keys():
                    if bookmark_name.lower().startswith(bookmark_search.lower()):
                        yield Completion(f"@{bookmark_name}", start_position=-len(current_word))
        else:
            # File/directory completion
            try:
                current_word = os.path.expanduser(current_word)
                path_prefix, partial_name = os.path.split(current_word)
                if not path_prefix:
                    path_prefix = '.'

                if os.path.isdir(path_prefix):
                    for entry in os.listdir(path_prefix):
                        if entry.lower().startswith(partial_name.lower()):
                            full_path = os.path.join(path_prefix, entry)
                            display = entry + ("/" if os.path.isdir(full_path) else "")
                            yield Completion(entry, start_position=-len(partial_name), display=display)
            except (OSError, IndexError):
                pass

# ====================
# Built-in Commands
# ====================

def shell_cd(args: List[str]):
    """Change directory with bookmark support"""
    if not args:
        path = os.path.expanduser("~")
    elif args[0].startswith("@"):
        bookmark_name = args[0][1:]
        if bookmark_name in bookmarks:
            path = bookmarks[bookmark_name]
            echo_info(f"Jumping to bookmark: {bookmark_name}")
        else:
            echo_error(f"Bookmark not found: {bookmark_name}")
            return
    elif args[0] == "-":
        # Go to previous directory
        prev_dir = os.environ.get("OLDPWD")
        if prev_dir:
            path = prev_dir
        else:
            echo_error("No previous directory")
            return
    else:
        path = os.path.expanduser(args[0])

    try:
        os.environ["OLDPWD"] = os.getcwd()
        os.chdir(path)
    except FileNotFoundError:
        echo_error(f"No such directory: {path}")
    except Exception as e:
        echo_error(f"Error changing directory: {e}")

def shell_exit(args: List[str]):
    """Exit DeviShell"""
    console.print("[bold cyan]Farewell from DeviShell.[/bold cyan]")
    sys.exit(0)

def shell_clear(args: List[str]):
    """Clear the screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def shell_history(args: List[str]):
    """Show command history"""
    if not command_history:
        echo_info("No command history")
        return

    table = Table(title="Command History")
    table.add_column("#", style="cyan", width=6)
    table.add_column("Command", style="white")

    for i, cmd in enumerate(list(command_history)[-50:], 1):
        table.add_row(str(i), cmd)

    console.print(table)

BUILTIN_COMMANDS: Dict[str, Callable[[List[str]], None]] = {
    "cd": shell_cd,
    "exit": shell_exit,
    "quit": shell_exit,
    "clear": shell_clear,
    "cls": shell_clear,
    "history": shell_history,
}

# ====================
# Extended Commands (Direct Functions)
# ====================

# We'll use a command registry instead of Typer's dispatcher for better shell integration
EXTENDED_COMMANDS = {}

def command(func):
    """Decorator to register extended commands"""
    EXTENDED_COMMANDS[func.__name__] = func
    return func

# Configuration Commands
@command
def config_set(key: str = None, value: str = None):
    """Set a configuration value"""
    config[key] = value
    save_config(config)
    echo_success(f"Set {key} = {value}")

@app.command()
def config_get(key: str = typer.Argument(None)):
    """Get configuration value(s)"""
    if key:
        value = config.get(key, "Not set")
        console.print(f"{key}: [cyan]{value}[/cyan]")
    else:
        table = Table(title="Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")

        for k, v in config.items():
            table.add_row(k, str(v))

        console.print(table)

@app.command()
def theme(name: str = typer.Argument(None)):
    """Set or list themes"""
    if name:
        if name in THEMES:
            config["theme"] = name
            save_config(config)
            echo_success(f"Theme set to: {name}")
        else:
            echo_error(f"Unknown theme: {name}")
            console.print(f"Available themes: {', '.join(THEMES.keys())}")
    else:
        console.print(f"Current theme: [cyan]{config.get('theme', 'default')}[/cyan]")
        console.print(f"Available themes: {', '.join(THEMES.keys())}")

# Bookmark Commands
@app.command()
def bookmark(name: str = typer.Argument(None), path: str = typer.Argument(None)):
    """Bookmark current or specified directory"""
    if not name:
        # List bookmarks
        if not bookmarks:
            echo_info("No bookmarks saved")
            return

        table = Table(title="Bookmarks")
        table.add_column("Name", style="cyan")
        table.add_column("Path", style="white")

        for bm_name, bm_path in bookmarks.items():
            table.add_row(bm_name, bm_path)

        console.print(table)
    else:
        # Add bookmark
        target_path = path if path else os.getcwd()
        target_path = os.path.abspath(os.path.expanduser(target_path))

        if not os.path.isdir(target_path):
            echo_error(f"Not a directory: {target_path}")
            return

        bookmarks[name] = target_path
        save_bookmarks()
        echo_success(f"Bookmarked '{target_path}' as '@{name}'")

@app.command()
def unbookmark(name: str):
    """Remove a bookmark"""
    if name in bookmarks:
        del bookmarks[name]
        save_bookmarks()
        echo_success(f"Removed bookmark: {name}")
    else:
        echo_error(f"Bookmark not found: {name}")

# Alias Commands
@app.command()
def alias(name: str = typer.Argument(None), command: str = typer.Argument(None)):
    """Create or list command aliases"""
    if not name:
        # List aliases
        if not aliases:
            echo_info("No aliases defined")
            return

        table = Table(title="Aliases")
        table.add_column("Alias", style="cyan")
        table.add_column("Command", style="white")

        for alias_name, alias_cmd in aliases.items():
            table.add_row(alias_name, alias_cmd)

        console.print(table)
    elif not command:
        # Show specific alias
        if name in aliases:
            console.print(f"{name}: [cyan]{aliases[name]}[/cyan]")
        else:
            echo_error(f"Alias not found: {name}")
    else:
        # Create alias
        aliases[name] = command
        save_aliases()
        echo_success(f"Created alias: {name} -> {command}")

@app.command()
def unalias(name: str):
    """Remove an alias"""
    if name in aliases:
        del aliases[name]
        save_aliases()
        echo_success(f"Removed alias: {name}")
    else:
        echo_error(f"Alias not found: {name}")

# File Operations
@app.command()
def search(term: str, path: str = typer.Option(".", "-p", "--path")):
    """Recursively search for files and directories"""
    echo_info(f"Searching for '[bold white]{term}[/bold white]' in '{os.path.abspath(path)}'...")
    match_count = 0

    for root, dirs, files in os.walk(path):
        for name in files + dirs:
            if term.lower() in name.lower():
                full_path = os.path.join(root, name)
                is_dir = os.path.isdir(full_path)
                icon = "📁" if is_dir else "📄"
                console.print(f"{icon} [green]{full_path}[/green]")
                match_count += 1

    echo_info(f"Found {match_count} match(es).")

@app.command()
def tree(path: str = typer.Argument("."), max_depth: int = typer.Option(3, "-d", "--depth")):
    """Display directory tree"""
    path = os.path.abspath(path)
    tree_obj = Tree(f"📁 [bold cyan]{path}[/bold cyan]")

    def add_tree_items(parent_tree, parent_path, current_depth):
        if current_depth >= max_depth:
            return

        try:
            items = sorted(os.listdir(parent_path))
            dirs = [i for i in items if os.path.isdir(os.path.join(parent_path, i))]
            files = [i for i in items if os.path.isfile(os.path.join(parent_path, i))]

            for d in dirs:
                dir_path = os.path.join(parent_path, d)
                branch = parent_tree.add(f"📁 [cyan]{d}[/cyan]")
                add_tree_items(branch, dir_path, current_depth + 1)

            for f in files:
                parent_tree.add(f"📄 {f}")
        except PermissionError:
            parent_tree.add("[red]Permission Denied[/red]")

    add_tree_items(tree_obj, path, 0)
    console.print(tree_obj)

@app.command()
def mkcd(name: str):
    """Create directory and enter it"""
    try:
        os.makedirs(name, exist_ok=True)
        shell_cd([name])
        echo_success(f"Created and entered directory: {os.path.abspath(name)}")
    except OSError as e:
        echo_error(f"Could not create directory: {e}")

@app.command()
def touch(filename: str):
    """Create an empty file"""
    try:
        Path(filename).touch()
        echo_success(f"Created file: {filename}")
    except Exception as e:
        echo_error(f"Failed to create file: {e}")

@app.command()
def cat(filename: str, lines: int = typer.Option(None, "-n", "--lines")):
    """Display file contents with syntax highlighting"""
    try:
        with open(filename, 'r') as f:
            content = f.read()

        if lines:
            content = '\n'.join(content.split('\n')[:lines])

        # Detect file type for syntax highlighting
        syntax = Syntax(content, lexer="text", theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=filename, border_style="cyan"))
    except FileNotFoundError:
        echo_error(f"File not found: {filename}")
    except Exception as e:
        echo_error(f"Error reading file: {e}")

@app.command()
def grep(pattern: str, path: str = typer.Argument("."),
         recursive: bool = typer.Option(True, "-r", "--recursive")):
    """Search for pattern in files"""
    import re

    echo_info(f"Searching for pattern: {pattern}")
    match_count = 0

    if recursive:
        for root, dirs, files in os.walk(path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if re.search(pattern, line):
                                console.print(f"[cyan]{file_path}[/cyan]:[yellow]{line_num}[/yellow]: {line.strip()}")
                                match_count += 1
                except:
                    pass
    else:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    if re.search(pattern, line):
                        console.print(f"[yellow]{line_num}[/yellow]: {line.strip()}")
                        match_count += 1
        except Exception as e:
            echo_error(f"Error: {e}")

    echo_info(f"Found {match_count} match(es)")

@app.command()
def copy(source: str, dest: str):
    """Copy file or directory"""
    try:
        if os.path.isdir(source):
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
        echo_success(f"Copied: {source} -> {dest}")
    except Exception as e:
        echo_error(f"Copy failed: {e}")

@app.command()
def move(source: str, dest: str):
    """Move file or directory"""
    try:
        shutil.move(source, dest)
        echo_success(f"Moved: {source} -> {dest}")
    except Exception as e:
        echo_error(f"Move failed: {e}")

@app.command()
def remove(path: str, force: bool = typer.Option(False, "-f", "--force")):
    """Remove file or directory"""
    if not force:
        confirm = input(f"Remove {path}? (y/N): ")
        if confirm.lower() != 'y':
            echo_warning("Cancelled")
            return

    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        echo_success(f"Removed: {path}")
    except Exception as e:
        echo_error(f"Remove failed: {e}")

# Network Commands
@app.command()
def serve(port: int = 8000, path: str = typer.Option(".", "-d", "--directory")):
    """Start a local HTTP server"""
    class DirectoryHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=os.path.abspath(path), **kwargs)

    httpd = socketserver.TCPServer(("", port), DirectoryHandler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    echo_success(f"Serving '{os.path.abspath(path)}' at http://localhost:{port}")
    console.print("[yellow]Press Ctrl+C to stop the server.[/yellow]")

    try:
        while server_thread.is_alive():
            server_thread.join(1)
    except KeyboardInterrupt:
        httpd.shutdown()
        echo_warning("\nWeb server stopped.")

@app.command()
def myip():
    """Show local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        echo_info(f"Local IP: [bold white]{ip}[/bold white]")
    except Exception:
        echo_error("Could not determine local IP address")

@app.command()
def port_scan(host: str = "localhost", start: int = 1, end: int = 1024):
    """Scan for open ports"""
    echo_info(f"Scanning ports {start}-{end} on {host}...")
    open_ports = []

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Scanning...", total=end - start + 1)

        for port in range(start, end + 1):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                open_ports.append(port)
                console.print(f"[green]Port {port}: OPEN[/green]")

            progress.advance(task)

    if open_ports:
        echo_success(f"Found {len(open_ports)} open port(s)")
    else:
        echo_info("No open ports found")

# System Commands
@app.command()
def sysinfo():
    """Display system information"""
    table = Table(title="System Information")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("OS", f"{platform.system()} {platform.release()}")
    table.add_row("Version", platform.version())
    table.add_row("Architecture", platform.machine())
    table.add_row("Processor", platform.processor())
    table.add_row("Hostname", socket.gethostname())

    # Memory info
    mem = psutil.virtual_memory()
    table.add_row("Total RAM", f"{mem.total / (1024**3):.2f} GB")
    table.add_row("Available RAM", f"{mem.available / (1024**3):.2f} GB")
    table.add_row("RAM Usage", f"{mem.percent}%")

    # Disk info
    disk = psutil.disk_usage('/')
    table.add_row("Total Disk", f"{disk.total / (1024**3):.2f} GB")
    table.add_row("Free Disk", f"{disk.free / (1024**3):.2f} GB")
    table.add_row("Disk Usage", f"{disk.percent}%")

    # CPU info
    table.add_row("CPU Cores", str(psutil.cpu_count(logical=False)))
    table.add_row("CPU Threads", str(psutil.cpu_count(logical=True)))
    table.add_row("CPU Usage", f"{psutil.cpu_percent(interval=1)}%")

    console.print(table)

@app.command()
def processes(limit: int = typer.Option(20, "-n", "--limit")):
    """List running processes"""
    table = Table(title="Top Processes")
    table.add_column("PID", style="cyan", width=8)
    table.add_column("Name", style="white", width=30)
    table.add_column("CPU%", style="yellow", width=8)
    table.add_column("Memory%", style="magenta", width=8)

    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Sort by CPU usage
    processes.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)

    for proc in processes[:limit]:
        table.add_row(
            str(proc['pid']),
            proc['name'][:28],
            f"{proc.get('cpu_percent', 0):.1f}",
            f"{proc.get('memory_percent', 0):.1f}"
        )

    console.print(table)

@app.command()
def kill(pid: int):
    """Kill a process by PID"""
    try:
        process = psutil.Process(pid)
        process_name = process.name()
        process.kill()
        echo_success(f"Killed process {pid} ({process_name})")
    except psutil.NoSuchProcess:
        echo_error(f"No process with PID {pid}")
    except psutil.AccessDenied:
        echo_error(f"Access denied to kill process {pid}")
    except Exception as e:
        echo_error(f"Failed to kill process: {e}")

@app.command()
def env(var: str = typer.Argument(None), value: str = typer.Argument(None)):
    """Get or set environment variables"""
    if not var:
        # List all environment variables
        table = Table(title="Environment Variables")
        table.add_column("Variable", style="cyan")
        table.add_column("Value", style="white")

        for key, val in sorted(os.environ.items()):
            # Truncate long values
            display_val = val if len(val) < 80 else val[:77] + "..."
            table.add_row(key, display_val)

        console.print(table)
    elif not value:
        # Get specific variable
        val = os.environ.get(var)
        if val:
            console.print(f"{var}: [cyan]{val}[/cyan]")
        else:
            echo_warning(f"Environment variable not set: {var}")
    else:
        # Set variable
        os.environ[var] = value
        echo_success(f"Set {var} = {value}")

@app.command()
def diskusage(path: str = "."):
    """Show disk usage of directory"""
    path = os.path.abspath(path)

    if not os.path.exists(path):
        echo_error(f"Path not found: {path}")
        return

    echo_info(f"Calculating disk usage for: {path}")

    total_size = 0
    file_count = 0
    dir_count = 0

    for dirpath, dirnames, filenames in os.walk(path):
        dir_count += len(dirnames)
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(file_path)
                file_count += 1
            except OSError:
                pass

    # Convert to appropriate unit
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if total_size < 1024.0:
            break
        total_size /= 1024.0

    console.print(f"Total Size: [bold cyan]{total_size:.2f} {unit}[/bold cyan]")
    console.print(f"Files: [yellow]{file_count}[/yellow]")
    console.print(f"Directories: [magenta]{dir_count}[/magenta]")

# Git Commands
@app.command()
def gitstatus():
    """Enhanced git status"""
    try:
        repo = git.Repo(search_parent_directories=True)

        console.print(Panel(f"[bold cyan]Repository: {repo.working_dir}[/bold cyan]"))

        # Branch info
        branch = repo.active_branch.name
        console.print(f"Branch: [green]{branch}[/green]")

        # Modified files
        if repo.is_dirty():
            console.print("\n[yellow]Modified files:[/yellow]")
            for item in repo.index.diff(None):
                console.print(f"  • [yellow]{item.a_path}[/yellow]")

        # Untracked files
        untracked = repo.untracked_files
        if untracked:
            console.print("\n[red]Untracked files:[/red]")
            for file in untracked:
                console.print(f"  • [red]{file}[/red]")

        # Staged files
        staged = repo.index.diff("HEAD")
        if staged:
            console.print("\n[green]Staged files:[/green]")
            for item in staged:
                console.print(f"  • [green]{item.a_path}[/green]")

        if not repo.is_dirty() and not untracked:
            echo_success("Working directory clean")

    except git.InvalidGitRepositoryError:
        echo_error("Not a git repository")

@app.command()
def gitlog(count: int = typer.Option(10, "-n", "--count")):
    """Show git log"""
    try:
        repo = git.Repo(search_parent_directories=True)

        table = Table(title="Git Log")
        table.add_column("Hash", style="cyan", width=10)
        table.add_column("Author", style="yellow", width=20)
        table.add_column("Date", style="magenta", width=20)
        table.add_column("Message", style="white")

        for commit in list(repo.iter_commits())[:count]:
            table.add_row(
                commit.hexsha[:8],
                commit.author.name[:18],
                datetime.fromtimestamp(commit.committed_date).strftime("%Y-%m-%d %H:%M"),
                commit.message.split('\n')[0][:50]
            )

        console.print(table)

    except git.InvalidGitRepositoryError:
        echo_error("Not a git repository")

@app.command()
def gitbranches():
    """List git branches"""
    try:
        repo = git.Repo(search_parent_directories=True)
        current_branch = repo.active_branch.name

        console.print("[bold]Branches:[/bold]")
        for branch in repo.branches:
            marker = "* " if branch.name == current_branch else "  "
            color = "green" if branch.name == current_branch else "white"
            console.print(f"{marker}[{color}]{branch.name}[/{color}]")

    except git.InvalidGitRepositoryError:
        echo_error("Not a git repository")

# Utility Commands
@app.command()
def pwgen(length: int = typer.Option(16, "-l", "--length"),
          count: int = typer.Option(1, "-c", "--count")):
    """Generate secure random passwords"""
    alphabet = string.ascii_letters + string.digits + string.punctuation

    console.print("[bold magenta]Generated Passwords:[/bold magenta]")
    for _ in range(count):
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        console.print(f"  • {password}")

@app.command()
def calc(expression: str):
    """Simple calculator"""
    try:
        # Safe evaluation
        allowed_chars = set("0123456789+-*/()%. ")
        if not all(c in allowed_chars for c in expression):
            echo_error("Invalid characters in expression")
            return

        result = eval(expression, {"__builtins__": {}}, {})
        console.print(f"[cyan]{expression}[/cyan] = [bold green]{result}[/bold green]")
    except Exception as e:
        echo_error(f"Calculation error: {e}")

@app.command()
def weather(city: str = typer.Argument("London")):
    """Get weather information (requires internet)"""
    try:
        import urllib.request
        url = f"http://wttr.in/{city}?format=3"
        with urllib.request.urlopen(url, timeout=5) as response:
            weather_info = response.read().decode('utf-8').strip()
            console.print(f"[cyan]{weather_info}[/cyan]")
    except Exception as e:
        echo_error(f"Could not fetch weather: {e}")

@app.command()
def encode(text: str, method: str = typer.Option("base64", "-m", "--method")):
    """Encode text (base64, hex)"""
    import base64

    if method == "base64":
        encoded = base64.b64encode(text.encode()).decode()
    elif method == "hex":
        encoded = text.encode().hex()
    else:
        echo_error(f"Unknown method: {method}")
        return

    console.print(f"Encoded ({method}): [cyan]{encoded}[/cyan]")

@app.command()
def decode(text: str, method: str = typer.Option("base64", "-m", "--method")):
    """Decode text (base64, hex)"""
    import base64

    try:
        if method == "base64":
            decoded = base64.b64decode(text).decode()
        elif method == "hex":
            decoded = bytes.fromhex(text).decode()
        else:
            echo_error(f"Unknown method: {method}")
            return

        console.print(f"Decoded ({method}): [cyan]{decoded}[/cyan]")
    except Exception as e:
        echo_error(f"Decoding failed: {e}")

@app.command()
def timestamp():
    """Show current Unix timestamp"""
    ts = int(datetime.now().timestamp())
    dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"Timestamp: [cyan]{ts}[/cyan]")
    console.print(f"Human: [yellow]{dt}[/yellow]")

@app.command()
def plugins():
    """List loaded plugins"""
    if not loaded_plugins:
        echo_info("No plugins loaded")
        return

    table = Table(title="Loaded Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="white")

    for name, module in loaded_plugins.items():
        path = getattr(module, '__file__', 'Unknown')
        table.add_row(name, path)

    console.print(table)

@app.command()
def help_cmd(command: str = typer.Argument(None)):
    """Show help for commands"""
    if command:
        # Show help for specific command
        if command in BUILTIN_COMMANDS:
            func = BUILTIN_COMMANDS[command]
            doc = func.__doc__ or "No documentation available"
            console.print(Panel(f"[bold]{command}[/bold]\n\n{doc}",
                              title="Command Help", border_style="cyan"))
        else:
            # Try typer command
            try:
                app(["--help"], standalone_mode=False)
            except SystemExit:
                pass
    else:
        # Show all commands
        console.print(Panel("[bold cyan]DeviShell - Enhanced PowerShell Experience[/bold cyan]\n\n"
                          "A feature-rich shell with advanced commands, themes, and plugins.",
                          title="DeviShell Help", border_style="cyan"))

        # Built-in commands
        console.print("\n[bold yellow]Built-in Commands:[/bold yellow]")
        for cmd in sorted(BUILTIN_COMMANDS.keys()):
            console.print(f"  • [cyan]{cmd}[/cyan]")

        # Typer commands
        console.print("\n[bold yellow]Extended Commands:[/bold yellow]")
        for cmd in app.registered_commands:
            if cmd.name:
                console.print(f"  • [cyan]{cmd.name}[/cyan]")

        console.print("\n[dim]Use 'help_cmd <command>' for detailed help[/dim]")

# ====================
# Command Execution
# ====================

def run_system_command(command: List[str]):
    """Execute PowerShell command"""
    ps_path = config.get("powershell_path", POWERSHELL_EXECUTABLE)

    if not os.path.exists(ps_path):
        echo_error(f"PowerShell executable not found at '{ps_path}'")
        return

    try:
        full_command = [ps_path, "-Command", " ".join(command)]
        subprocess.run(full_command, check=True)
    except subprocess.CalledProcessError:
        pass  # Command failed, but error already shown by PowerShell
    except KeyboardInterrupt:
        echo_warning("\nCommand interrupted")
    except Exception as e:
        echo_error(f"An unexpected error occurred: {e}")

def get_typer_commands():
    """Get dictionary of all typer commands"""
    import sys
    from io import StringIO

    # Build command registry
    commands = {}

    # Use globals to find all command functions
    for name, obj in globals().items():
        if callable(obj) and hasattr(obj, '__wrapped__'):
            # This is a typer command
            # Map the function name to the function
            commands[name.replace('_', '')] = obj  # Remove underscores for command names

    return commands

def execute_command(command: List[str]):
    """Execute a command"""
    if not command:
        return

    # Save to history
    command_history.append(" ".join(command))

    command_name = command[0].lower()
    args = command[1:]

    # Check for alias
    if command_name in aliases:
        alias_cmd = aliases[command_name]
        echo_info(f"Expanding alias: {alias_cmd}")
        command = alias_cmd.split() + args
        command_name = command[0].lower()
        args = command[1:]

    # Built-in commands
    if command_name in BUILTIN_COMMANDS:
        BUILTIN_COMMANDS[command_name](args)
        return

    # Try Typer commands using CLI invocation
    try:
        import sys
        from io import StringIO

        # Capture sys.argv
        old_argv = sys.argv
        sys.argv = [sys.argv[0]] + command

        # Try to invoke the typer app
        try:
            app(standalone_mode=False)
            return
        finally:
            sys.argv = old_argv

    except typer.Exit:
        return
    except SystemExit as e:
        if e.code == 0:
            return
        # Command might not exist, continue to plugins
    except Exception as e:
        # If it's a real error (not "command not found"), show it
        error_msg = str(e).lower()
        if "no such command" not in error_msg and "not recognized" not in error_msg:
            echo_error(f"Command error: {e}")
            return

    # Check plugins
    for plugin_name, plugin_module in loaded_plugins.items():
        if hasattr(plugin_module, 'handle_command'):
            if plugin_module.handle_command(command):
                return

    # Fallback to PowerShell
    run_system_command(command)

def execute_startup_script():
    """Execute startup script if it exists"""
    if STARTUP_SCRIPT.exists():
        echo_info("Executing startup script...")
        try:
            with open(STARTUP_SCRIPT, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        console.print(f"[dim]> {line}[/dim]")
                        execute_command(line.split())
        except Exception as e:
            echo_error(f"Startup script error: {e}")

# ====================
# Main Loop
# ====================

def main():
    """Main shell loop"""
    # Initialize
    ensure_config_dir()
    load_config()
    load_bookmarks()
    load_aliases()
    load_plugins()

    # Welcome message
    console.print(Panel.fit(
        "[bold cyan]DeviShell[/bold cyan] [white]v2.0[/white]\n"
        "[dim]The Ultimate PowerShell Experience[/dim]\n\n"
        f"Theme: [cyan]{config.get('theme', 'default')}[/cyan] | "
        f"Type [yellow]help_cmd[/yellow] for assistance",
        border_style="cyan"
    ))

    # Execute startup script
    execute_startup_script()

    # Setup prompt
    update_prompt_cache()
    typer_commands = [cmd.name for cmd in app.registered_commands if cmd.name]
    builtin_command_names = list(BUILTIN_COMMANDS.keys())
    unique_sorted_commands = sorted(list(set(typer_commands + builtin_command_names)))

    # Create session
    completer = DeviShellCompleter(unique_sorted_commands)
    session = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        completer=completer,
        style=get_style(),
        enable_history_search=True,
    )

    # Key bindings
    kb = KeyBindings()

    @kb.add('c-l')
    def _(event):
        """Clear screen with Ctrl+L"""
        shell_clear([])

    # Main loop
    while True:
        try:
            user_input = session.prompt(get_prompt_parts, key_bindings=kb)
            command_parts = user_input.strip().split()

            if command_parts:
                execute_command(command_parts)

                # Update prompt if directory changed
                current_cwd = os.getcwd()
                if PROMPT_CACHE['cwd'] != current_cwd:
                    update_prompt_cache()

        except KeyboardInterrupt:
            print()

        except EOFError:
            shell_exit([])

if __name__ == "__main__":
    main()
