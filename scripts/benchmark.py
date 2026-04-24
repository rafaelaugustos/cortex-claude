import asyncio
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from cortex_claude.core.engine import CortexEngine
from cortex_claude.embeddings.tokenizer import count_tokens
from cortex_claude.server.config import CortexConfig

SAMPLE_MEMORIES = [
    "The auth service uses JWT tokens with 24-hour expiry. Refresh tokens are stored in httpOnly cookies with 7-day lifetime.",
    "PostgreSQL is the primary database. We use JSONB columns for flexible metadata storage. Read replicas handle analytics queries.",
    "The API is rate limited to 1000 requests per minute per API key. Rate limiting uses a sliding window algorithm with Redis.",
    "The frontend is built with React 18 and TypeScript. State management uses Zustand. Styling uses Tailwind CSS.",
    "Deployments go through GitHub Actions CI/CD. Production runs on AWS ECS Fargate with auto-scaling. Staging uses a single task.",
    "Logging uses structured JSON format via Winston. Logs are shipped to Datadog via the Datadog agent running as a sidecar.",
    "The search service uses Elasticsearch 8 with custom analyzers for multi-language support. Index rotation happens weekly.",
    "User uploads are stored in S3 with server-side encryption. CloudFront serves as CDN with signed URLs for private content.",
    "The notification service uses Amazon SQS for queueing and SES for email delivery. Push notifications go through Firebase.",
    "GraphQL API is powered by Apollo Server. Schema stitching combines the user, product, and order subgraphs.",
]


async def timed(coro):
    start = time.perf_counter()
    result = await coro
    elapsed = (time.perf_counter() - start) * 1000
    return result, elapsed


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="cortex_bench_"))
    config = CortexConfig(base_path=tmp)
    engine = CortexEngine(config=config)

    print("=" * 60)
    print("  Cortex Claude Benchmark")
    print("=" * 60)

    # Save
    print("\n--- Save Performance ---\n")
    save_times = []
    for i, content in enumerate(SAMPLE_MEMORIES):
        _, elapsed = await timed(engine.save(content=content, tags=[f"bench-{i}"]))
        save_times.append(elapsed)
        print(f"  Save {i+1:2d}: {elapsed:7.1f} ms | {count_tokens(content):3d} tokens")

    print(f"\n  Avg: {statistics.mean(save_times):.1f} ms")
    print(f"  Med: {statistics.median(save_times):.1f} ms")

    # Recall
    queries = [
        "How does authentication work?",
        "What database is used?",
        "How are deployments done?",
        "rate limiting configuration",
        "frontend technology stack",
    ]

    for depth in ["facts", "summaries", "full", "auto"]:
        print(f"\n--- Recall depth='{depth}' ---\n")
        recall_times = []
        recall_tokens = []

        for query in queries:
            result, elapsed = await timed(engine.recall(query=query, max_tokens=500, depth=depth))
            recall_times.append(elapsed)
            recall_tokens.append(result.total_tokens)
            print(f"  '{query[:35]:<35}' {elapsed:7.1f} ms | {result.total_tokens:3d} tok | {len(result.memories)} res")

        print(f"\n  Avg: {statistics.mean(recall_times):.1f} ms | {statistics.mean(recall_tokens):.0f} tokens")

    # Facts
    print("\n--- Facts Query ---\n")
    fact_times = []
    for topic in ["auth", "database", "api", "frontend", "deploy"]:
        result, elapsed = await timed(engine.get_facts(topic=topic))
        fact_times.append(elapsed)
        print(f"  cortex_facts('{topic}'): {elapsed:7.1f} ms | {len(result)} facts")
    print(f"\n  Avg: {statistics.mean(fact_times):.1f} ms")

    # Traversal
    print("\n--- Graph Traversal ---\n")
    for start in ["auth", "postgresql", "api"]:
        result, elapsed = await timed(engine.traverse_graph(start=start, max_hops=2))
        print(f"  traverse('{start}', 2 hops): {elapsed:7.1f} ms | {len(result)} connections")

    # Token efficiency
    print("\n--- Token Efficiency ---\n")
    total_stored = sum(count_tokens(m) for m in SAMPLE_MEMORIES)
    for depth in ["facts", "auto", "full"]:
        result = await engine.recall("tell me everything", max_tokens=2000, depth=depth)
        reduction = (1 - result.total_tokens / total_stored) * 100 if total_stored else 0
        print(f"  depth='{depth:<10}': {result.total_tokens:4d} tok (vs {total_stored} stored) → {reduction:.0f}% reduction")

    # Storage
    status = await engine.status()
    print(f"\n--- Storage ---\n")
    print(f"  Memories: {status.total_memories}")
    print(f"  Facts: {status.total_facts}")
    print(f"  Size: {status.total_size_bytes / 1024:.1f} KB")

    engine.close()
    shutil.rmtree(tmp)
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
