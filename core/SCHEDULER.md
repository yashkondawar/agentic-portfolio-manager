# Scheduler

Runs registered strategies unattended on a daily cadence and writes every result
to the run history, so the workbench shows last night's report the moment you
open it. The UI never has to be running.

- Code: `core/scheduler.py` (daemon, CLI, installer) and `core/schedules.py`
  (the `Schedule` record, CRUD and due-time arithmetic)
- UI: **Automation & Schedules** page (`ui/pages.py::schedules_page`)
- Storage: the `schedules` table in the same SQLite database as everything else

## Quick start

```powershell
uv run python -m core.scheduler install-task
```

That is the whole setup. It registers the daemon to start at every logon and
prints a one-liner to start it immediately without logging out. From then on it
runs for as long as you are logged in — app open or closed, terminal closed,
after a crash, after sleep.

Check it worked:

```powershell
uv run python -m core.scheduler list
```

or open the **Automation & Schedules** page, which shows a live health badge.

## Default schedules

Seeded on first use, then yours to edit. The seeding only happens while the
table is empty, so it never overwrites your changes.

| Job | When | Why this time |
|-----|------|---------------|
| `gfs_live` | 17:30 IST, Mon-Fri | NSE closes at 15:30 and the bar store needs the exchange to publish today's candle (~16:00). 17:30 leaves headroom, and the engine's orders are for tomorrow's open anyway. |
| `qtr_results` | 19:30 IST, every day | Indian boards approve results after the close and filings keep landing all evening. 19:30 catches the day's batch, and running all seven days picks up the Saturday board meetings banks and NBFCs favour. Exit management still uses the last available close. |
| `qtr_results` (pre-open) | 08:15 IST, Mon-Fri, **disabled** | Optional second pass for filings that land late at night, so the action list is current when you open the app at 09:15. Off by default because the evening run usually already has them. |

Both strategies are *post-close* jobs: their output is meant to be read before
the **next** open, which is why none of them run during market hours.

## CLI

| Command | What it does |
|---------|--------------|
| `python -m core.scheduler` | Poll forever (same as `serve`). This is the daemon. |
| `python -m core.scheduler serve --poll N` | Poll every `N` seconds (default 30). |
| `python -m core.scheduler once` | Fire whatever is due right now, then exit. |
| `python -m core.scheduler list` | Print every schedule with its next occurrence. |
| `python -m core.scheduler run <id>` | Force one schedule to run immediately, ignoring its clock. |
| `python -m core.scheduler supervise` | Run `serve` in a child process and relaunch it if it dies. |
| `python -m core.scheduler install-task` | Register auto-start (see below). |
| `python -m core.scheduler uninstall-task` | Remove everything `install-task` created. |

`install-task` flags:

| Flag | Effect |
|------|--------|
| `--interval N` | Minutes between watchdog sweeps (default 30). |
| `--no-watchdog` | Install only the logon daemon, no periodic safety net. |
| `--method {auto,task,startup}` | Force a mechanism. `auto` is the default. |

## How auto-start works

Two mechanisms, tried in order.

**1. Windows Task Scheduler** (`--method task`) creates two tasks:

- `AgenticPortfolioManager Scheduler` — the daemon, trigger `ONLOGON`
- `AgenticPortfolioManager Scheduler Watchdog` — `once` every 30 minutes

The watchdog exists because a daemon that crashed, or was never started, would
otherwise silently swallow a day's runs. The two race safely (see *Claiming*).

**2. Startup folder** (`--method startup`) — the fallback. Creating scheduled
tasks needs administrator rights on many managed machines; `schtasks /Create`
returns `Access is denied` and `auto` falls back here automatically. It writes
`AgenticPortfolioManagerScheduler.cmd` into

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
```

which launches `supervise` — a thin parent process that relaunches the daemon
whenever the child dies. Same crash protection as the watchdog task, no
elevation required.

Both paths launch through `pythonw.exe`, so nothing ever flashes a console
window. Neither depends on Streamlit.

### The generated launcher

`install-task` writes a small bootstrap script next to the database
(`<runtime>/scheduler_serve.py`, `scheduler_once.py`, `scheduler_supervise.py`).
It is regenerated on every install and safe to delete. It exists because:

- `schtasks` cannot express a "Start in" directory, so the script does
  `sys.path.insert(0, REPO)` and `os.chdir(REPO)` itself;
- under `pythonw.exe` there is no console, so `sys.stdout` and `sys.stderr` are
  `None` — any `print` or logging `StreamHandler` would raise on the first log
  record. The script redirects both to `scheduler.log` *before* importing
  anything from the app.

### Not covered

`ONLOGON` and the Startup folder both mean **logon**, not boot. A machine that
is powered on at the lock screen with nobody logged in is not running the
scheduler. A true boot-time Windows service would fix that and needs admin.

## Timing semantics

Schedules are time-of-day, not cron expressions: `HH:MM` + a set of weekdays +
an IANA timezone. It covers everything this app needs, renders as a form, and
cannot be mis-typed.

**Catch-up.** If the machine was asleep or off at the scheduled moment, the job
still fires when it wakes, as long as it is inside that schedule's
`catch_up_minutes` window (default 720 = 12 hours). Past that the occurrence is
abandoned rather than retried forever — the next day is a fresh occurrence.

**Claiming.** Each schedule stores `last_fired_key`, the local date of the
occurrence it last fired. Claiming is a single conditional `UPDATE ... WHERE
id = ? AND enabled = 1 AND (last_fired_key IS NULL OR last_fired_key != ?)`;
the claim succeeds only if it changed a row. So a job can never run twice for
the same day, even with a daemon and a watchdog both awake. The claim happens
*before* the run, so a crash mid-run does not re-trigger a partly applied
strategy — it is recorded as a failure instead.

**Timezone.** Windows ships no IANA database. `tzdata` is a declared dependency,
but if it ever goes missing the code falls back to a fixed `+05:30` offset for
`Asia/Kolkata` and UTC otherwise, rather than failing.

## Results in the UI

Every fired run goes through `core.run_history.save_run`, exactly like a run you
trigger from a page. Strategy pages fall back to the newest saved run when the
session has nothing newer and label it with when it was produced, so opening the
app in the morning shows last night's report with no clicking. The run button on
each page still forces a fresh run at any time.

`gfs/run_daily.py` also persists to the run history when invoked directly, so a
hand-rolled Task Scheduler entry pointed at it shows up in the UI too. Skip that
with `--no-history`; `--dry-run` never records.

## Configuring schedules

Use the **Automation & Schedules** page. It lists every schedule with its next
occurrence and last outcome, offers *Run now*, and the editor generates its
parameter form from the strategy's own `ParamSpec` — the same form the strategy
page uses — so a schedule can carry any parameters the strategy accepts.

Programmatically:

```python
from core import schedules

schedules.create_schedule(
    strategy_id="qtr_results",
    run_at="21:00",
    name="Late filings sweep",
    days_of_week=(0, 1, 2, 3, 4),   # 0 = Monday
    params={"mode": "nse_delta"},
)
```

## Troubleshooting

**The health badge says "Not running".** The daemon has not checked in. Start it
with the command the page shows, or run `uv run python -m core.scheduler` in a
terminal to watch it live.

**A job did not fire.** Check `scheduler.log` next to the database
(`%LOCALAPPDATA%\AgenticPortfolioManager\runtime\scheduler.log`, or beside
whatever `PORTFOLIO_DB_PATH` points at). The log rotates to `.1` past 5 MB. Then
check the schedule's last status on the page — a failed run records its error.

**It fired but the report is missing.** Failures are saved to the run history
too, with the error attached. Look at the strategy's run history rather than
assuming nothing happened.

**Is it actually installed?** `core.scheduler.installed_mechanism()` returns
`"task"`, `"startup"` or `"none"`.

**Stop it.** `uninstall-task` removes the auto-start, but a scheduler already
running keeps going until you log out. Kill the `pythonw.exe` running
`core.scheduler` to stop it immediately.

## Non-Windows

`install-task` prints the equivalent crontab lines instead of doing anything:

```
@reboot cd <repo> && python -m core.scheduler serve
*/30 * * * * cd <repo> && python -m core.scheduler once
```
