import asyncio
import shutil
import tempfile
from pathlib import Path

from cortex_claude.core.engine import CortexEngine


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="cortex_demo_"))
    engine = CortexEngine(base_path=tmp)

    print("=== Cortex Claude Phase 2 Demo ===\n")

    memories = [
        ("The auth service uses JWT tokens with 24-hour expiry. Refresh tokens are stored in httpOnly cookies.", ["auth", "jwt"]),
        ("The API is rate limited to 1000 requests per minute per API key. Rate limiting uses a sliding window algorithm.", ["api", "rate-limit"]),
        ("PostgreSQL is the primary database. We use JSONB columns for flexible metadata storage.", ["database", "postgresql"]),
        ("The frontend is built with React 18 and TypeScript. State management uses Zustand.", ["frontend", "react"]),
        ("Deployments go through GitHub Actions CI/CD. Production runs on AWS ECS Fargate.", ["infra", "deploy"]),
    ]

    print("--- Saving memories (with fact extraction + summarization) ---\n")
    for content, tags in memories:
        result = await engine.save(content=content, tags=tags)
        print(f"  [{result.scope}] {result.tokens_stored} tokens | {content[:60]}...")

    # Show extracted facts
    print("\n--- Knowledge Graph (cortex_facts) ---\n")
    for topic in ["auth", "api", "postgresql", "react", "deploy"]:
        facts = await engine.get_facts(topic=topic)
        if facts:
            for f in facts:
                print(f"  {f.subject} → {f.relation} → {f.object} ({f.confidence:.1f})")

    # Progressive recall demo
    print("\n--- Progressive Recall Demo ---\n")

    print("  depth='facts' (cheapest):")
    r = await engine.recall("authentication", max_tokens=200, depth="facts")
    for m in r.memories:
        print(f"    {m.content}")
    print(f"    → {r.total_tokens} tokens\n")

    print("  depth='summaries':")
    r = await engine.recall("authentication", max_tokens=200, depth="summaries")
    for m in r.memories:
        print(f"    {m.content[:80]}...")
    print(f"    → {r.total_tokens} tokens\n")

    print("  depth='full':")
    r = await engine.recall("authentication", max_tokens=500, depth="full")
    for m in r.memories:
        print(f"    {m.content[:80]}...")
    print(f"    → {r.total_tokens} tokens\n")

    print("  depth='auto' (progressive):")
    r = await engine.recall("authentication", max_tokens=200, depth="auto")
    for m in r.memories:
        print(f"    {m.content[:80]}...")
    print(f"    → {r.total_tokens} tokens\n")

    # Dedup test
    print("--- Deduplication ---\n")
    await engine.save(content="The API is rate limited to 1000 requests per minute per API key.")
    r = await engine.recall("rate limit", depth="full", max_tokens=1000)
    print(f"  After saving near-duplicate: {len(r.memories)} unique results")

    engine.close()
    shutil.rmtree(tmp)
    print("\n=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
