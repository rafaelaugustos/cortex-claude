import sys

from cortex_claude.server.app import mcp, _init_engine


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "daemon":
        _run_daemon()
    else:
        _init_engine()
        mcp.run(transport="stdio")


def _run_daemon() -> None:
    import asyncio
    from cortex_claude.daemon import CortexDaemon

    daemon = CortexDaemon()
    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        daemon.close()


if __name__ == "__main__":
    main()
