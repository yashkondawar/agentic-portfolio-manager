# Review and run manually when ready — not auto-registered.
#
# Generates two Windows Task Scheduler entries for the afund orchestrator:
#   1. daily_data          — 18:30, daily (prices/amfi/index_valuation/news
#                             fetch; universe refresh is Monday-only, handled
#                             inside the job itself).
#   2. daily_news_process  — 07:45, daily morning news fetch/enrichment pass.
#
# Each task invokes .venv\Scripts\python -m afund.orchestrator.run --job <trigger>
# with WorkingDirectory set to the repo root, so relative paths (config/,
# registry/, data/) resolve correctly regardless of the Task Scheduler
# service's default working directory.
#
# This script only calls Register-ScheduledTask — it does not run anything
# on its own. Read it, adjust the repo path / trigger times if needed, then
# run it manually (as an elevated PowerShell session if required by your
# Task Scheduler permissions) when you're ready to activate the schedule.

$RepoRoot = "D:\Documents\Claude\1Projects\AI Native Fund"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

# --- daily_data: 18:30 daily -------------------------------------------------

$DailyDataAction = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m afund.orchestrator.run --job daily_data" `
    -WorkingDirectory $RepoRoot

$DailyDataTrigger = New-ScheduledTaskTrigger -Daily -At "18:30"

Register-ScheduledTask `
    -TaskName "afund_daily_data" `
    -Action $DailyDataAction `
    -Trigger $DailyDataTrigger `
    -Description "afund orchestrator: daily_data (universe-if-monday, prices, amfi, index_valuation, news_fetch)" `
    -RunLevel Limited

# --- daily_news_process: 07:45 daily morning news fetch ---------------------

$DailyNewsAction = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m afund.orchestrator.run --job daily_news_process" `
    -WorkingDirectory $RepoRoot

$DailyNewsTrigger = New-ScheduledTaskTrigger -Daily -At "07:45"

Register-ScheduledTask `
    -TaskName "afund_daily_news_process" `
    -Action $DailyNewsAction `
    -Trigger $DailyNewsTrigger `
    -Description "afund orchestrator: daily_news_process (news_processor agent packet prep for unprocessed news_items)" `
    -RunLevel Limited
