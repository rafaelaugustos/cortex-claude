from cortex_claude.server.app import mcp, _init_engine


def main() -> None:
    _init_engine()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
