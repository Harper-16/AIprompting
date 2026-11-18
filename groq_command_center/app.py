from __future__ import annotations

import asyncio
import os
import pty
import signal
import subprocess
import time
import tty
from dataclasses import dataclass
from datetime import datetime
from openai import AsyncOpenAI
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, RichLog, Static


SYSTEM_PROMPT = (
    "You are a helpful coding and prompt-engineering assistant. Be clear, "
    "practical, and honest about uncertainty. Do not claim to run commands "
    "or inspect files unless the user provides the output."
)


@dataclass
class ShellSession:
    session_id: int
    process: subprocess.Popen[bytes]
    master_fd: int
    pane: Vertical
    output: RichLog
    prompt: Input
    label: str


class CommandCenter(App[None]):
    TITLE = "NEXUS // GROQ COMMAND CENTER"
    SUB_TITLE = "STREAMING AGENT  •  LOCAL SHELL"

    CSS = """
    Screen {
        background: #080d12;
        color: #d7e1e9;
    }
    Header {
        background: #0b151d;
        color: #53e0d0;
        height: 1;
    }
    Footer {
        background: #0b151d;
        color: #7f96a6;
    }
    #topline {
        height: 1;
        padding: 0 1;
        color: #849aa8;
        background: #101923;
    }
    #workspace {
        height: 1fr;
        padding: 1;
        layout: horizontal;
    }
    #agent-column {
        width: 1fr;
        min-width: 38;
        border: round #1f897f;
        margin-right: 1;
        padding: 0 1;
    }
    #terminal-column {
        width: 1fr;
        min-width: 38;
        border: round #375c78;
        padding: 0 1;
    }
    .section-title {
        height: 1;
        color: #53e0d0;
        text-style: bold;
        padding: 0 1;
    }
    #agent-subtitle, #terminal-subtitle {
        height: 1;
        color: #8297a5;
        padding: 0 1;
    }
    #chat-log {
        height: 1fr;
        border: round #1c3441;
        background: #0a1118;
        padding: 0 1;
        scrollbar-color: #246e70;
    }
    #assistant-live {
        height: auto;
        max-height: 12;
        color: #d7e1e9;
        padding: 0 1;
    }
    #agent-input {
        height: 3;
        border: round #278f83;
        margin-top: 1;
    }
    #agent-status {
        height: 1;
        color: #58d9a4;
        padding: 0 1;
    }
    #activity-log {
        height: 9;
        border: round #263d4c;
        background: #0a1118;
        padding: 0 1;
        margin-bottom: 1;
    }
    #terminal-tabs {
        height: 3;
        align: left middle;
    }
    .tab-button {
        min-width: 10;
        height: 3;
        margin-right: 0;
        background: #14222d;
        color: #9ab1bf;
        border: tall #263d4c;
    }
    .tab-button.active {
        color: #53e0d0;
        background: #102b30;
        border: tall #278f83;
    }
    .close-button {
        width: 3;
        min-width: 3;
        height: 3;
        margin-right: 1;
        background: #18212a;
        color: #e68b7d;
        border: tall #49333a;
    }
    #new-tab {
        min-width: 5;
        height: 3;
        background: #102b30;
        color: #53e0d0;
        border: tall #278f83;
    }
    #terminal-stack {
        height: 1fr;
        border: round #1c3441;
        background: #0a1118;
    }
    .terminal-pane {
        height: 1fr;
        padding: 0 1;
    }
    .terminal-output {
        height: 1fr;
        background: #0a1118;
        padding: 0 1;
    }
    .shell-prompt {
        height: 3;
        border: round #375c78;
        margin-top: 1;
    }
    #terminal-controls {
        height: 3;
        align: right middle;
    }
    #interrupt {
        width: 14;
        height: 3;
        color: #f2b66d;
        background: #2a2018;
        border: tall #745534;
    }
    #hint {
        height: 1;
        color: #687f8c;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+n", "new_terminal", "New terminal"),
        ("ctrl+tab", "next_terminal", "Next terminal"),
        ("ctrl+shift+tab", "previous_terminal", "Previous terminal"),
        ("ctrl+l", "clear_terminal", "Clear terminal"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.sessions: dict[int, ShellSession] = {}
        self.active_session_id: int | None = None
        self._next_session_id = 1
        self._busy = False
        self._history: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self._client: AsyncOpenAI | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "● LINK: LOCAL SHELL   ● MODEL: GROQ STREAM   ● MODE: INTERACTIVE",
            id="topline",
        )
        with Horizontal(id="workspace"):
            with Vertical(id="agent-column"):
                yield Static("01  /  AGENT INTERFACE", classes="section-title")
                yield Static(
                    "Responses stream live. Activity shows operational status, not hidden reasoning.",
                    id="agent-subtitle",
                )
                yield RichLog(id="chat-log", wrap=True, markup=False, highlight=False)
                yield Static("", id="assistant-live")
                yield Input(
                    placeholder="Ask the agent anything…  [Enter to send]",
                    id="agent-input",
                )
                yield Static("● READY  //  waiting for input", id="agent-status")
            with Vertical(id="terminal-column"):
                yield Static("02  /  TERMINAL ARRAY", classes="section-title")
                yield Static(
                    "Each tab has its own persistent shell session.",
                    id="terminal-subtitle",
                )
                yield RichLog(id="activity-log", wrap=True, markup=False)
                yield Horizontal(id="terminal-tabs")
                yield Vertical(id="terminal-stack")
                with Horizontal(id="terminal-controls"):
                    yield Button("INTERRUPT", id="interrupt")
                yield Static(
                    "CTRL+N new tab   CTRL+TAB cycle   CTRL+L clear",
                    id="hint",
                )
        yield Footer()

    async def on_mount(self) -> None:
        self._client = AsyncOpenAI(
            api_key=os.environ.get("GROQ_API_KEY", "missing-key"),
            base_url=os.environ.get(
                "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
            ),
        )
        self._activity("NEXUS online. Local shell ready.")
        self._activity("Agent connected to the Groq-compatible streaming endpoint.")
        if not os.environ.get("GROQ_API_KEY"):
            self.query_one("#agent-status", Static).update(
                "● KEY REQUIRED  //  set GROQ_API_KEY and restart"
            )
            self._activity(
                "GROQ_API_KEY is not set; agent requests are disabled.", kind="WARN"
            )
        await self._create_terminal()
        self.query_one("#agent-input", Input).focus()

    async def on_unmount(self) -> None:
        for session in list(self.sessions.values()):
            self._stop_session(session)
        if self._client is not None:
            await self._client.close()

    def _activity(self, message: str, *, kind: str = "INFO") -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.query_one("#activity-log", RichLog).write(
            Text.from_markup(f"[dim]{now}[/dim]  [{kind}]  {message}")
        )

    @on(Input.Submitted, "#agent-input")
    async def submit_prompt(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.value = ""
        if self._busy:
            self._activity("Agent is already processing a request.", kind="WARN")
            return
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            self.query_one("#agent-status", Static).update(
                "● KEY REQUIRED  //  set GROQ_API_KEY and restart"
            )
            self._activity("GROQ_API_KEY is not set; request was not sent.", kind="ERR")
            return

        self._busy = True
        chat = self.query_one("#chat-log", RichLog)
        chat.write(Text("YOU  ›  ", style="bold #53e0d0") + Text(prompt))
        self.query_one("#assistant-live", Static).update("")
        self.query_one("#agent-status", Static).update(
            "● CONNECTING  //  waiting for Groq stream"
        )
        self._activity("Prompt accepted; opening a streamed completion.")
        self._history.append({"role": "user", "content": prompt})
        response = ""
        started_at = time.monotonic()
        try:
            assert self._client is not None
            stream = await self._client.chat.completions.create(
                model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=self._history,
                temperature=0.4,
                max_tokens=2048,
                stream=True,
            )
            self.query_one("#agent-status", Static).update(
                "● STREAMING  //  receiving tokens"
            )
            self._activity("Groq stream active; response tokens are arriving.")
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    response += delta
                    self.query_one("#assistant-live", Static).update(
                        Text("AGENT  ›  ", style="bold #76d8a9") + Text(response)
                    )
            self._history.append({"role": "assistant", "content": response})
            chat.write(Text("AGENT  ›  ", style="bold #76d8a9") + Text(response))
            self.query_one("#assistant-live", Static).update("")
            self.query_one("#agent-status", Static).update(
                f"● COMPLETE  //  {len(response)} chars  //  ready"
            )
            elapsed = time.monotonic() - started_at
            self._activity(
                f"Response complete: {len(response)} characters in {elapsed:.1f}s.",
                kind="OK",
            )
        except Exception as exc:
            if response:
                self._history.append({"role": "assistant", "content": response})
            else:
                self._history.pop()
            self.query_one("#assistant-live", Static).update("")
            self.query_one("#agent-status", Static).update("● REQUEST FAILED")
            self._activity(
                f"Groq request failed: {type(exc).__name__}: {exc}", kind="ERR"
            )
        finally:
            self._busy = False
            self.query_one("#agent-input", Input).focus()

    async def _create_terminal(self) -> None:
        session_id = self._next_session_id
        self._next_session_id += 1
        master_fd, slave_fd = pty.openpty()
        tty.setraw(slave_fd)
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        try:
            process = subprocess.Popen(
                [os.environ.get("SHELL", "/bin/bash"), "-i"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=os.getcwd(),
                env=env,
                start_new_session=True,
                close_fds=True,
            )
        except Exception:
            os.close(master_fd)
            os.close(slave_fd)
            raise
        os.close(slave_fd)
        os.set_blocking(master_fd, False)

        output = RichLog(
            id=f"terminal-output-{session_id}",
            classes="terminal-output",
            wrap=True,
            markup=False,
            highlight=False,
        )
        prompt = Input(
            placeholder=f"{os.path.basename(os.getcwd())} $  enter command",
            id=f"shell-prompt-{session_id}",
            classes="shell-prompt",
        )
        pane = Vertical(output, prompt, classes="terminal-pane")
        session = ShellSession(
            session_id=session_id,
            process=process,
            master_fd=master_fd,
            pane=pane,
            output=output,
            prompt=prompt,
            label=f" SHELL {session_id:02d} ",
        )
        self.sessions[session_id] = session
        await self.query_one("#terminal-stack", Vertical).mount(pane)
        asyncio.get_running_loop().add_reader(
            master_fd, self._read_terminal, session_id
        )
        self._set_active_session(session_id)
        await self._refresh_tabs()
        self._activity(
            f"Terminal {session_id:02d} started (PID {process.pid}).", kind="SHELL"
        )

    def _read_terminal(self, session_id: int) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            return
        try:
            data = os.read(session.master_fd, 8192)
        except (BlockingIOError, OSError):
            data = b""
        if data:
            text = data.decode("utf-8", errors="replace")
            session.output.write(Text.from_ansi(text))
        elif session.process.poll() is not None:
            session.prompt.disabled = True
            self._activity(
                f"Terminal {session_id:02d} shell exited ({session.process.returncode}).",
                kind="SHELL",
            )
            self._stop_session(session)

    @on(Input.Submitted)
    async def submit_shell_command(self, event: Input.Submitted) -> None:
        for session in self.sessions.values():
            if event.input is session.prompt:
                command = event.value
                event.input.value = ""
                if command:
                    try:
                        os.write(session.master_fd, command.encode() + b"\n")
                    except OSError as exc:
                        self._activity(
                            f"Could not write to terminal {session.session_id:02d}: {exc}",
                            kind="ERR",
                        )
                    else:
                        self._activity(
                            f"Terminal {session.session_id:02d} received a command.",
                            kind="SHELL",
                        )
                return

    @on(Button.Pressed)
    async def button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "new-tab":
            await self._create_terminal()
        elif button_id.startswith("tab-"):
            self._set_active_session(int(button_id.removeprefix("tab-")))
        elif button_id.startswith("close-"):
            await self._close_terminal(int(button_id.removeprefix("close-")))
        elif button_id == "interrupt" and self.active_session_id in self.sessions:
            session = self.sessions[self.active_session_id]
            try:
                os.killpg(session.process.pid, signal.SIGINT)
                self._activity(
                    f"SIGINT sent to terminal {session.session_id:02d}.", kind="SHELL"
                )
            except ProcessLookupError:
                self._activity("Active shell has already exited.", kind="WARN")

    def _set_active_session(self, session_id: int) -> None:
        self.active_session_id = session_id
        for current_id, session in self.sessions.items():
            session.pane.display = current_id == session_id
        for button in self.query("#terminal-tabs .tab-button"):
            button.set_class(button.id == f"tab-{session_id}", "active")

    async def _refresh_tabs(self) -> None:
        bar = self.query_one("#terminal-tabs", Horizontal)
        await bar.remove_children()
        for session_id, session in self.sessions.items():
            button = Button(session.label, id=f"tab-{session_id}", classes="tab-button")
            if session_id == self.active_session_id:
                button.add_class("active")
            await bar.mount(button)
            await bar.mount(
                Button("×", id=f"close-{session_id}", classes="close-button")
            )
        await bar.mount(Button("+", id="new-tab"))

    async def _close_terminal(self, session_id: int) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            return
        self._stop_session(session)
        await session.pane.remove()
        del self.sessions[session_id]
        if self.active_session_id == session_id:
            self.active_session_id = next(iter(self.sessions), None)
        await self._refresh_tabs()
        if self.active_session_id is None:
            await self._create_terminal()
        else:
            self._set_active_session(self.active_session_id)

    def _stop_session(self, session: ShellSession) -> None:
        try:
            asyncio.get_running_loop().remove_reader(session.master_fd)
        except (OSError, RuntimeError):
            pass
        if session.process.poll() is None:
            try:
                os.killpg(session.process.pid, signal.SIGHUP)
                session.process.wait(timeout=0.5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                session.process.kill()
                session.process.wait()
        try:
            os.close(session.master_fd)
        except OSError:
            pass

    async def action_new_terminal(self) -> None:
        await self._create_terminal()

    def action_next_terminal(self) -> None:
        self._cycle_terminal(1)

    def action_previous_terminal(self) -> None:
        self._cycle_terminal(-1)

    def _cycle_terminal(self, offset: int) -> None:
        ids = list(self.sessions)
        if not ids:
            return
        index = ids.index(self.active_session_id) if self.active_session_id in ids else 0
        self._set_active_session(ids[(index + offset) % len(ids)])

    def action_clear_terminal(self) -> None:
        if self.active_session_id in self.sessions:
            session = self.sessions[self.active_session_id]
            session.output.clear()
            session.prompt.focus()


if __name__ == "__main__":
    CommandCenter().run()
