"""Every command-line entry point must be printable on a plain Windows console.

Windows terminals still default to the cp1252 code page. Python writes argparse
help straight to that stream, so a single curly quote, em-dash or arrow in a
module docstring is enough to make ``--help`` die with a UnicodeEncodeError -
before the user has run anything at all. It is a uniquely bad failure: it hits
newcomers first, on the one command they were told to try, and the traceback
points at ``argparse`` rather than at the offending character.

The suite cannot catch this by running the commands, because pytest captures
output through a UTF-8 pipe where every character encodes fine. So we assert
the property directly: the help text an entry point would print must survive a
round trip through cp1252.
"""

import importlib

import pytest

#: Modules exposing a ``python -m <module> --help`` interface. These are the
#: commands the setup guide tells a new user to run, so they are exactly the
#: ones that must not fail on a fresh machine.
CLI_MODULES = [
    "core.storage",
    "core.scheduler",
    "scraper.bhavcopy",
    "scraper.backfill_nse_fundamentals",
    "backtesting.warm_bars",
]

CONSOLE_ENCODING = "cp1252"


def _help_text(module_name: str) -> str:
    """Render the help an entry point prints, without running its side effects."""
    module = importlib.import_module(module_name)

    for builder in ("_build_parser", "build_parser", "_parser", "make_parser"):
        factory = getattr(module, builder, None)
        if callable(factory):
            return factory().format_help()

    # The rest build their parser inside main(); argparse only ever prints the
    # module docstring it was handed as a description, so check that directly.
    return module.__doc__ or ""


@pytest.mark.parametrize("module_name", CLI_MODULES)
def test_help_survives_a_windows_console(module_name):
    text = _help_text(module_name)
    try:
        text.encode(CONSOLE_ENCODING)
    except UnicodeEncodeError as exc:
        offender = text[exc.start : exc.end]
        line = text[: exc.start].count("\n") + 1
        pytest.fail(
            f"{module_name} help text contains {offender!r} "
            f"(U+{ord(offender[0]):04X}) on line {line}, which a Windows "
            f"console cannot print. Use a plain ASCII equivalent: "
            f"'-' for dashes, '->' for arrows, \"'\" for curly quotes."
        )
