"""Command-line entry point: `uv run research "your question"`.

Placeholder until the research graph is implemented in Phase 2.
"""

import argparse

from research_system import __version__


def main() -> None:
    """Parse CLI arguments and run a research query."""
    parser = argparse.ArgumentParser(prog="research", description="Multi-agent research system")
    parser.add_argument("query", nargs="?", help="Research question to investigate")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        return
    print("The research graph is not implemented yet (Phase 2).")
