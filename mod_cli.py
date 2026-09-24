#!/usr/bin/env python3
"""mod-cli — interactive developer CLI for the Moderator service."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Optional

import httpx
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

CONFIG_FILE = Path.home() / ".mod_cli.json"
DEFAULT_URL = "http://localhost:8000"
VERSION = "1.0.0"

# Neutral palette
C_PRIMARY   = "#9ca3af"
C_DIM       = "#4b5563"
C_BLUE      = "#60a5fa"
C_GREEN     = "#34d399"
C_AMBER     = "#fbbf24"
C_RED       = "#f87171"
C_PINK      = "#f9a8d4"

# Provider brand colours (CLAUDE.md spec)
C_ANTHROPIC = "#D97757"
C_OPENAI    = "#FFFFFF"
C_GEMINI    = "#4285F4"

PROVIDER_COLORS = {
    "anthropic": C_ANTHROPIC,
    "openai":    C_OPENAI,
    "gemini":    C_GEMINI,
}
PROVIDER_LABELS = {
    "anthropic": "Anthropic Claude",
    "openai":    "OpenAI",
    "gemini":    "Google Gemini",
}
PROVIDER_URLS = {
    "anthropic": "console.anthropic.com/settings/keys",
    "openai":    "platform.openai.com/api-keys",
    "gemini":    "aistudio.google.com/app/apikey",
}
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai":    "gpt-4o-mini",
    "gemini":    "gemini-1.5-flash",
}

console = Console()
SEP = f"  [dim]{'─' * 60}[/dim]"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def mask(value: Optional[str], visible: int = 8) -> str:
    if not value:
        return "not set"
    return value[:visible] + "••••••••"


def get_client(cfg: dict) -> httpx.Client:
    return httpx.Client(base_url=cfg.get("url", DEFAULT_URL), timeout=15.0)


# ---------------------------------------------------------------------------
# Welcome panel
# ---------------------------------------------------------------------------

def _build_welcome_panel(cfg: dict) -> Panel:
    token    = cfg.get("token")
    name     = cfg.get("name") or cfg.get("email", "")
    provider = cfg.get("provider", "")

    left_lines: list[str] = []

    if token:
        display_name = name.split("@")[0] if "@" in name else name
        left_lines.append(f"[bold white]Welcome back, {display_name}[/bold white]")
        if provider:
            p_color = PROVIDER_COLORS.get(provider, C_PRIMARY)
            p_label = PROVIDER_LABELS.get(provider, provider.capitalize())
            model   = cfg.get("model") or DEFAULT_MODELS.get(provider, "")
            model_short = model.split("-")[0].capitalize() if model else ""
            left_lines.append(f"[{p_color}]{p_label}[/] · [{C_DIM}]{model_short}[/]")
        left_lines.append("")
        left_lines.append(f"[{C_DIM}]Quick start[/]")
        left_lines.append(f"  [{C_GREEN}]✓[/] Account connected")
        if provider:
            left_lines.append(f"  [{C_GREEN}]✓[/] Provider connected")
            left_lines.append(f"  [{C_DIM}]·[/] key create <app> <email>")
        else:
            left_lines.append(f"  [{C_AMBER}]·[/] Connect a provider  [{C_DIM}](type /)[/]")
    else:
        left_lines.append("[bold white]Welcome to mod[/bold white]")
        left_lines.append(f"[{C_DIM}]AI-powered message moderation[/]")
        left_lines.append("")
        left_lines.append(f"[{C_DIM}]Simple. Fast. Bring your[/]")
        left_lines.append(f"[{C_DIM}]own AI key.[/]")

    right_lines = [
        f"[{C_DIM}]Tips[/]",
        f"[{C_DIM}]· Use / for settings[/]",
        f"[{C_DIM}]· mod <user> <msg>[/]",
        f"[{C_DIM}]· violations --user u[/]",
        f"[{C_DIM}]· key create <app> <email>[/]",
    ]

    left_text  = Text.from_markup("\n".join(left_lines))
    right_text = Text.from_markup("\n".join(right_lines))

    cols = Columns([left_text, right_text], expand=True, equal=True)
    return Panel(
        cols,
        title=f"[bold white]mod v{VERSION}[/bold white]",
        title_align="left",
        border_style="blue",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def print_welcome(cfg: dict) -> None:
    console.print(_build_welcome_panel(cfg))
    console.print()


# ---------------------------------------------------------------------------
# Arrow-key selection helper
# ---------------------------------------------------------------------------

def _arrow_select(
    options: list[str],
    prompt: str = "",
    colors: Optional[list[str]] = None,
) -> Optional[int]:
    """Render a list of options with arrow-key navigation.

    Returns the selected index or None if cancelled.
    Falls back to numbered input in non-TTY environments.
    """
    if not sys.stdin.isatty():
        if prompt:
            console.print(f"\n  {prompt}\n")
        for i, opt in enumerate(options):
            console.print(f"  [{C_DIM}]{i + 1}.[/] {opt}")
        try:
            raw = console.input(f"  [{C_BLUE}]Enter number:[/] ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except (ValueError, KeyboardInterrupt, EOFError):
            pass
        return None

    try:
        import termios
        import tty
    except ImportError:
        # Windows — fall back to numbered input
        for i, opt in enumerate(options):
            console.print(f"  [{C_DIM}]{i + 1}.[/] {opt}")
        try:
            raw = console.input(f"  [{C_BLUE}]Enter number:[/] ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except (ValueError, KeyboardInterrupt, EOFError):
            pass
        return None

    if prompt:
        console.print(f"\n  {prompt}\n")

    selected = 0
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def _render(sel: int) -> None:
        sys.stdout.write(f"\033[{len(options)}A")
        sys.stdout.flush()
        for i, opt in enumerate(options):
            col = colors[i] if colors else C_PRIMARY
            if i == sel:
                console.print(f"  [bold {col}]> {opt}[/]")
            else:
                console.print(f"  [{C_DIM}]  {opt}[/]")

    for i, opt in enumerate(options):
        col = colors[i] if colors else C_PRIMARY
        if i == 0:
            console.print(f"  [bold {col}]> {opt}[/]")
        else:
            console.print(f"  [{C_DIM}]  {opt}[/]")

    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        selected = (selected - 1) % len(options)
                        _render(selected)
                    elif ch3 == "B":
                        selected = (selected + 1) % len(options)
                        _render(selected)
                else:
                    return None  # Escape
            elif ch in ("\r", "\n"):
                console.print()
                return selected
            elif ch in ("\x03", "\x04"):
                raise KeyboardInterrupt
    except KeyboardInterrupt:
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ---------------------------------------------------------------------------
# Auth flows
# ---------------------------------------------------------------------------

def _prompt_password(label: str = "Password") -> str:
    try:
        return getpass.getpass(f"  {label}: ")
    except (KeyboardInterrupt, EOFError):
        console.print()
        return ""


def _fetch_and_store_profile(cfg: dict, client: httpx.Client, token: str) -> None:
    try:
        r = client.get("/providers/me", headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            providers = r.json()
            if providers:
                p = providers[0]
                cfg["provider"] = p["provider"]
                cfg["model"]    = p["model"]
    except Exception:
        pass


def flow_login(cfg: dict) -> bool:
    """Interactive login. Returns True on success."""
    console.print(f"\n  [{C_BLUE}]Login[/]\n")
    try:
        email = console.input(f"  [{C_DIM}]Email:[/]    ").strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False
    password = _prompt_password()
    if not email or not password:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]Email and password are required[/]")
        return False
    with get_client(cfg) as client:
        try:
            r = client.post("/auth/login", json={"email": email, "password": password})
            if r.status_code == 401:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]Invalid email or password[/]")
                return False
            if r.status_code == 403:
                detail = r.json().get("detail", "")
                if "not verified" in detail.lower():
                    console.print(f"  [{C_AMBER}]⚠[/]  [{C_AMBER}]Email not verified — enter your OTP[/]")
                    return flow_verify_otp(cfg, email)
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{detail}[/]")
                return False
            r.raise_for_status()
            token = r.json()["access_token"]
            cfg["token"] = token
            cfg["email"] = email
            _fetch_and_store_profile(cfg, client, token)
            save_config(cfg)
            name = cfg.get("name") or email
            console.print(f"\n  [{C_GREEN}]✓[/]  [{C_GREEN}]Logged in as {name}[/]")
            return True
        except httpx.ConnectError:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]Cannot reach server — is it running?[/]")
            return False
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")
            return False


def flow_register(cfg: dict) -> bool:
    """Interactive account creation. Returns True when verified and logged in."""
    console.print(f"\n  [{C_BLUE}]Create account[/]\n")
    try:
        email    = console.input(f"  [{C_DIM}]Email:[/]     ").strip()
        password = _prompt_password()
        confirm  = _prompt_password("Confirm")
        name     = console.input(f"  [{C_DIM}]Name:[/]      [{C_DIM}](optional)[/] ").strip() or None
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False
    if not email or not password:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]Email and password are required[/]")
        return False
    if password != confirm:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]Passwords do not match[/]")
        return False
    with get_client(cfg) as client:
        try:
            r = client.post(
                "/auth/register",
                json={"email": email, "password": password, "full_name": name},
            )
            if r.status_code == 409:
                console.print(f"  [{C_AMBER}]⚠[/]  [{C_AMBER}]Email already registered — logging in instead[/]")
                cfg["email"] = email
                return flow_login(cfg)
            r.raise_for_status()
            console.print(f"\n  [{C_GREEN}]✓[/]  [{C_GREEN}]Account created — check your email for your OTP[/]")
            return flow_verify_otp(cfg, email)
        except httpx.ConnectError:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]Cannot reach server — is it running?[/]")
            return False
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")
            return False


def flow_verify_otp(cfg: dict, email: str) -> bool:
    """Prompt for OTP, verify it, store JWT. Returns True on success."""
    console.print(f"\n  Enter the 6-digit code sent to [{C_BLUE}]{email}[/]\n")
    try:
        otp = console.input(f"  [{C_DIM}]Code:[/]  ").strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False
    with get_client(cfg) as client:
        try:
            r = client.post("/auth/verify", json={"email": email, "otp": otp})
            if r.status_code == 400:
                detail = r.json().get("detail", "Invalid code")
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{detail}[/]")
                return False
            r.raise_for_status()
            token = r.json()["access_token"]
            cfg["token"] = token
            cfg["email"] = email
            _fetch_and_store_profile(cfg, client, token)
            save_config(cfg)
            console.print(f"  [{C_GREEN}]✓[/]  [{C_GREEN}]Email verified[/]")
            return True
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")
            return False


def flow_connect_provider(cfg: dict) -> bool:
    """Interactive provider selection and key entry. Returns True on success."""
    token = cfg.get("token")
    if not token:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]You must be logged in first[/]")
        return False

    providers  = ["Anthropic Claude", "OpenAI", "Google Gemini"]
    prov_keys  = ["anthropic", "openai", "gemini"]
    colors     = [C_ANTHROPIC, C_OPENAI, C_GEMINI]

    idx = _arrow_select(providers, prompt="Pick your AI provider", colors=colors)
    if idx is None:
        return False

    chosen = prov_keys[idx]
    label  = providers[idx]
    url    = PROVIDER_URLS[chosen]
    col    = PROVIDER_COLORS[chosen]

    console.print(f"\n  [{col}]{label}[/]\n")
    console.print(f"  [{C_DIM}]1. Open   →[/]  [{C_BLUE}]{url}[/]")
    console.print(f"  [{C_DIM}]2. Click  →[/]  [{C_PRIMARY}]\"Create Key\"[/]")
    console.print(f"  [{C_DIM}]3. Paste your key below[/]\n")

    try:
        api_key = getpass.getpass("  API Key: ").strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False
    if not api_key:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]No key provided[/]")
        return False

    with get_client(cfg) as client:
        try:
            r = client.post(
                "/providers/connect",
                json={"provider": chosen, "api_key": api_key},
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 422:
                detail = r.json().get("detail", "Validation failed")
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{detail}[/]")
                return False
            r.raise_for_status()
            data = r.json()
            cfg["provider"] = chosen
            cfg["model"]    = data.get("model", DEFAULT_MODELS.get(chosen, ""))
            save_config(cfg)
            model_short = cfg["model"].split("-")[0].capitalize()
            console.print(f"\n  [{C_GREEN}]✓[/]  [{C_GREEN}]Key validated — {label} {model_short} connected[/]")
            return True
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")
            return False


def first_run_flow(cfg: dict) -> None:
    """Guide a new user through login or account creation."""
    options = ["Login", "Create account"]
    idx = _arrow_select(options)
    if idx is None:
        return
    ok = flow_login(cfg) if idx == 0 else flow_register(cfg)
    if ok and not cfg.get("provider"):
        console.print()
        console.print(f"  [{C_DIM}]No provider connected yet.[/]  [{C_AMBER}]Let's set one up.[/]\n")
        flow_connect_provider(cfg)


# ---------------------------------------------------------------------------
# Settings slash menu (opened by typing /)
# ---------------------------------------------------------------------------

def settings_menu(cfg: dict) -> None:
    console.print(f"\n  [{C_BLUE}]/[/]  Settings\n")
    options = [
        "Switch AI provider",
        "Rotate API key",
        "Disconnect provider",
        "Change model",
        "Account details",
        "Logout",
    ]
    idx = _arrow_select(options)
    if idx is None:
        console.print(f"  [{C_DIM}]dismissed[/]")
        return
    choice = options[idx]
    if choice in ("Switch AI provider", "Rotate API key"):
        flow_connect_provider(cfg)
    elif choice == "Disconnect provider":
        _settings_disconnect(cfg)
    elif choice == "Change model":
        _settings_change_model(cfg)
    elif choice == "Account details":
        _settings_account(cfg)
    elif choice == "Logout":
        _settings_logout(cfg)


def _settings_disconnect(cfg: dict) -> None:
    token    = cfg.get("token")
    provider = cfg.get("provider")
    if not token or not provider:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]No provider connected[/]")
        return
    with get_client(cfg) as client:
        try:
            r = client.request(
                "DELETE", "/providers/disconnect",
                json={"provider": provider, "model": cfg.get("model", "")},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            cfg.pop("provider", None)
            cfg.pop("model", None)
            save_config(cfg)
            console.print(f"  [{C_GREEN}]✓[/]  Provider disconnected")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def _settings_change_model(cfg: dict) -> None:
    token    = cfg.get("token")
    provider = cfg.get("provider")
    if not token or not provider:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]No provider connected[/]")
        return
    try:
        model = console.input(
            f"  [{C_DIM}]New model (current: {cfg.get('model', '?')}):[/] "
        ).strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        return
    if not model:
        return
    with get_client(cfg) as client:
        try:
            r = client.patch(
                "/providers/switch-model",
                json={"provider": provider, "model": model},
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            cfg["model"] = model
            save_config(cfg)
            console.print(f"  [{C_GREEN}]✓[/]  Model updated to [{C_PRIMARY}]{model}[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def _settings_account(cfg: dict) -> None:
    console.print()
    console.print(f"  [{C_DIM}]email[/]     [{C_PRIMARY}]{cfg.get('email', 'not set')}[/]")
    if cfg.get("name"):
        console.print(f"  [{C_DIM}]name[/]      [{C_PRIMARY}]{cfg['name']}[/]")
    console.print(f"  [{C_DIM}]provider[/]  [{C_PRIMARY}]{cfg.get('provider', 'none')}[/]")
    if cfg.get("model"):
        console.print(f"  [{C_DIM}]model[/]     [{C_PRIMARY}]{cfg['model']}[/]")


def _settings_logout(cfg: dict) -> None:
    token = cfg.get("token")
    if not token:
        console.print(f"  [{C_DIM}]Not logged in[/]")
        return
    with get_client(cfg) as client:
        try:
            client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        except Exception:
            pass
    for k in ("token", "email", "name", "provider", "model"):
        cfg.pop(k, None)
    save_config(cfg)
    console.print(f"  [{C_GREEN}]✓[/]  Logged out")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_help() -> None:
    console.print()
    sections = [
        ("connection", [
            ("health", "ping /health — show service status"),
        ]),
        ("keys", [
            ("key create <app> <email>", "create a new API key"),
            ("key test <raw-key>",       "verify a key is valid and active"),
            ("key list",                 "list all registered keys"),
            ("key revoke <app>",         "deactivate a key by app name"),
        ]),
        ("moderation", [
            ("mod <user-id> <message>",  "moderate a message as the given user"),
        ]),
        ("admin", [
            ("violations [--user u] [--limit n]", "list violation logs"),
            ("users [--flagged]",                 "list users with violations"),
            ("unban <user-id>",                   "reset a user's strikes and clear ban"),
        ]),
        ("account", [
            ("/",            "open settings menu"),
            ("clear",        "clear the terminal"),
            ("exit / quit",  "exit the CLI"),
        ]),
    ]
    for section, cmds in sections:
        console.print(f"  [{C_DIM}]{section}[/]")
        for name, desc in cmds:
            console.print(f"    [{C_BLUE}]{name:<44}[/] [{C_PRIMARY}]{desc}[/]")
        console.print()


def _parse_error_response(response: httpx.Response) -> str:
    try:
        data   = response.json()
        detail = data.get("detail", "")
        if isinstance(detail, str):
            d = detail.lower()
            if "invalid" in d and "api key" in d:
                return "API key is invalid or has been revoked"
            if "expired" in d:
                return "API key has expired"
            if "missing" in d and "api key" in d:
                return "no API key — use key create <app> <email>"
            if "admin" in d:
                return "invalid admin secret"
            return detail
        return str(detail)
    except Exception:
        return response.text


def cmd_health(cfg: dict) -> None:
    with get_client(cfg) as client:
        try:
            r = client.get("/health")
            r.raise_for_status()
            data    = r.json()
            service = data.get("service", "moderator")
            version = data.get("version", "?")
            status  = data.get("status", "?")
            console.print(
                f"  [{C_GREEN}]●[/]  [{C_PRIMARY}]{service} v{version}[/]  [{C_DIM}]—[/]  [{C_GREEN}]{status}[/]"
            )
        except httpx.ConnectError:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]cannot reach {cfg.get('url', DEFAULT_URL)} — is the server running?[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def _get_admin_secret(cfg: dict) -> Optional[str]:
    secret = cfg.get("secret")
    if not secret:
        try:
            secret = console.input(f"  [{C_DIM}]Admin secret:[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return None
        if secret:
            cfg["secret"] = secret
            save_config(cfg)
    return secret or None


def cmd_key_create(cfg: dict, app_name: str, owner_email: str) -> None:
    secret = _get_admin_secret(cfg)
    if not secret:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]admin secret required[/]")
        return
    with get_client(cfg) as client:
        try:
            r = client.post(
                "/admin/keys",
                json={"app_name": app_name, "owner_email": owner_email},
                headers={"X-Admin-Secret": secret},
            )
            if r.status_code == 401:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]invalid admin secret[/]")
                return
            r.raise_for_status()
            raw_key = r.json()["raw_key"]
            console.print(f"  [{C_GREEN}]✓[/]  [{C_PRIMARY}]key created for[/] [{C_BLUE}]{app_name}[/]")
            console.print()
            console.print(f"     [{C_PINK}]{raw_key}[/]")
            console.print(f"     [{C_DIM}]← use this key in your app (X-API-Key header)[/]")
        except httpx.HTTPStatusError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{_parse_error_response(e.response)}[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def cmd_key_test(cfg: dict, raw_key: str) -> None:
    with get_client(cfg) as client:
        try:
            r = client.post(
                "/moderate",
                json={"user_id": "cli-key-test", "message": "hello"},
                headers={"X-API-Key": raw_key},
            )
            if r.status_code in (401, 403):
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]key is invalid or has been revoked[/]")
                return
            r.raise_for_status()
            info_r = client.get("/keys/me", headers={"X-API-Key": raw_key})
            console.print(f"  [{C_GREEN}]✓[/]  [{C_PRIMARY}]key is valid and active[/]")
            if info_r.status_code == 200:
                info = info_r.json()
                console.print(
                    f"     [{C_DIM}]app[/]    [{C_PRIMARY}]{info['app_name']}[/]\n"
                    f"     [{C_DIM}]owner[/]  [{C_PRIMARY}]{info['owner_email']}[/]"
                )
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def cmd_key_list(cfg: dict) -> None:
    secret = _get_admin_secret(cfg)
    if not secret:
        return
    with get_client(cfg) as client:
        try:
            r = client.get("/admin/keys", headers={"X-Admin-Secret": secret})
            if r.status_code == 401:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]invalid admin secret[/]")
                return
            r.raise_for_status()
            keys = r.json()
            if not keys:
                console.print(f"  [{C_DIM}](no keys found)[/]")
                return
            t = Table(box=box.SIMPLE, style=C_DIM, header_style=C_DIM, show_header=True)
            t.add_column("app",     style=C_PRIMARY)
            t.add_column("owner",   style=C_PRIMARY)
            t.add_column("created", style=C_PRIMARY)
            t.add_column("active",  style=C_PRIMARY)
            for k in keys:
                created = k["created_at"][:10] if k.get("created_at") else ""
                active  = f"[{C_GREEN}]✓  yes[/]" if k.get("is_active") else f"[{C_RED}]✗  revoked[/]"
                t.add_row(k.get("app_name", ""), k.get("owner_email", ""), created, active)
            console.print(t)
        except httpx.HTTPStatusError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{_parse_error_response(e.response)}[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def cmd_key_revoke(cfg: dict, app_name: str) -> None:
    secret = _get_admin_secret(cfg)
    if not secret:
        return
    try:
        answer = console.input(f"  [{C_AMBER}]revoke key for \"{app_name}\"? [y/N][/] ")
    except (KeyboardInterrupt, EOFError):
        console.print()
        return
    if answer.strip().lower() != "y":
        console.print(f"  [{C_DIM}]cancelled[/]")
        return
    with get_client(cfg) as client:
        try:
            r = client.patch(
                f"/admin/keys/{app_name}/revoke",
                headers={"X-Admin-Secret": secret},
            )
            if r.status_code == 401:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]invalid admin secret[/]")
                return
            r.raise_for_status()
            console.print(f"  [{C_GREEN}]✓[/]  [{C_PRIMARY}]key for {app_name} revoked[/]")
        except httpx.HTTPStatusError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{_parse_error_response(e.response)}[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def cmd_mod(cfg: dict, user_id: str, message: str) -> None:
    key = cfg.get("key") or os.environ.get("MOD_API_KEY", "")
    if not key:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]API key not set — use key create <app> <email> to create one[/]")
        return
    with get_client(cfg) as client:
        try:
            r = client.post(
                "/moderate",
                json={"user_id": user_id, "message": message},
                headers={"X-API-Key": key},
            )
            if r.status_code == 401:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]API key is invalid or has been revoked[/]")
                return
            if r.status_code == 403:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]API key is inactive or expired[/]")
                return
            r.raise_for_status()
            data = r.json()
            if data.get("safe"):
                console.print(f"  [{C_GREEN}]✓[/]  [{C_GREEN}]safe[/]")
            elif data.get("flagged") and data.get("strike_count") is None:
                console.print(f"  [{C_RED}]⛔[/]  [{C_RED}]account permanently restricted[/]")
            else:
                count    = data.get("strike_count", "?")
                reason   = data.get("reason") or ""
                severity = data.get("severity") or ""
                warning  = data.get("warning") or ""
                console.print(f"  [{C_AMBER}]⚠[/]  [{C_AMBER}]strike {count}/5[/]")
                if reason:
                    console.print(f"     [{C_DIM}]reason[/]    [{C_PRIMARY}]{reason}[/]")
                if severity:
                    console.print(f"     [{C_DIM}]severity[/]  [{C_PRIMARY}]{severity}[/]")
                if warning:
                    console.print(f"     [{C_DIM}]warning[/]   [{C_PRIMARY}]{warning}[/]")
        except httpx.HTTPStatusError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{_parse_error_response(e.response)}[/]")
        except httpx.ConnectError:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]cannot reach server — is Docker running?[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def cmd_violations(cfg: dict, user: Optional[str], limit: int) -> None:
    secret = _get_admin_secret(cfg)
    if not secret:
        return
    params: dict = {"limit": limit}
    if user:
        params["user_id"] = user
    with get_client(cfg) as client:
        try:
            r = client.get(
                "/admin/violations",
                headers={"X-Admin-Secret": secret},
                params=params,
            )
            if r.status_code == 401:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]invalid admin secret[/]")
                return
            r.raise_for_status()
            rows = r.json()
            if not rows:
                console.print(f"  [{C_DIM}](no violations found)[/]")
                return
            t = Table(box=box.SIMPLE, style=C_DIM, header_style=C_DIM)
            t.add_column("user",    style=C_PRIMARY)
            t.add_column("sev",     style=C_PRIMARY)
            t.add_column("reason",  style=C_PRIMARY)
            t.add_column("message", style=C_PRIMARY)
            t.add_column("at",      style=C_PRIMARY)
            for row in rows:
                msg = row.get("message_text", "")
                if len(msg) > 30:
                    msg = msg[:27] + "..."
                ts = (row.get("created_at", "") or "")[:16].replace("T", " ")
                t.add_row(
                    row.get("user_id", ""),
                    row.get("severity", ""),
                    row.get("reason", ""),
                    msg, ts,
                )
            console.print(t)
        except httpx.HTTPStatusError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{_parse_error_response(e.response)}[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def cmd_users(cfg: dict, flagged: bool) -> None:
    secret = _get_admin_secret(cfg)
    if not secret:
        return
    params: dict = {}
    if flagged:
        params["flagged_only"] = "true"
    with get_client(cfg) as client:
        try:
            r = client.get(
                "/admin/users",
                headers={"X-Admin-Secret": secret},
                params=params,
            )
            if r.status_code == 401:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]invalid admin secret[/]")
                return
            r.raise_for_status()
            rows = r.json()
            if not rows:
                console.print(f"  [{C_DIM}](no users found)[/]")
                return
            t = Table(box=box.SIMPLE, style=C_DIM, header_style=C_DIM)
            t.add_column("user_id",    style=C_PRIMARY)
            t.add_column("strikes",    style=C_PRIMARY)
            t.add_column("flagged",    style=C_PRIMARY)
            t.add_column("flagged_at", style=C_PRIMARY)
            for row in rows:
                is_flagged_row = row.get("flagged", False)
                uid_text  = Text(row.get("user_id", ""), style=C_RED if is_flagged_row else C_PRIMARY)
                flag_text = f"[{C_RED}]⛔  yes[/]" if is_flagged_row else f"[{C_GREEN}]✓  no[/]"
                fat       = (row.get("flagged_at") or "")[:10]
                t.add_row(uid_text, str(row.get("count", 0)), flag_text, fat)
            console.print(t)
        except httpx.HTTPStatusError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{_parse_error_response(e.response)}[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


def cmd_unban(cfg: dict, user_id: str) -> None:
    secret = _get_admin_secret(cfg)
    if not secret:
        return
    try:
        answer = console.input(f"  [{C_AMBER}]unban {user_id}? [y/N][/] ")
    except (KeyboardInterrupt, EOFError):
        console.print()
        return
    if answer.strip().lower() != "y":
        console.print(f"  [{C_DIM}]cancelled[/]")
        return
    with get_client(cfg) as client:
        try:
            r = client.patch(
                f"/admin/users/{user_id}/unban",
                headers={"X-Admin-Secret": secret},
            )
            if r.status_code == 401:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]invalid admin secret[/]")
                return
            r.raise_for_status()
            console.print(f"  [{C_GREEN}]✓[/]  [{C_PRIMARY}]{user_id} unbanned — strikes reset to 0[/]")
        except httpx.HTTPStatusError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{_parse_error_response(e.response)}[/]")
        except httpx.HTTPError as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]{e}[/]")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(line: str, cfg: dict) -> bool:
    try:
        parts = shlex.split(line.strip())
    except ValueError as e:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]parse error: {e}[/]")
        console.print(SEP)
        return True
    if not parts:
        return True
    cmd = parts[0].lower()

    if cmd in ("exit", "quit"):
        return False
    elif cmd == "/":
        settings_menu(cfg)
    elif cmd == "help":
        cmd_help()
    elif cmd == "health":
        cmd_health(cfg)
    elif cmd == "clear":
        os.system("clear")
        return True
    elif cmd == "key":
        if len(parts) < 2:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]usage: key create|test|list|revoke ...[/]")
        elif parts[1] == "create":
            if len(parts) < 4:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]usage: key create <app-name> <owner-email>[/]")
            else:
                cmd_key_create(cfg, parts[2], parts[3])
        elif parts[1] == "test":
            if len(parts) < 3:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]usage: key test <raw-key>[/]")
            else:
                cmd_key_test(cfg, parts[2])
        elif parts[1] == "list":
            cmd_key_list(cfg)
        elif parts[1] == "revoke":
            if len(parts) < 3:
                console.print(f"  [{C_RED}]✗[/]  [{C_RED}]usage: key revoke <app-name>[/]")
            else:
                cmd_key_revoke(cfg, parts[2])
        else:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]unknown key subcommand: {parts[1]}[/]")
    elif cmd == "mod":
        if len(parts) < 3:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]usage: mod <user-id> <message>[/]")
        else:
            cmd_mod(cfg, parts[1], " ".join(parts[2:]))
    elif cmd == "violations":
        p = argparse.ArgumentParser(prog="violations", add_help=False)
        p.add_argument("--user",  default=None)
        p.add_argument("--limit", type=int, default=50)
        try:
            args, _ = p.parse_known_args(parts[1:])
            cmd_violations(cfg, args.user, args.limit)
        except SystemExit:
            pass
    elif cmd == "users":
        p = argparse.ArgumentParser(prog="users", add_help=False)
        p.add_argument("--flagged", action="store_true")
        try:
            args, _ = p.parse_known_args(parts[1:])
            cmd_users(cfg, args.flagged)
        except SystemExit:
            pass
    elif cmd == "unban":
        if len(parts) < 2:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]usage: unban <user-id>[/]")
        else:
            cmd_unban(cfg, parts[1])
    elif cmd == "set":
        # Legacy commands — redirect with friendly hints
        sub = parts[1] if len(parts) > 1 else ""
        if sub in ("url", "key", "secret"):
            console.print(
                f"  [{C_DIM}]'set {sub}' is no longer needed.[/]  "
                f"[{C_AMBER}]Use / to open settings or login first.[/]"
            )
        elif sub == "show":
            _settings_account(cfg)
        else:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]unknown: set {sub}[/]")
    else:
        console.print(f"  [{C_RED}]✗[/]  [{C_RED}]unknown command: {cmd}  (type help)[/]")

    console.print(SEP)
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="mod-cli — Moderator developer CLI")
    parser.add_argument("--url", default=None)
    args = parser.parse_args()

    cfg = load_config()
    if args.url:
        cfg["url"] = args.url

    os.system("clear")
    print_welcome(cfg)

    if not cfg.get("token"):
        console.print(SEP)
        console.print()
        try:
            first_run_flow(cfg)
        except (KeyboardInterrupt, EOFError):
            console.print()
        console.print()
        os.system("clear")
        print_welcome(cfg)

    console.print(SEP)
    console.print()

    while True:
        try:
            line = console.input(f"[{C_BLUE}]mod ❯[/] ")
        except (KeyboardInterrupt, EOFError):
            console.print()
            console.print(SEP)
            console.print(f"  [{C_DIM}]bye[/]")
            console.print(SEP)
            break
        try:
            if not dispatch(line, cfg):
                console.print(SEP)
                console.print(f"  [{C_DIM}]bye[/]")
                console.print(SEP)
                break
        except Exception as e:
            console.print(f"  [{C_RED}]✗[/]  [{C_RED}]unexpected error: {e}[/]")
            console.print(SEP)


if __name__ == "__main__":
    main()
