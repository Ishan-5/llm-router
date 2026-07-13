"""
Seed script -- fires ~200 varied queries through the router to make the
dashboard look alive with real data across tiers, cache hits, and multiple days.

Usage:
    cd backend
    python scripts/seed_requests.py --api-key rw_xxx
    python scripts/seed_requests.py --api-key rw_xxx --url https://llm-router-d2b2.onrender.com
    python scripts/seed_requests.py --api-key rw_xxx --count 100 --delay 0.5
"""
import argparse
import time
import random
import requests

# ---------------------------------------------------------------------------
# Query bank -- spread across tiers
# ---------------------------------------------------------------------------

CHEAP_QUERIES = [
    "What is the capital of France?",
    "What is 15 multiplied by 7?",
    "How many days are in a leap year?",
    "What color is the sky?",
    "Who wrote Romeo and Juliet?",
    "What is the boiling point of water in Celsius?",
    "How many continents are there?",
    "What is the largest planet in our solar system?",
    "What language is spoken in Brazil?",
    "What is the square root of 144?",
    "How many sides does a hexagon have?",
    "What is the capital of Japan?",
    "Who painted the Mona Lisa?",
    "What is H2O?",
    "How many hours are in a day?",
    "What is the fastest land animal?",
    "What year did World War II end?",
    "What is the currency of the UK?",
    "How many planets are in our solar system?",
    "What is the capital of Australia?",
    "What does CPU stand for?",
    "What is the tallest mountain in the world?",
    "How many bones are in the human body?",
    "What is the chemical symbol for gold?",
    "Who invented the telephone?",
    "What is the capital of Germany?",
    "What is 100 divided by 4?",
    "What is the longest river in the world?",
    "How many strings does a standard guitar have?",
    "What is the capital of Canada?",
    "What does HTML stand for?",
    "What is the speed of light?",
    "Who was the first US president?",
    "What is the smallest country in the world?",
    "How many weeks are in a year?",
    "What is the capital of Italy?",
    "What does RAM stand for?",
    "What is the atomic number of carbon?",
    "Who wrote Harry Potter?",
    "What is the capital of Spain?",
    "What is 2 to the power of 10?",
    "What is the most spoken language in the world?",
    "How many chambers does the human heart have?",
    "What is the capital of Brazil?",
    "What does GPS stand for?",
    "What is the freezing point of water in Fahrenheit?",
    "Who invented the light bulb?",
    "What is the capital of India?",
    "How many zeros are in one million?",
    "What is the largest ocean on Earth?",
]

MID_QUERIES = [
    "Explain the difference between REST and GraphQL APIs.",
    "What is the CAP theorem in distributed systems?",
    "How does HTTPS work?",
    "Explain the concept of recursion with an example.",
    "What is the difference between SQL and NoSQL databases?",
    "How does garbage collection work in Python?",
    "Explain what a neural network is in simple terms.",
    "What is the difference between TCP and UDP?",
    "How does a hash table work?",
    "Explain the MVC design pattern.",
    "What is Docker and why is it useful?",
    "How does OAuth 2.0 work?",
    "Explain the difference between a process and a thread.",
    "What is Big O notation and why does it matter?",
    "How does a binary search tree work?",
    "What is the difference between synchronous and asynchronous programming?",
    "Explain what a CDN is and how it works.",
    "What is the difference between stack and heap memory?",
    "How does a load balancer work?",
    "Explain the concept of database indexing.",
    "What is the difference between authentication and authorization?",
    "How does React's virtual DOM work?",
    "Explain what microservices architecture is.",
    "What is a deadlock and how can it be prevented?",
    "How does public key cryptography work?",
    "Explain the difference between monolithic and microservices architecture.",
    "What is a message queue and when would you use one?",
    "How does DNS resolution work?",
    "Explain the concept of eventual consistency.",
    "What is the difference between horizontal and vertical scaling?",
    "How does a relational database handle transactions?",
    "Explain what a webhook is.",
    "What is the difference between compiled and interpreted languages?",
    "How does rate limiting work in APIs?",
    "Explain the concept of idempotency in HTTP methods.",
    "What is a reverse proxy and how does it differ from a forward proxy?",
    "How does JWT authentication work?",
    "Explain the difference between optimistic and pessimistic locking.",
    "What is a bloom filter and when would you use one?",
    "How does the event loop work in JavaScript?",
    "Explain what CORS is and why it exists.",
    "What is the difference between a mutex and a semaphore?",
    "How does consistent hashing work?",
    "Explain the concept of database sharding.",
    "What is the difference between eager and lazy loading?",
    "How does a circuit breaker pattern work?",
    "Explain what a Merkle tree is.",
    "What is the difference between memoization and caching?",
    "How does WebSocket differ from HTTP?",
    "Explain the concept of dependency injection.",
]

FRONTIER_QUERIES = [
    "Design a distributed rate limiter that works across multiple server instances.",
    "How would you design a URL shortener like bit.ly that handles 100 million requests per day?",
    "Design a real-time collaborative document editing system like Google Docs.",
    "How would you architect a recommendation system for a streaming platform with 50 million users?",
    "Design a distributed cache system with consistency guarantees.",
    "How would you build a fault-tolerant message queue from scratch?",
    "Design a system to detect fraud in real-time for a payment processor handling 10,000 TPS.",
    "How would you design the backend for a ride-sharing app like Uber?",
    "Design a distributed search engine that can index 1 billion documents.",
    "How would you architect a multi-region database with zero downtime deployments?",
    "Design a real-time analytics pipeline that processes 1 million events per second.",
    "How would you build a distributed file storage system like S3?",
    "Design a notification system that can deliver 10 million push notifications per hour.",
    "How would you architect a social media feed that scales to 500 million users?",
    "Design a distributed transaction system that maintains ACID properties across microservices.",
    "How would you build a global CDN from scratch?",
    "Design a machine learning feature store for a company with 100+ ML models in production.",
    "How would you architect a video streaming platform like YouTube?",
    "Design a distributed job scheduler that handles millions of cron jobs.",
    "How would you build a real-time bidding system for online advertising?",
    "Design a system for detecting distributed denial of service attacks in real time.",
    "How would you architect a multi-tenant SaaS platform with strict data isolation?",
    "Design a globally distributed key-value store with tunable consistency.",
    "How would you build a system to handle 1 million concurrent WebSocket connections?",
    "Design a data pipeline for ingesting and processing IoT sensor data from 10 million devices.",
    "How would you architect a banking system that handles international transfers with compliance?",
    "Design a content moderation system that processes 100 million user-generated posts per day.",
    "How would you build a distributed tracing system for a microservices architecture?",
    "Design a real-time leaderboard system for a game with 10 million concurrent players.",
    "How would you architect a healthcare data platform that meets HIPAA compliance requirements?",
    "Design a system for A/B testing that can run 1000 simultaneous experiments.",
    "How would you build a distributed consensus system using the Raft algorithm?",
    "Design a semantic search engine that understands natural language queries.",
    "How would you architect an event sourcing system for a financial ledger?",
    "Design a multi-cloud disaster recovery system with RPO of 1 minute.",
    "How would you build a real-time collaborative whiteboard for 10,000 simultaneous users?",
    "Design a system to detect and prevent account takeover attacks at scale.",
    "How would you architect a data warehouse that handles petabyte-scale analytics?",
    "Design a distributed lock manager that prevents split-brain scenarios.",
    "How would you build a zero-knowledge proof system for private transactions?",
    "Design a chaos engineering platform for testing distributed system resilience.",
    "How would you architect a GraphQL federation layer for 50 microservices?",
    "Design a system for real-time anomaly detection in time-series data.",
    "How would you build a distributed workflow engine like Apache Airflow from scratch?",
    "Design a privacy-preserving analytics system using differential privacy.",
    "How would you architect a multi-model AI inference platform with auto-scaling?",
    "Design a system for managing database schema migrations across 100 microservices.",
    "How would you build a real-time collaborative code editor with conflict resolution?",
    "Design a distributed secret management system for a large enterprise.",
    "How would you architect a platform for running untrusted code safely at scale?",
]

# near-duplicate pairs -- will trigger cache hits
CACHE_PAIRS = [
    ("What is the capital of France?", "What's the capital city of France?"),
    ("Explain how HTTPS works.", "How does HTTPS work?"),
    ("What is Docker?", "What is Docker and why is it useful?"),
    ("Design a URL shortener system.", "How would you design a URL shortener like bit.ly?"),
    ("What is the CAP theorem?", "Explain the CAP theorem in distributed systems."),
]


def send_query(base_url: str, api_key: str, query: str, override_tier: str | None = None) -> dict | None:
    try:
        payload = {"query": query}
        if override_tier:
            payload["override_tier"] = override_tier
        response = requests.post(
            f"{base_url}/route",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if response.ok:
            return response.json()
        else:
            print(f"  ERROR {response.status_code}: {response.text[:100]}")
            return None
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Seed the router with varied queries")
    parser.add_argument("--api-key", required=True, help="Your routewise API key (rw_xxx)")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Router base URL")
    parser.add_argument("--count", type=int, default=200, help="Total queries to send")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    parser.add_argument("--force-tier", choices=["cheap", "mid", "frontier"], default=None, help="Force all queries to a specific tier")
    parser.add_argument("--skip-cache-pairs", action="store_true", help="Skip near-duplicate cache pairs (useful with --force-tier)")
    args = parser.parse_args()

    print(f"Seeding {args.count} queries to {args.url}")
    print(f"Using API key: {args.api_key[:12]}...")
    if args.force_tier:
        print(f"Forcing all queries to tier: {args.force_tier}")
    print()

    # build query list: ~40% cheap, ~35% mid, ~25% frontier
    cheap_count  = int(args.count * 0.40)
    mid_count    = int(args.count * 0.35)
    frontier_count = args.count - cheap_count - mid_count

    queries = (
        [(q, None) for q in random.sample(CHEAP_QUERIES * 4, cheap_count)] +
        [(q, None) for q in random.sample(MID_QUERIES * 4, mid_count)] +
        [(q, None) for q in random.sample(FRONTIER_QUERIES * 4, frontier_count)]
    )

    # add ~10 cache-hit pairs at the end (skip if --skip-cache-pairs)
    if not args.skip_cache_pairs:
        for original, duplicate in CACHE_PAIRS[:5]:
            queries.append((original, None))
            queries.append((duplicate, None))

    random.shuffle(queries)

    # if force-tier, override all
    if args.force_tier:
        queries = [(q, args.force_tier) for q, _ in queries]

    total = len(queries)
    success = 0
    cache_hits = 0
    tier_counts = {"cheap": 0, "mid": 0, "frontier": 0}
    total_cost = 0.0

    for i, (query, override) in enumerate(queries, 1):
        print(f"[{i}/{total}] {query[:70]}{'...' if len(query) > 70 else ''}")
        result = send_query(args.url, args.api_key, query, override)

        if result:
            success += 1
            tier = result.get("routed_to", "unknown")
            cost = result.get("cost_usd", 0.0)
            cached = result.get("cache_hit", False)
            score = result.get("difficulty_score")

            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            total_cost += cost
            if cached:
                cache_hits += 1

            score_str = f"score={score:.1f} " if score is not None else ""
            print(f"  → {tier} | {score_str}cost=${cost:.6f} | {'CACHE HIT' if cached else 'live'}")

        time.sleep(args.delay)

    print()
    print("=" * 50)
    print(f"Done. {success}/{total} succeeded")
    print(f"Tier distribution: {tier_counts}")
    print(f"Cache hits: {cache_hits}")
    print(f"Total cost: ${total_cost:.4f}")
    print("=" * 50)


if __name__ == "__main__":
    main()
