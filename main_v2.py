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
import re
from pathlib import Path
from typing import List, Dict, Callable, Optional, Any
from datetime import datetime
from collections import deque

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
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
        console.print(f"[red]Failed to load config: {e}[/red]")
        config = DEFAULT_CONFIG.copy()

def save_config(cfg: Dict):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        console.print(f"[red]Failed to save config: {e}[/red]")

def load_bookmarks():
    """Load bookmarks from file"""
    global bookmarks
    try:
        with open(BOOKMARKS_FILE, 'r') as f:
            bookmarks = json.load(f)
    except Exception as e:
        console.print(f"[red]Failed to load bookmarks: {e}[/red]")
        bookmarks = {}

def save_bookmarks():
    """Save bookmarks to file"""
    try:
        with open(BOOKMARKS_FILE, 'w') as f:
            json.dump(bookmarks, f, indent=2)
    except Exception as e:
        console.print(f"[red]Failed to save bookmarks: {e}[/red]")

def load_aliases():
    """Load aliases from file"""
    global aliases
    try:
        with open(ALIASES_FILE, 'r') as f:
            aliases = json.load(f)
    except Exception as e:
        console.print(f"[red]Failed to load aliases: {e}[/red]")
        aliases = {}

def save_aliases():
    """Save aliases to file"""
    try:
        with open(ALIASES_FILE, 'w') as f:
            json.dump(aliases, f, indent=2)
    except Exception as e:
        console.print(f"[red]Failed to save aliases: {e}[/red]")

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
                    console.print(f"[green]✔ Loaded plugin: {plugin_file.stem}[/green]")
        except Exception as e:
            console.print(f"[red]✖ Failed to load plugin {plugin_file.stem}: {e}[/red]")

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

# ===================
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
# Extended Commands Registry
# ====================

EXTENDED_COMMANDS: Dict[str, Callable] = {}

def parse_args(args: List[str], expected: Dict[str, Any]) -> Dict[str, Any]:
    """Simple argument parser for commands"""
    result = {}
    i = 0

    for key, default in expected.items():
        if i < len(args):
            result[key] = args[i]
            i += 1
        else:
            result[key] = default

    return result

# Configuration Commands
def cmd_config_set(args: List[str]):
    """Set a configuration value"""
    if len(args) < 2:
        echo_error("Usage: config_set <key> <value>")
        return

    key, value = args[0], args[1]
    config[key] = value
    save_config(config)
    echo_success(f"Set {key} = {value}")

def cmd_config_get(args: List[str]):
    """Get configuration value(s)"""
    if args:
        key = args[0]
        value = config.get(key, "Not set")
        console.print(f"{key}: [cyan]{value}[/cyan]")
    else:
        table = Table(title="Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")

        for k, v in config.items():
            table.add_row(k, str(v))

        console.print(table)

def cmd_theme(args: List[str]):
    """Set or list themes"""
    if args:
        name = args[0]
        if name in THEMES:
            config["theme"] = name
            save_config(config)
            echo_success(f"Theme set to: {name}")
            echo_warning("Restart DeviShell to apply theme")
        else:
            echo_error(f"Unknown theme: {name}")
            console.print(f"Available themes: {', '.join(THEMES.keys())}")
    else:
        console.print(f"Current theme: [cyan]{config.get('theme', 'default')}[/cyan]")
        console.print(f"Available themes: {', '.join(THEMES.keys())}")

# Bookmark Commands
def cmd_bookmark(args: List[str]):
    """Bookmark current or specified directory"""
    if not args:
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
        name = args[0]
        target_path = args[1] if len(args) > 1 else os.getcwd()
        target_path = os.path.abspath(os.path.expanduser(target_path))

        if not os.path.isdir(target_path):
            echo_error(f"Not a directory: {target_path}")
            return

        bookmarks[name] = target_path
        save_bookmarks()
        echo_success(f"Bookmarked '{target_path}' as '@{name}'")

def cmd_unbookmark(args: List[str]):
    """Remove a bookmark"""
    if not args:
        echo_error("Usage: unbookmark <name>")
        return

    name = args[0]
    if name in bookmarks:
        del bookmarks[name]
        save_bookmarks()
        echo_success(f"Removed bookmark: {name}")
    else:
        echo_error(f"Bookmark not found: {name}")

# Alias Commands
def cmd_alias(args: List[str]):
    """Create or list command aliases"""
    if not args:
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
    elif len(args) == 1:
        # Show specific alias
        name = args[0]
        if name in aliases:
            console.print(f"{name}: [cyan]{aliases[name]}[/cyan]")
        else:
            echo_error(f"Alias not found: {name}")
    else:
        # Create alias
        name = args[0]
        command = " ".join(args[1:])
        aliases[name] = command
        save_aliases()
        echo_success(f"Created alias: {name} -> {command}")

def cmd_unalias(args: List[str]):
    """Remove an alias"""
    if not args:
        echo_error("Usage: unalias <name>")
        return

    name = args[0]
    if name in aliases:
        del aliases[name]
        save_aliases()
        echo_success(f"Removed alias: {name}")
    else:
        echo_error(f"Alias not found: {name}")

# File Operations (continuing in next part due to length...)
def cmd_search(args: List[str]):
    """Recursively search for files and directories"""
    if not args:
        echo_error("Usage: search <term> [-p path]")
        return

    term = args[0]
    path = "."

    # Check for -p flag
    if "-p" in args:
        idx = args.index("-p")
        if idx + 1 < len(args):
            path = args[idx + 1]

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

def cmd_tree(args: List[str]):
    """Display directory tree"""
    path = args[0] if args else "."
    max_depth = 3

    # Check for -d flag
    if "-d" in args:
        idx = args.index("-d")
        if idx + 1 < len(args):
            try:
                max_depth = int(args[idx + 1])
            except:
                pass

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

def cmd_mkcd(args: List[str]):
    """Create directory and enter it"""
    if not args:
        echo_error("Usage: mkcd <dirname>")
        return

    name = args[0]
    try:
        os.makedirs(name, exist_ok=True)
        shell_cd([name])
        echo_success(f"Created and entered directory: {os.path.abspath(name)}")
    except OSError as e:
        echo_error(f"Could not create directory: {e}")

def cmd_touch(args: List[str]):
    """Create an empty file"""
    if not args:
        echo_error("Usage: touch <filename>")
        return

    filename = args[0]
    try:
        Path(filename).touch()
        echo_success(f"Created file: {filename}")
    except Exception as e:
        echo_error(f"Failed to create file: {e}")

def cmd_cat(args: List[str]):
    """Display file contents with syntax highlighting"""
    if not args:
        echo_error("Usage: cat <filename> [-n lines]")
        return

    filename = args[0]
    lines = None

    if "-n" in args:
        idx = args.index("-n")
        if idx + 1 < len(args):
            try:
                lines = int(args[idx + 1])
            except:
                pass

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

def cmd_grep(args: List[str]):
    """Search for pattern in files"""
    if not args:
        echo_error("Usage: grep <pattern> [path] [-r]")
        return

    pattern = args[0]
    path = args[1] if len(args) > 1 else "."
    recursive = "-r" in args or len(args) > 1

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

def cmd_copy(args: List[str]):
    """Copy file or directory"""
    if len(args) < 2:
        echo_error("Usage: copy <source> <dest>")
        return

    source, dest = args[0], args[1]
    try:
        if os.path.isdir(source):
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
        echo_success(f"Copied: {source} -> {dest}")
    except Exception as e:
        echo_error(f"Copy failed: {e}")

def cmd_move(args: List[str]):
    """Move file or directory"""
    if len(args) < 2:
        echo_error("Usage: move <source> <dest>")
        return

    source, dest = args[0], args[1]
    try:
        shutil.move(source, dest)
        echo_success(f"Moved: {source} -> {dest}")
    except Exception as e:
        echo_error(f"Move failed: {e}")

def cmd_remove(args: List[str]):
    """Remove file or directory"""
    if not args:
        echo_error("Usage: remove <path> [-f]")
        return

    path = args[0]
    force = "-f" in args

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
def cmd_serve(args: List[str]):
    """Start a local HTTP server"""
    port = 8000
    path = "."

    # Parse args
    for i, arg in enumerate(args):
        if arg.isdigit():
            port = int(arg)
        elif arg == "-d" and i + 1 < len(args):
            path = args[i + 1]

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

def cmd_myip(args: List[str]):
    """Show local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        echo_info(f"Local IP: [bold white]{ip}[/bold white]")
    except Exception:
        echo_error("Could not determine local IP address")

def cmd_port_scan(args: List[str]):
    """Scan for open ports"""
    host = args[0] if args else "localhost"
    start = int(args[1]) if len(args) > 1 else 1
    end = int(args[2]) if len(args) > 2 else 1024

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
def cmd_sysinfo(args: List[str]):
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

def cmd_processes(args: List[str]):
    """List running processes"""
    limit = 20
    if "-n" in args:
        idx = args.index("-n")
        if idx + 1 < len(args):
            try:
                limit = int(args[idx + 1])
            except:
                pass

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

def cmd_kill(args: List[str]):
    """Kill a process by PID"""
    if not args:
        echo_error("Usage: kill <pid>")
        return

    try:
        pid = int(args[0])
        process = psutil.Process(pid)
        process_name = process.name()
        process.kill()
        echo_success(f"Killed process {pid} ({process_name})")
    except psutil.NoSuchProcess:
        echo_error(f"No process with PID {args[0]}")
    except psutil.AccessDenied:
        echo_error(f"Access denied to kill process {args[0]}")
    except Exception as e:
        echo_error(f"Failed to kill process: {e}")

def cmd_env(args: List[str]):
    """Get or set environment variables"""
    if not args:
        # List all environment variables
        table = Table(title="Environment Variables")
        table.add_column("Variable", style="cyan")
        table.add_column("Value", style="white")

        for key, val in sorted(os.environ.items()):
            # Truncate long values
            display_val = val if len(val) < 80 else val[:77] + "..."
            table.add_row(key, display_val)

        console.print(table)
    elif len(args) == 1:
        # Get specific variable
        var = args[0]
        val = os.environ.get(var)
        if val:
            console.print(f"{var}: [cyan]{val}[/cyan]")
        else:
            echo_warning(f"Environment variable not set: {var}")
    else:
        # Set variable
        var, value = args[0], args[1]
        os.environ[var] = value
        echo_success(f"Set {var} = {value}")

def cmd_diskusage(args: List[str]):
    """Show disk usage of directory"""
    path = args[0] if args else "."
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
def cmd_gitstatus(args: List[str]):
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

def cmd_gitlog(args: List[str]):
    """Show git log"""
    count = 10
    if "-n" in args:
        idx = args.index("-n")
        if idx + 1 < len(args):
            try:
                count = int(args[idx + 1])
            except:
                pass

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

def cmd_gitbranches(args: List[str]):
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
def cmd_pwgen(args: List[str]):
    """Generate secure random passwords"""
    length = 16
    count = 1

    if "-l" in args:
        idx = args.index("-l")
        if idx + 1 < len(args):
            try:
                length = int(args[idx + 1])
            except:
                pass

    if "-c" in args:
        idx = args.index("-c")
        if idx + 1 < len(args):
            try:
                count = int(args[idx + 1])
            except:
                pass

    alphabet = string.ascii_letters + string.digits + string.punctuation

    console.print("[bold magenta]Generated Passwords:[/bold magenta]")
    for _ in range(count):
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        console.print(f"  • {password}")

def cmd_calc(args: List[str]):
    """Simple calculator"""
    if not args:
        echo_error("Usage: calc <expression>")
        return

    expression = " ".join(args)
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

def cmd_weather(args: List[str]):
    """Get weather information (requires internet)"""
    city = args[0] if args else "London"
    try:
        import urllib.request
        url = f"http://wttr.in/{city}?format=3"
        with urllib.request.urlopen(url, timeout=5) as response:
            weather_info = response.read().decode('utf-8').strip()
            console.print(f"[cyan]{weather_info}[/cyan]")
    except Exception as e:
        echo_error(f"Could not fetch weather: {e}")

def cmd_encode(args: List[str]):
    """Encode text (base64, hex)"""
    if not args:
        echo_error("Usage: encode <text> [-m method]")
        return

    text = args[0]
    method = "base64"

    if "-m" in args:
        idx = args.index("-m")
        if idx + 1 < len(args):
            method = args[idx + 1]

    import base64

    if method == "base64":
        encoded = base64.b64encode(text.encode()).decode()
    elif method == "hex":
        encoded = text.encode().hex()
    else:
        echo_error(f"Unknown method: {method}")
        return

    console.print(f"Encoded ({method}): [cyan]{encoded}[/cyan]")

def cmd_decode(args: List[str]):
    """Decode text (base64, hex)"""
    if not args:
        echo_error("Usage: decode <text> [-m method]")
        return

    text = args[0]
    method = "base64"

    if "-m" in args:
        idx = args.index("-m")
        if idx + 1 < len(args):
            method = args[idx + 1]

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

def cmd_timestamp(args: List[str]):
    """Show current Unix timestamp"""
    ts = int(datetime.now().timestamp())
    dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"Timestamp: [cyan]{ts}[/cyan]")
    console.print(f"Human: [yellow]{dt}[/yellow]")

def cmd_plugins(args: List[str]):
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

def cmd_help(args: List[str]):
    """Show help for commands"""
    if args:
        # Show help for specific command
        command = args[0]
        if command in BUILTIN_COMMANDS:
            func = BUILTIN_COMMANDS[command]
            doc = func.__doc__ or "No documentation available"
            console.print(Panel(f"[bold]{command}[/bold]\n\n{doc}",
                              title="Command Help", border_style="cyan"))
        elif command in EXTENDED_COMMANDS:
            func = EXTENDED_COMMANDS[command]
            doc = func.__doc__ or "No documentation available"
            console.print(Panel(f"[bold]{command}[/bold]\n\n{doc}",
                              title="Command Help", border_style="cyan"))
        else:
            echo_error(f"Unknown command: {command}")
    else:
        # Show all commands
        console.print(Panel("[bold cyan]DeviShell - Enhanced PowerShell Experience[/bold cyan]\n\n"
                          "A feature-rich shell with advanced commands, themes, and plugins.",
                          title="DeviShell Help", border_style="cyan"))

        # Built-in commands
        console.print("\n[bold yellow]Built-in Commands:[/bold yellow]")
        for cmd in sorted(BUILTIN_COMMANDS.keys()):
            console.print(f"  • [cyan]{cmd}[/cyan]")

        # Extended commands
        console.print("\n[bold yellow]Extended Commands:[/bold yellow]")
        for cmd in sorted(EXTENDED_COMMANDS.keys()):
            console.print(f"  • [cyan]{cmd}[/cyan]")

        console.print("\n[dim]Use 'help <command>' for detailed help[/dim]")

# Register all extended commands
EXTENDED_COMMANDS.update({
    "config_set": cmd_config_set,
    "config_get": cmd_config_get,
    "theme": cmd_theme,
    "bookmark": cmd_bookmark,
    "unbookmark": cmd_unbookmark,
    "alias": cmd_alias,
    "unalias": cmd_unalias,
    "search": cmd_search,
    "tree": cmd_tree,
    "mkcd": cmd_mkcd,
    "touch": cmd_touch,
    "cat": cmd_cat,
    "grep": cmd_grep,
    "copy": cmd_copy,
    "move": cmd_move,
    "remove": cmd_remove,
    "serve": cmd_serve,
    "myip": cmd_myip,
    "port_scan": cmd_port_scan,
    "sysinfo": cmd_sysinfo,
    "processes": cmd_processes,
    "kill": cmd_kill,
    "env": cmd_env,
    "diskusage": cmd_diskusage,
    "gitstatus": cmd_gitstatus,
    "gitlog": cmd_gitlog,
    "gitbranches": cmd_gitbranches,
    "pwgen": cmd_pwgen,
    "calc": cmd_calc,
    "weather": cmd_weather,
    "encode": cmd_encode,
    "decode": cmd_decode,
    "timestamp": cmd_timestamp,
    "plugins": cmd_plugins,
    "help": cmd_help,
})

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

    # Extended commands
    if command_name in EXTENDED_COMMANDS:
        EXTENDED_COMMANDS[command_name](args)
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
        f"Type [yellow]help[/yellow] for assistance",
        border_style="cyan"
    ))

    # Execute startup script
    execute_startup_script()

    # Setup prompt
    update_prompt_cache()
    all_commands = list(BUILTIN_COMMANDS.keys()) + list(EXTENDED_COMMANDS.keys())
    unique_sorted_commands = sorted(list(set(all_commands)))

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
