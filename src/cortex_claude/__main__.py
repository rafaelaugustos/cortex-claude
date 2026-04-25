import sys


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "setup":
        from cortex_claude.setup import run_setup
        run_setup()
    elif cmd == "daemon":
        _run_daemon()
    else:
        from cortex_claude.server.app import mcp, _init_engine
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
