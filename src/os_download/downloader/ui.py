import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress
from rich.table import Table

from os_download.downloader.paths import filename_from_url

_SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def keyboard_listener(quit_event: threading.Event, stop_event: threading.Event) -> None:
    if not sys.stdin.isatty():
        return
    try:
        import select as _sel
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not stop_event.is_set():
                if _sel.select([sys.stdin], [], [], 0.1)[0]:
                    if sys.stdin.read(1).lower() == "q":
                        quit_event.set()
                        return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass


@dataclass
class SessionState:
    """Outcome of one download session.

    Files are only counted once their future actually reports back, so quitting or
    interrupting mid-session leaves the never-started files out of both tallies.
    """

    urls: list[str]
    parallel: int
    resume: bool
    verify: bool
    started_at: float = field(default_factory=time.monotonic)
    succeeded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    interrupted: bool = False
    mido_failed: int = 0

    @property
    def done_count(self) -> int:
        return len(self.succeeded) + len(self.failed)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def record(self, url: str, ok: bool) -> None:
        (self.succeeded if ok else self.failed).append(url)


class SessionDashboard:
    """Owns the Rich layout for a download session: header, file list, completion panel."""

    def __init__(self, console: Console, progress: Progress, state: SessionState):
        self.console = console
        self.progress = progress
        self.state = state
        self.speed_samples: deque[tuple[float, int]] = deque(maxlen=40)
        self.layout = Layout()
        self._stop_refresh = threading.Event()
        self._refresh_thread: threading.Thread | None = None
        self._shortcuts = self._build_shortcuts()
        self._build_layout()

    def _build_shortcuts(self) -> Table:
        shortcuts = Table.grid(expand=True, padding=(0, 1))
        shortcuts.add_column(justify="left")
        shortcuts.add_column(justify="right")
        shortcuts.add_row(
            "  [bold dim]q[/bold dim] [dim]quit[/dim]"
            "   [bold dim]Ctrl+C[/bold dim] [dim]interrupt[/dim]"
            "   [dim]— partial files resume automatically[/dim]",
            f"[dim]parallel={self.state.parallel}"
            f"  resume={'on' if self.state.resume else 'off'}"
            f"  verify={'on' if self.state.verify else 'off'}  [/dim]",
        )
        return shortcuts

    def layout_sizes(
        self,
        completion_lines: list[str] | None = None,
        terminal_height: int | None = None,
    ) -> tuple[int, int, int, int]:
        header_size = 6
        footer_size = 1
        body_size = len(self.state.urls) + 2
        completion_size = 0

        if completion_lines is not None:
            content_lines = sum(line.count("\n") + 1 for line in completion_lines)
            completion_size = content_lines + 2

        if terminal_height is None:
            return header_size, body_size, completion_size, footer_size

        available_body = terminal_height - header_size - completion_size - footer_size
        body_size = max(3, min(body_size, available_body))
        return header_size, body_size, completion_size, footer_size

    def _build_layout(self) -> None:
        header_size, body_size, _, footer_size = self.layout_sizes(
            terminal_height=self.console.height
        )
        self.layout.split_column(
            Layout(name="header", size=header_size),
            Layout(name="body", size=body_size),
            Layout(name="footer", size=footer_size),
        )
        self.layout["body"].update(
            Panel(self.progress, title="[dim]Files[/]", border_style="dim")
        )
        self.layout["footer"].update(self._shortcuts)
        self.update()

    def _total_bytes(self) -> int:
        return sum(
            task.completed for task in self.progress.tasks if task.completed is not None
        )

    def _speed_sparkline(self) -> str:
        if len(self.speed_samples) < 2:
            return "[dim]—[/dim]"

        speeds = []
        for index in range(1, len(self.speed_samples)):
            delta_t = self.speed_samples[index][0] - self.speed_samples[index - 1][0]
            delta_b = self.speed_samples[index][1] - self.speed_samples[index - 1][1]
            if delta_t > 0:
                speeds.append(max(0.0, delta_b / delta_t))

        if not speeds:
            return "[dim]—[/dim]"

        peak = max(speeds) or 1.0
        bars = "".join(_SPARK_CHARS[min(8, int(speed / peak * 8))] for speed in speeds[-20:])
        current_mbs = speeds[-1] / 1_048_576
        return f"[yellow]{bars}[/yellow] [bold]{current_mbs:.1f} MB/s[/bold]"

    def update(self) -> None:
        state = self.state
        total_files = len(state.urls)
        total_bytes = self._total_bytes()
        self.speed_samples.append((time.monotonic(), total_bytes))

        minutes, seconds = divmod(int(state.elapsed), 60)
        active = min(state.parallel, max(0, total_files - state.done_count))
        waiting = max(0, total_files - state.done_count - active)
        pct = int(state.done_count / total_files * 100) if total_files else 0

        parts: list[str] = []
        if active > 0:
            parts.append(f"[cyan]▶ {active} downloading[/cyan]")
        if state.succeeded:
            parts.append(f"[green]✓ {len(state.succeeded)} done[/green]")
        if state.failed:
            last_name = filename_from_url(state.failed[-1])
            short = last_name[:24] + "…" if len(last_name) > 25 else last_name
            parts.append(f"[red]✗ {len(state.failed)} failed[/red] [dim]({short})[/dim]")
        if waiting > 0:
            parts.append(f"[dim]○ {waiting} queued[/dim]")

        status = "  ".join(parts) if parts else "[dim]preparing…[/dim]"
        file_cell = f"{status}  [dim]·  {state.done_count}/{total_files}  {pct}%[/dim]"

        grid = Table.grid(expand=True, padding=(0, 3))
        grid.add_column(style="bold dim", min_width=14)
        grid.add_column(min_width=24)
        grid.add_column(style="bold dim", min_width=10)
        grid.add_column()
        grid.add_row("Files", file_cell, "Elapsed", f"{minutes:02d}:{seconds:02d}")
        grid.add_row(
            "Downloaded",
            f"[cyan]{total_bytes / 1_048_576:.1f} MB[/cyan]",
            "Speed",
            self._speed_sparkline(),
        )

        if state.interrupted:
            title, border_style = "[bold yellow]⏸  os-download[/bold yellow]", "yellow"
        elif state.done_count == total_files and state.failed:
            title, border_style = "[bold red]✗  os-download[/bold red]", "red"
        elif state.done_count == total_files:
            title, border_style = "[bold green]✓  os-download[/bold green]", "green"
        else:
            title, border_style = "[bold cyan]os-download[/bold cyan]", "cyan"

        self.layout["header"].update(
            Panel(grid, title=title, border_style=border_style, padding=(1, 2))
        )

    def start_refresh(self) -> None:
        def refresh() -> None:
            while not self._stop_refresh.is_set():
                self.update()
                time.sleep(0.25)

        self._refresh_thread = threading.Thread(target=refresh, daemon=True)
        self._refresh_thread.start()

    def stop_refresh(self) -> None:
        self._stop_refresh.set()
        if self._refresh_thread is not None:
            self._refresh_thread.join(timeout=0.5)

    def completion_summary(self) -> tuple[str, str, list[str]]:
        state = self.state
        minutes, seconds = divmod(int(state.elapsed), 60)
        succeeded = len(state.succeeded)
        failed = state.failed
        skipped = len(state.urls) - state.done_count

        if state.interrupted:
            border_style, title = "yellow", "⏸  Interrupted"
        elif failed or state.mido_failed:
            border_style, title = "red", "✗  Finished with errors"
        else:
            border_style, title = "green", "✓  Complete"

        files_line = f"  [bold]Files[/bold]       [green]{succeeded}[/green] downloaded"
        if failed:
            files_line += f"  [red]{len(failed)} failed[/red]"
        if skipped:
            files_line += f"  [dim]{skipped} not started[/dim]"
        if state.mido_failed:
            files_line += f"  [red]{state.mido_failed} Mido failed[/red]"

        lines = [
            files_line,
            f"  [bold]Data[/bold]        {self._total_bytes() / 1_048_576:.1f} MB",
            f"  [bold]Time[/bold]        {minutes:02d}:{seconds:02d}",
        ]
        if state.interrupted:
            lines.append("\n  [dim]Partial files can be resumed with the same command.[/dim]")
        for failed_url in failed:
            lines.append(f"  [red]✗[/red] {filename_from_url(failed_url)}")

        return border_style, title, lines

    def show_completion(self) -> None:
        border_style, title, lines = self.completion_summary()
        header_size, body_size, completion_size, footer_size = self.layout_sizes(
            completion_lines=lines, terminal_height=self.console.height
        )
        self.layout.split_column(
            Layout(name="header", size=header_size),
            Layout(name="body", size=body_size),
            Layout(name="completion", size=completion_size),
            Layout(name="footer", size=footer_size),
        )
        self.layout["body"].update(
            Panel(self.progress, title="[dim]Files[/]", border_style="dim")
        )
        self.layout["completion"].update(
            Panel(
                "\n".join(lines),
                title=f"[bold]{title}[/bold]",
                border_style=border_style,
                expand=True,
            )
        )
        self.layout["footer"].update(self._shortcuts)
        self.update()
