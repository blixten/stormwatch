#!/usr/bin/env python3
"""StormWatch – Realtidsövervakning av stormen Dave över svenska västkusten."""
import asyncio
import sys


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    from stormwatch.app import StormWatchApp
    app = StormWatchApp()
    app.run()


if __name__ == "__main__":
    main()
