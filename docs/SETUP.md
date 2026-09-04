# Getting Started

A step-by-step guide for setting this up on a brand new computer.

You do **not** need to be a programmer to follow this. You will copy and paste
some commands into a terminal window, and that is about it. Every command is
safe to re-run if you are unsure whether it worked.

Total time: about 30 minutes of your attention, plus some waiting while
historical data downloads in the background.

---

## Contents

1. [What this app does](#1-what-this-app-does)
2. [What you need before you start](#2-what-you-need-before-you-start)
3. [Install it](#3-install-it)
4. [Choose who powers the AI](#4-choose-who-powers-the-ai)
5. [Start the app](#5-start-the-app)
6. [About the database](#6-about-the-database)
7. [Getting the historical market data](#7-getting-the-historical-market-data)
8. [Sharing your data with a friend](#8-sharing-your-data-with-a-friend)
9. [Letting it run on a schedule](#9-letting-it-run-on-a-schedule)
10. [Connecting your broker (optional)](#10-connecting-your-broker-optional)
11. [If something goes wrong](#11-if-something-goes-wrong)

---

## 1. What this app does

It researches Indian stocks (NSE) for you. It downloads years of price history
and company results, runs a set of AI analysts over them, and produces written
research reports you can read in your browser.

Everything runs on your own computer. Your data stays with you.

---

## 2. What you need before you start

Three things. Take them in order.

### a) A terminal window

This is where you type commands.

- **Windows** — press the Start button, type `powershell`, press Enter.
- **Mac** — press `Cmd + Space`, type `terminal`, press Enter.

Leave it open. You will use it several times.

### b) Two free tools: Git and uv

**Git** downloads the app. **uv** installs everything the app needs.

Check whether you already have them by typing this and pressing Enter:

```
git --version
uv --version
```

If both print a version number, skip ahead to (c).

If either says "not recognized" or "command not found", install the missing one:

| Tool | Windows | Mac |
|------|---------|-----|
| Git | `winget install Git.Git` | `brew install git` |
| uv  | `winget install astral-sh.uv` | `brew install uv` |

**Close your terminal and open a new one afterwards**, otherwise it will not
notice the new tools. Then run the two `--version` commands again to confirm.

> You do **not** need to install Python. `uv` handles that for you.

### c) One AI provider

The app needs an AI service to do the thinking. You need **exactly one** of the
options below — whichever you already have. Do not buy anything new.

| You have | What to use | Cost |
|----------|-------------|------|
| A GitHub Copilot subscription | Copilot | Already paid for |
| A Claude Pro or Max subscription | Claude Code | Already paid for |
| A Google Gemini API key | Gemini | Free tier available |
| An OpenAI API key | OpenAI | Pay per use |
| An Anthropic (Claude) API key | Claude | Pay per use |

**Don't have any of these?** Get a free Gemini key: go to
[aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in with a
Google account, click **Create API key**, and copy the long string it shows you.
Keep it somewhere safe for step 4 — treat it like a password.

> **A note on Claude subscriptions:** a Claude Pro or Max plan *does* work,
> through the **Claude Code** option. It is a different thing from an Anthropic
> API key, and it is set up differently — see step 3 and step 4. Your plan
> includes a monthly allowance for apps like this one, kept separate from the
> allowance you use when chatting with Claude yourself. You may need to switch
> it on once in your account settings at
> [console.anthropic.com](https://console.anthropic.com).

---

## 3. Install it

Copy these three commands into your terminal, one at a time, pressing Enter
after each:

```
git clone https://github.com/yashkondawar/agentic-portfolio-manager.git
```

```
cd agentic-portfolio-manager
```

Now install, using the line that matches the provider you chose in step 2c:

```
uv sync --extra copilot      # GitHub Copilot
uv sync --extra claude       # Claude Pro/Max subscription
uv sync --extra gemini       # Google Gemini
uv sync --extra openai       # OpenAI
uv sync --extra anthropic    # Claude API key
```

The last command downloads a lot of files and takes a few minutes. A wall of
scrolling text is normal. It is finished when your cursor comes back.

> **Important:** every command in the rest of this guide must be run from
> inside the `agentic-portfolio-manager` folder. If you close your terminal and
> come back later, type `cd agentic-portfolio-manager` first.

### Only if you chose Copilot

Copilot needs one extra program and a one-time sign-in:

```
npm install -g @github/copilot
copilot
```

The second command opens a sign-in prompt in your browser. Complete it, then
close it with `Ctrl + C`. You only ever do this once.

### Only if you chose Claude Pro/Max

**Already use Claude Code on this computer?** Then you are done — the app finds
your existing sign-in by itself. Skip to step 4.

Otherwise, install it and sign in once:

```
npm install -g @anthropic-ai/claude-code
claude setup-token
```

The second command opens your browser to approve access, then prints a long
code starting with `sk-ant-oat`. **Copy that code** — you will paste it into
the app in step 4. It lasts about a year.

> **If you also have an Anthropic API key:** having both can quietly send the
> bill to your card instead of your subscription. This app watches for that and
> uses your subscription, telling you when it does. If you would rather pay per
> use, put `CLAUDE_CODE_USE_API_KEY=1` in your `.env` file.

---

## 4. Choose who powers the AI

You can do this inside the app, which is easier — skip to step 5 and come back
here only if it asks you to.

The app checks for a provider when it starts. If it finds exactly one, it uses
it automatically and tells you which one it picked. If it finds none, open the
**Settings & Catalog** page in the sidebar, choose your provider from the list,
paste your API key — or, for Claude Pro/Max, the `sk-ant-oat` code from step 3 —
into the box, and press Save. The app writes it down for you and remembers it
next time.

**If you have more than one**, the app picks one for you and says which on the
Settings page. Read that line once, because the two Claude options cost money in
different ways: a Pro/Max subscription is already paid for, while a Claude API
key is billed per use on your card.

If you have both, what decides it is whether you did the `sk-ant-oat` step in
step 3. With that code saved, the app uses your subscription and leaves the card
alone. Without it, the app cannot tell you have a subscription at all, so it
falls back to the key and you end up paying twice for the same thing. Either
save the code, or go to **Settings & Catalog**, pick **Claude Code** and press
Save. Whenever the two are mixed up the app writes a line in its logs naming
which one is paying.

<details>
<summary>Prefer to set it up by hand? Click here.</summary>

Make a copy of the example settings file:

```
copy example.env .env        # Windows
cp example.env .env          # Mac
```

Open `.env` in Notepad or TextEdit and fill in the block at the top. Set one
key for your provider, for example:

```
GOOGLE_API_KEY=your-key-here
```

...or, for a Claude Pro/Max subscription:

```
AI_AGENT_BACKEND=claude_code
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat-your-code-here
```

Save the file. The app picks the rest up on its own.

</details>

> **Never share your `.env` file, or paste your API key into a chat or email.**
> Anyone who has it can spend your money.

---

## 5. Start the app

```
uv run streamlit run app.py
```

Your browser opens at `http://localhost:8501` automatically. If it does not,
open that address yourself.

To stop the app, come back to the terminal and press `Ctrl + C`.

**First thing to do:** open **Settings & Catalog** from the sidebar. It shows a
checklist of everything that is working and everything that still needs
attention. Green means ready.

The app works right now, but it has no market history yet, so its research will
be thin. Step 7 fixes that.

---

## 6. About the database

**There is nothing to install and nothing to set up.** This section is only so
you know where your data lives.

The app stores everything in a single file that it creates by itself the first
time it runs. It is not inside the app's folder, so deleting or re-downloading
the app never destroys your data.

To find out where that file is:

```
uv run python -m core.storage path
```

To see what is in it:

```
uv run python -m core.storage summary
```

Typically:

- **Windows** — `C:\Users\<you>\AppData\Local\AgenticPortfolioManager\portfolio.sqlite3`
- **Mac** — `~/Library/Application Support/AgenticPortfolioManager/portfolio.sqlite3`

### Backing it up

Copy that one file somewhere safe — an external drive, or a cloud folder. That
is a complete backup of everything: your market history, your settings, your
saved reports.

**Do not send that file to anyone else.** It contains your API keys, your
broker login and your holdings. To share data with a friend safely, see
[step 8](#8-sharing-your-data-with-a-friend), which is built for exactly that.

---

## 7. Getting the historical market data

The AI is only as good as the data behind it, so this step matters. You are
downloading years of Indian market history onto your machine.

**These downloads take a long time — hours, sometimes overnight.** That is
normal and unavoidable; the data sources are slow on purpose. The good news:

- You can stop any of them at any time with `Ctrl + C`.
- Re-running one picks up where it left off. Nothing is downloaded twice.
- Once you are up to date, re-running only fetches what is new.

Run each of the three below. Do them one at a time, not all at once — they
compete for the same slow connection.

> **Faster option:** if a friend already has this data, they can send you a copy
> and you can skip most of the waiting. See [step 8](#8-sharing-your-data-with-a-friend).

### a) Daily prices for every stock

```
uv run python -m scraper.bhavcopy
```

Downloads the official end-of-day price sheet the exchange publishes, for every
trading day since 2013. This is the slowest one — leave it running overnight.

It matters more than it looks: it includes companies that have since been
delisted or merged away. Without them, any test of a strategy would only ever
see today's survivors and would flatter itself badly.

### b) Price history for the main stocks

```
uv run python -m backtesting.warm_bars --universe nifty500 --start 2018-01-01
```

Fills in clean daily price history for the top 500 companies. Takes 30–60
minutes.

Check on it any time with:

```
uv run python -m backtesting.warm_bars --stats
```

### c) Company financial results

```
uv run python -m scraper.backfill_nse_fundamentals --from-year 2012
```

Downloads quarterly results and annual reports. Takes a few hours.

Check on it any time with:

```
uv run python -m scraper.backfill_nse_fundamentals --status
```

### Keeping it current

Run the same three commands again whenever you want to catch up — weekly is
plenty. They only fetch what is missing. Or set up [step 9](#9-letting-it-run-on-a-schedule)
and never think about it again.

---

## 8. Sharing your data with a friend

**Yes, you can share it — but use the command below, never a copy of the raw
database file.**

Your database has two very different kinds of thing in it, side by side:

| Safe to share | Must never leave your computer |
|---------------|-------------------------------|
| Market prices | Your API keys |
| Company results | Your broker login token |
| Corporate actions | Your holdings and portfolio |
| Index membership | Your saved research reports |

The market data took you hours to download and is identical for everyone, so
sharing it is genuinely useful. The rest is yours alone.

The app can separate the two for you.

### To send your data to a friend

```
uv run python -m core.storage share market-history.sqlite3
```

This creates a new file, `market-history.sqlite3`, in your current folder,
containing **only** the market data. It prints a list of what went in and how
many rows. Send that file over WhatsApp, email, Google Drive — anywhere.

It contains no keys, no broker token, no holdings and no reports. Your friend
gets the years of downloading, and nothing personal.

### To load a file a friend sent you

Put their file in your app folder, then:

```
uv run python -m core.storage import-shared market-history.sqlite3
```

It adds anything you were missing and leaves everything you already had
untouched. Running it twice is harmless — the second time it will simply add
nothing.

This works on a completely fresh machine too, so a new user can skip straight
past most of step 7.

---

## 9. Letting it run on a schedule

Optional, but recommended. This keeps your data fresh and runs your research
automatically, so the app has fresh answers waiting for you.

**Run this once per computer:**

```
uv run python -m core.scheduler install-task
```

That is the whole thing. From now on the scheduler starts by itself every time
you log in, restarts itself if it ever crashes, and keeps running whether or
not you have the app open.

If your computer refuses because you are not an administrator, it notices and
quietly sets itself up a different way that needs no special permission. Either
way it works — read the message it prints to see which route it took.

### Checking it is alive

Open the **Schedules** page in the app. It shows a status at the top: green and
running, or a warning with the exact command to fix it.

### Choosing what it does

Also on the **Schedules** page. You can add, edit and remove scheduled jobs
there, and force one to run immediately to see what happens.

### Turning it off

```
uv run python -m core.scheduler uninstall-task
```

---

## 10. Connecting your broker (optional)

Only if you want the app to see your actual holdings. **You can skip this
entirely** — everything else works without it.

The app supports Zerodha, and it is **read-only**: it can look at your account,
but it cannot place, modify or cancel a single order.

You will need a Zerodha Kite Connect app, which costs extra from Zerodha. If
you have one, put the credentials in your `.env` file as shown in
`example.env`, then use the connect button on the **Settings & Catalog** page.

Your broker login is stored only on your computer, and it is one of the things
the sharing command in step 8 deliberately leaves behind.

---

## 11. If something goes wrong

Work down this list. Most problems are one of the first three.

**"git is not recognized" / "uv is not recognized"**
The tool is not installed, or you did not restart your terminal after
installing it. Go back to [step 2b](#b-two-free-tools-git-and-uv), install it,
then close the terminal window and open a fresh one.

**"No such file or directory" / "cannot find the path"**
You are in the wrong folder. Type `cd agentic-portfolio-manager` and try again.

**The app says it cannot find a model provider**
It has no API key to work with. Open **Settings & Catalog** in the sidebar,
pick your provider and paste your key. If you already did, check for a stray
space at the start or end of the pasted key.

**"Rate limit" warnings, or a report where analysts are missing**
Your AI provider is capping how fast the app may ask it questions — common on
free tiers. The report will say which analysts were dropped. Wait a few minutes
and run it again, or slow the app down by adding this line to your `.env` file:

```
AI_MAX_CONCURRENCY=2
```

**A download stopped partway through**
Just run the same command again. It continues from where it stopped.

**The install fails with "Failed to fetch", "HandshakeFailure" or "Connect"**
You are almost certainly on a work, school or VPN network that inspects secure
connections, so the installer does not trust it. Add `--native-tls` to the end
of your install line, which tells the installer to use the certificates your
computer already trusts:

```
uv sync --extra claude --native-tls
```

(swap `claude` for whichever provider you chose). If it still fails, your
network probably requires you to download packages from an internal mirror
rather than the public one. Ask your IT team for the mirror address, then run
the install once more with it — replacing the example address below:

Windows PowerShell:
```
$env:UV_DEFAULT_INDEX = "https://your-company-mirror/pypi/simple/"
uv sync --extra claude --native-tls
```

macOS:
```
export UV_DEFAULT_INDEX="https://your-company-mirror/pypi/simple/"
uv sync --extra claude --native-tls
```

You only need to do this the first time. Afterwards `uv run streamlit run
app.py` starts the app normally, because everything is already downloaded.

**The app will not start at all**
Make sure you ran the `uv sync` line for your provider in
[step 3](#3-install-it) — a different provider's line will not do. Then try:

```
uv sync --extra all
```

**Something else**
Check the **Settings & Catalog** page first; it diagnoses most configuration
problems and tells you what is missing. For anything deeper, the
[README](../README.md) has the technical detail.

---

## Quick reference

Once you are set up, these are the commands worth remembering. All of them are
run from inside the `agentic-portfolio-manager` folder.

| I want to... | Command |
|---|---|
| Start the app | `uv run streamlit run app.py` |
| Update market data | `uv run python -m scraper.bhavcopy` |
| See what data I have | `uv run python -m core.storage summary` |
| Find my database file | `uv run python -m core.storage path` |
| Share data with a friend | `uv run python -m core.storage share market-history.sqlite3` |
| Load a friend's data | `uv run python -m core.storage import-shared market-history.sqlite3` |
| Turn on scheduling | `uv run python -m core.scheduler install-task` |
