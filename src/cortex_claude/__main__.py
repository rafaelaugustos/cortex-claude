import asyncio

from cortex_claude.server.app import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
