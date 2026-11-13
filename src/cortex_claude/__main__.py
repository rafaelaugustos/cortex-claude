import sys


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "hook":
        from cortex_claude.hooks import run_hook
        run_hook(sys.argv[2] if len(sys.argv) > 2 else "", client=sys.argv[3] if len(sys.argv) > 3 else 'claude')
    elif cmd == 'recovery':
        from cortex_claude.reliability.cli import main as recovery_main
        recovery_main(sys.argv[2:])
    elif cmd == "learning":
        from cortex_claude.hooks import learning_cli
        learning_cli(sys.argv[2:])
    elif cmd == "setup":
        from cortex_claude.setup import run_setup
        run_setup(hooks_only="--hooks-only" in sys.argv)
    elif cmd == "daemon":
        _run_daemon()
    elif cmd == "web":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 37800
        from cortex_claude.web.server import run_web
        run_web(port=port)
    else:
        from cortex_claude.server.app import mcp, _record_connection
        _record_connection()
        mcp.run(transport="stdio")


def _run_daemon() -> None:
    import fcntl
    import os
    from pathlib import Path

    home = Path(os.environ.get('CORTEX_HOME', str(Path.home() / '.cortex-claude'))).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    with (home / 'daemon.lock').open('a') as process_lock:
        try:
            fcntl.flock(process_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        # Reject duplicate processes before loading the engine and its dependencies.
        import asyncio
        from cortex_claude.daemon import CortexDaemon

        daemon = CortexDaemon()
        try:
            asyncio.run(daemon.start(process_lock))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
