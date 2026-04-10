import asyncio
import shutil
import tempfile
from pathlib import Path

from cortex_claude.core.engine import CortexEngine


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="cortex_demo_"))
    engine = CortexEngine(base_path=tmp)

    print("=== Cortex Claude Demo ===\n")
    print(f"Storage: {tmp}\n")

    # Save some memories
    memories = [
        ("The auth service uses JWT tokens with 24-hour expiry. Refresh tokens are stored in httpOnly cookies.", ["auth", "jwt"]),
        ("The API is rate limited to 1000 requests per minute per API key. Rate limiting uses a sliding window algorithm.", ["api", "rate-limit"]),
        ("PostgreSQL is the primary database. We use JSONB columns for flexible metadata storage.", ["database", "postgresql"]),
        ("The frontend is built with React 18 and TypeScript. State management uses Zustand.", ["frontend", "react"]),
        ("Deployments go through GitHub Actions CI/CD. Production runs on AWS ECS Fargate.", ["infra", "deploy"]),
    ]

    print("--- Saving memories ---\n")
    for content, tags in memories:
        result = await engine.save(content=content, tags=tags)
        print(f"  [{result.scope}] {result.tokens_stored} tokens | {content[:60]}...")

    print("\n--- Recall tests ---\n")

    queries = [
        ("How does authentication work?", 200),
        ("What database do we use?", 200),
        ("How are deployments done?", 200),
        ("rate limiting", 100),
        ("frontend stack", 200),
    ]

    for query, budget in queries:
        print(f'  Query: "{query}" (budget: {budget} tokens)')
        result = await engine.recall(query=query, max_tokens=budget)

        if not result.memories:
            print("    No results.\n")
            continue

        for item in result.memories:
            tags_str = f" [{', '.join(item.tags)}]" if item.tags else ""
            print(f"    score={item.score:.3f}{tags_str}")
            print(f"    {item.content[:80]}...")
        print(f"    Total: {result.total_tokens} tokens\n")

    # Scope isolation test
    print("--- Scope isolation test ---\n")

    await engine.save(content="This is a secret only for project X", scope="project:x")
    await engine.save(content="This is global knowledge shared everywhere", scope="global")

    r1 = await engine.recall(query="secret", scope="project:x")
    r2 = await engine.recall(query="secret", scope="global")

    print(f"  Search 'secret' in project:x → {len(r1.memories)} result(s)")
    print(f"  Search 'secret' in global    → {len(r2.memories)} result(s)")

    engine.close()
    shutil.rmtree(tmp)
    print("\n=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
