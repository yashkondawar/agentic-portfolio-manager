"""Background scheduler that runs strategies on their configured cadence.

Run it as a long-lived process next to the Streamlit app::

    python -m core.scheduler                 # poll forever
    python -m core.scheduler once            # fire anything due, then exit
    python -m core.scheduler list            # show the configured schedules
    python -m core.scheduler run <id>        # force one schedule now
    python -m core.scheduler install-task    # register it to start at logon

Every fired run is persisted through :func:`core.run_history.save_run`, which is
what makes the report show up in the UI without the browser ever being open.

``install-task`` registers two Windows tasks: the daemon at logon, and a
periodic ``once`` sweep that acts as a watchdog so a crashed daemon cannot
silently swallow a day's runs. Creating scheduled tasks needs administrator
rights on many machines; when that is refused it falls back automatically to a
Startup-folder entry running ``supervise``, which restarts the daemon whenever
the process dies and needs no elevation at all.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core import registry, schedules as schedules_mod
from core.run_history import save_run
from core.schedules import Schedule, occurrence_key
from core.storage import get_document, runtime_dir, set_document
from core.strategy import StrategyResult
from logging_config import setup_logging

import logging

logger = logging.getLogger(__name__)

HEARTBEAT_NAMESPACE = "scheduler"
HEARTBEAT_KEY = "heartbeat"
TASK_NAME = "AgenticPortfolioManager Scheduler"
WATCHDOG_TASK_NAME = "AgenticPortfolioManager Scheduler Watchdog"
DEFAULT_POLL_SECONDS = 30
DEFAULT_WATCHDOG_MINUTES = 30
REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def run_schedule(
    schedule: Schedule,
    *,
    db_path: Optional[Path] = None,
) -> StrategyResult:
    """Run one schedule now and persist the result to the run history."""
    logger.info(
        "Running schedule %s (%s / %s)",
        schedule.id,
        schedule.name,
        schedule.strategy_id,
    )
    started = time.perf_counter()
    result = registry.run_strategy(schedule.strategy_id, dict(schedule.params))
    duration_ms = int((time.perf_counter() - started) * 1000)

    run_id: Optional[str] = None
    try:
        run_id = save_run(
            result,
            dict(schedule.params),
            duration_ms=duration_ms,
            db_path=db_path,
        )
    except Exception:  # persistence must never lose the outcome silently
        logger.exception("Could not persist run for schedule %s", schedule.id)

    schedules_mod.record_outcome(
        schedule.id,
        status=result.status,
        run_id=run_id,
        error=result.error,
        db_path=db_path,
    )
    logger.info(
        "Schedule %s finished with status=%s in %sms",
        schedule.id,
        result.status,
        duration_ms,
    )
    return result


def fire_due(
    now: Optional[datetime] = None,
    *,
    db_path: Optional[Path] = None,
) -> list[tuple[Schedule, StrategyResult]]:
    """Claim and run every schedule that is due at ``now``."""
    moment = now or datetime.now(timezone.utc)
    fired: list[tuple[Schedule, StrategyResult]] = []
    for schedule in schedules_mod.list_schedules(enabled_only=True, db_path=db_path):
        try:
            occurrence = schedule.due_occurrence(moment)
        except Exception:
            logger.exception("Skipping malformed schedule %s", schedule.id)
            continue
        if occurrence is None:
            continue
        # Claiming first means a crash mid-run does not re-trigger a partially
        # applied strategy on the next poll.
        if not schedules_mod.claim_occurrence(
            schedule.id, occurrence_key(occurrence), db_path=db_path
        ):
            continue
        fired.append((schedule, run_schedule(schedule, db_path=db_path)))
    return fired


# ---------------------------------------------------------------------------
# Heartbeat — lets the UI tell you whether the daemon is actually alive
# ---------------------------------------------------------------------------
def write_heartbeat(*, db_path: Optional[Path] = None, **extra) -> None:
    payload = {
        "at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "host": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "",
        **extra,
    }
    try:
        set_document(HEARTBEAT_NAMESPACE, HEARTBEAT_KEY, payload, db_path=db_path)
    except Exception:
        logger.exception("Could not write scheduler heartbeat")


def read_heartbeat(*, db_path: Optional[Path] = None) -> dict:
    try:
        return (
            get_document(HEARTBEAT_NAMESPACE, HEARTBEAT_KEY, {}, db_path=db_path) or {}
        )
    except Exception:
        return {}


def heartbeat_age_seconds(*, db_path: Optional[Path] = None) -> Optional[float]:
    beat = read_heartbeat(db_path=db_path)
    stamp = beat.get("at")
    if not stamp:
        return None
    try:
        seen = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - seen).total_seconds()


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------
def serve(
    *,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    max_cycles: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> int:
    schedules_mod.ensure_defaults(db_path=db_path)
    logger.info("Scheduler started; polling every %ss", poll_seconds)
    cycles = 0
    try:
        while max_cycles is None or cycles < max_cycles:
            write_heartbeat(db_path=db_path, poll_seconds=poll_seconds)
            try:
                fire_due(db_path=db_path)
            except Exception:
                logger.exception("Scheduler cycle failed; continuing")
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(max(1, poll_seconds))
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    return 0


def supervise(
    *,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    backoff_seconds: int = 15,
    max_restarts: Optional[int] = None,
) -> int:
    """Run `serve` in a child process and restart it whenever it dies.

    `serve` already swallows per-cycle exceptions, so this only matters when the
    process itself goes away — killed, out of memory, an interpreter fault. That
    is exactly the case a Startup-folder entry cannot recover from on its own.
    """
    interpreter = _interpreter()
    log = log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    restarts = 0
    while True:
        with open(log, "a", encoding="utf-8", errors="replace", buffering=1) as fh:
            completed = subprocess.run(
                [
                    str(interpreter),
                    "-m",
                    "core.scheduler",
                    "serve",
                    "--poll",
                    str(poll_seconds),
                ],
                cwd=str(REPO_ROOT),
                stdout=fh,
                stderr=fh,
            )
        logger.warning(
            "Scheduler process exited with %s; restarting in %ss",
            completed.returncode,
            backoff_seconds,
        )
        restarts += 1
        if max_restarts is not None and restarts >= max_restarts:
            return completed.returncode
        time.sleep(max(1, backoff_seconds))


# ---------------------------------------------------------------------------
# Windows Task Scheduler helper
# ---------------------------------------------------------------------------
# Two tasks, because one is not enough to be trustworthy:
#   * the daemon starts at logon and polls continuously;
#   * the watchdog fires `once` on a fixed interval, so a daemon that crashed
#     (or was never started) still cannot silently swallow a day's runs.
# Both race safely: claiming an occurrence is a single conditional UPDATE.
_BOOTSTRAP = '''\
"""Generated by core.scheduler — safe to delete; reinstalling recreates it."""

import os
import sys

REPO = r"{repo}"
LOG = r"{log}"

sys.path.insert(0, REPO)
os.chdir(REPO)

# pythonw.exe gives this process no console, so sys.stdout/sys.stderr are None
# and any print or logging StreamHandler would explode. Point them at a file.
try:
    if os.path.exists(LOG) and os.path.getsize(LOG) > 5_000_000:
        os.replace(LOG, LOG + ".1")
except OSError:
    pass
_stream = open(LOG, "a", encoding="utf-8", errors="replace", buffering=1)
sys.stdout = _stream
sys.stderr = _stream

from core.scheduler import main  # noqa: E402

raise SystemExit(main({args!r}))
'''


def log_path() -> Path:
    return runtime_dir() / "scheduler.log"


def _interpreter() -> Path:
    """Prefer the windowless interpreter so scheduled runs never flash a console."""
    executable = Path(sys.executable)
    windowless = executable.with_name("pythonw.exe")
    return windowless if windowless.exists() else executable


def write_bootstrap(filename: str, args: list[str]) -> Path:
    """Write a self-contained launcher script for one scheduler command."""
    path = runtime_dir() / filename
    path.write_text(
        _BOOTSTRAP.format(repo=REPO_ROOT, log=log_path(), args=args),
        encoding="utf-8",
    )
    return path


def _create_task(
    task_name: str, script: Path, schedule: list[str], *, quiet: bool = False
) -> int:
    command = [
        "schtasks",
        "/Create",
        "/TN",
        task_name,
        "/TR",
        f'"{_interpreter()}" "{script}"',
        *schedule,
        "/RL",
        "LIMITED",
        "/F",
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if not quiet:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
    return completed.returncode


def startup_entry_path() -> Optional[Path]:
    """The per-user Startup folder entry — the fallback that needs no admin."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / "AgenticPortfolioManagerScheduler.cmd"
    )


def install_startup_entry() -> int:
    """Start the supervisor at logon without touching Task Scheduler.

    Creating a scheduled task requires administrator rights on locked-down
    machines. A Startup-folder shortcut does not, and the supervisor it launches
    gives us the same crash recovery the watchdog task would have provided.
    """
    entry = startup_entry_path()
    if entry is None:
        print("Could not locate the Startup folder (%APPDATA% is unset).")
        return 1
    script = write_bootstrap(
        "scheduler_supervise.py", ["supervise", "--poll", str(DEFAULT_POLL_SECONDS)]
    )
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "@echo off\r\n" f'start "" /min "{_interpreter()}" "{script}"\r\n',
        encoding="utf-8",
    )
    print(f"Startup entry: {entry}")
    print(f"Launcher:      {script}")
    print(f"Log:           {log_path()}")
    print(
        "\nInstalled. It starts at every logon and restarts itself if it ever "
        "dies. Start it now without logging out:"
    )
    print(f'  Start-Process -WindowStyle Hidden "{entry}"')
    return 0


def install_task(
    *,
    task_name: str = TASK_NAME,
    watchdog_name: str = WATCHDOG_TASK_NAME,
    interval_minutes: int = DEFAULT_WATCHDOG_MINUTES,
    watchdog: bool = True,
    method: str = "auto",
) -> int:
    if os.name != "nt":
        print("Not on Windows. Add these to your crontab instead:\n")
        print(f"@reboot cd {REPO_ROOT} && {sys.executable} -m core.scheduler serve")
        print(
            f"*/{interval_minutes} * * * * cd {REPO_ROOT} && "
            f"{sys.executable} -m core.scheduler once"
        )
        return 0

    if method == "startup":
        return install_startup_entry()

    daemon_script = write_bootstrap(
        "scheduler_serve.py", ["serve", "--poll", str(DEFAULT_POLL_SECONDS)]
    )
    code = _create_task(
        task_name, daemon_script, ["/SC", "ONLOGON"], quiet=method == "auto"
    )
    if code != 0:
        if method == "task":
            return code
        print(
            "Task Scheduler refused the request - creating tasks needs "
            "administrator rights on this machine. Falling back to a Startup "
            "folder entry, which does not.\n"
        )
        return install_startup_entry()
    print(f"Launcher: {daemon_script}")
    print(f"Log:      {log_path()}")
    print(f"Installed '{task_name}' (starts at every logon).")

    if watchdog:
        watchdog_script = write_bootstrap("scheduler_once.py", ["once"])
        code = _create_task(
            watchdog_name,
            watchdog_script,
            ["/SC", "MINUTE", "/MO", str(max(1, int(interval_minutes)))],
        )
        if code != 0:
            return code
        print(
            f"Installed '{watchdog_name}' (every {interval_minutes} minutes, "
            "catches anything a stopped daemon missed)."
        )

    print("\nStart the daemon now without logging out:")
    print(f'  schtasks /Run /TN "{task_name}"')
    return 0


def uninstall_task(
    *,
    task_name: str = TASK_NAME,
    watchdog_name: str = WATCHDOG_TASK_NAME,
) -> int:
    if os.name != "nt":
        print("Nothing to remove: no Windows task was created.")
        return 0
    entry = startup_entry_path()
    removed = []
    if entry is not None and entry.exists():
        entry.unlink()
        removed.append(f"startup entry {entry}")
    for name in (task_name, watchdog_name):
        completed = subprocess.run(
            ["schtasks", "/Delete", "/TN", name, "/F"],
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            removed.append(f"task '{name}'")
    for item in removed:
        print(f"Removed {item}")
    if not removed:
        print("Nothing to remove: the scheduler was not installed.")
    print("Any scheduler already running keeps going until you log out.")
    return 0


def installed_mechanism() -> str:
    """Describe how (or whether) the scheduler is registered to auto-start."""
    if os.name != "nt":
        return "unknown"
    entry = startup_entry_path()
    if entry is not None and entry.exists():
        return "startup"
    probe = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        text=True,
    )
    return "task" if probe.returncode == 0 else "none"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_schedules() -> None:
    rows = schedules_mod.ensure_defaults()
    if not rows:
        print("No schedules configured.")
        return
    now = datetime.now(timezone.utc)
    for schedule in rows:
        state = "on " if schedule.enabled else "off"
        following = schedule.next_occurrence(now)
        print(f"[{state}] {schedule.name}  ({schedule.strategy_id})")
        print(f"        id={schedule.id}")
        print(f"        when={schedule.describe()}")
        print(
            "        next="
            + (following.strftime("%Y-%m-%d %H:%M %Z") if following else "never")
        )
        if schedule.last_run_at:
            print(f"        last={schedule.last_status} at {schedule.last_run_at}")
        if schedule.params:
            print(f"        params={schedule.params}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core.scheduler",
        description="Run workbench strategies on a daily schedule.",
    )
    sub = parser.add_subparsers(dest="command")

    serve_cmd = sub.add_parser("serve", help="Poll forever (default).")
    serve_cmd.add_argument(
        "--poll",
        type=int,
        default=DEFAULT_POLL_SECONDS,
        help=f"Seconds between checks (default {DEFAULT_POLL_SECONDS}).",
    )
    serve_cmd.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Stop after N polls (testing).",
    )

    sub.add_parser("once", help="Fire whatever is due right now, then exit.")
    sub.add_parser("list", help="Show configured schedules.")

    supervise_cmd = sub.add_parser(
        "supervise", help="Run the daemon and restart it if it ever dies."
    )
    supervise_cmd.add_argument(
        "--poll",
        type=int,
        default=DEFAULT_POLL_SECONDS,
        help=f"Seconds between checks (default {DEFAULT_POLL_SECONDS}).",
    )

    run_cmd = sub.add_parser("run", help="Force one schedule to run immediately.")
    run_cmd.add_argument("schedule_id")

    install = sub.add_parser(
        "install-task", help="Register the daemon to start at logon."
    )
    install.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_WATCHDOG_MINUTES,
        help=(
            "Minutes between watchdog sweeps that catch runs a stopped daemon "
            f"missed (default {DEFAULT_WATCHDOG_MINUTES})."
        ),
    )
    install.add_argument(
        "--no-watchdog",
        action="store_true",
        help="Install only the logon daemon, with no periodic safety net.",
    )
    install.add_argument(
        "--method",
        choices=("auto", "task", "startup"),
        default="auto",
        help=(
            "auto: try Task Scheduler, fall back to a Startup entry if it is "
            "blocked; task: Task Scheduler only; startup: Startup entry only."
        ),
    )
    sub.add_parser(
        "uninstall-task", help="Remove the logon task, watchdog and startup entry."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "serve"

    if command == "list":
        _print_schedules()
        return 0
    if command == "install-task":
        return install_task(
            interval_minutes=getattr(args, "interval", DEFAULT_WATCHDOG_MINUTES),
            watchdog=not getattr(args, "no_watchdog", False),
            method=getattr(args, "method", "auto"),
        )
    if command == "uninstall-task":
        return uninstall_task()
    if command == "supervise":
        return supervise(poll_seconds=getattr(args, "poll", DEFAULT_POLL_SECONDS))
    if command == "run":
        schedule = schedules_mod.get_schedule(args.schedule_id)
        if schedule is None:
            print(f"No schedule with id {args.schedule_id!r}.", file=sys.stderr)
            return 1
        result = run_schedule(schedule)
        print(result.report)
        return 0 if result.ok else 1
    if command == "once":
        schedules_mod.ensure_defaults()
        fired = fire_due()
        if not fired:
            print("Nothing due.")
        for schedule, result in fired:
            print(f"{schedule.name}: {result.status}")
        return 0

    return serve(
        poll_seconds=getattr(args, "poll", DEFAULT_POLL_SECONDS),
        max_cycles=getattr(args, "cycles", None),
    )


if __name__ == "__main__":
    raise SystemExit(main())
