# RouteWise — Production Scaling & Improvements Guide

> A production roadmap for scaling the RouteWise LLM Router from a prototype to a high-availability, low-latency system capable of handling **1,000+ Requests Per Second (RPS)**.

---

# Overview

This document outlines the architectural improvements, infrastructure upgrades, and machine learning enhancements required to transform RouteWise into a production-grade AI routing platform.

The focus areas include:

- Horizontal scalability
- Distributed state management
- High-performance semantic caching
- Fully asynchronous architecture
- Production monitoring
- ML inference optimization
- Security improvements
- Cost optimization

---

# Target Production Architecture

```
                    Client / SDK
                          │
                     HTTPS Requests
                          │
               Application Load Balancer
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
  FastAPI Node       FastAPI Node       FastAPI Node
      │                   │                   │
      ├──────────── Shared Redis Cluster ─────────────┤
      │        Rate Limits • Circuit Breakers         │
      │        Round Robin Keys • Cache              │
      │
      ├──────────── Postgres + pgvector ─────────────┤
      │        Semantic Cache                        │
      │        Query Logs                            │
      │
      └──────────── Redis Streams / Kafka ───────────┐
                                                     │
                                       Background Workers
                                    Celery / RQ / Cron Jobs
                                                     │
                                        Analytics / Alerts
```

---

# 1. Distributed State Management

## Current Implementation

- Rate limiting stored in local memory
- Circuit breaker state maintained per server
- API key pools exist independently on each node

## Problem

When multiple FastAPI instances are deployed:

- Rate limits become inconsistent
- Circuit breakers are isolated
- Load balancing becomes uneven
- Failed providers may continue receiving requests

## Production Upgrade

### Redis-Based Rate Limiting

Implement:

- Sliding Window
- Token Bucket

using:

```
Redis Sorted Sets

ZADD
ZREMRANGEBYSCORE
```

---

### Shared Circuit Breakers

Move all breaker states into Redis.

Benefits:

- Global cooldown state
- Coordinated failover
- Immediate propagation across servers

---

### Shared API Key Pool

Store:

- round robin indexes
- cooldown timestamps

inside Redis Hashes.

Result:

- Even provider utilization
- Consistent key rotation

---

# 2. High Performance Semantic Cache

## Current Implementation

Current flow:

1. Load last 500 cached queries
2. Deserialize JSON embeddings
3. Compute cosine similarity in Python
4. Return best match

Complexity:

```
O(N)
```

---

## Problems

- Database load on every request
- Large memory allocations
- High CPU usage
- Poor scalability

---

## Production Upgrade

Replace Python similarity search with vector search.

Options:

- PostgreSQL + pgvector
- Pinecone
- Qdrant
- Milvus

---

### Store Embeddings

```
embedding VECTOR(384)
```

---

### Vector Search

```sql
SELECT
    id,
    query,
    response,
    tier,
    model_id,
    original_cost_usd,
    embedding <=> :query_embedding AS distance
FROM query_cache
ORDER BY distance
LIMIT 1;
```

Use:

- HNSW Index
- Cosine Distance
- Distance Threshold

Benefits:

- Sub-millisecond search
- Millions of embeddings
- Minimal memory usage

---

# 3. Fully Asynchronous Backend

## Current Implementation

Current code uses:

- synchronous HTTP clients
- synchronous SQLAlchemy sessions
- thread pools

Problems:

- Thread blocking
- Context switching
- Limited concurrency

---

## Production Upgrade

### Async Model Providers

Replace with:

- AsyncOpenAI
- AsyncAnthropic
- Async Gemini SDK

Example:

```python
response = await client.chat.completions.create(...)
```

---

### Async Database

Use:

- SQLAlchemy AsyncIO
- asyncpg

---

### PgBouncer

Introduce PgBouncer for:

- connection pooling
- transaction mode
- high concurrency

---

# 4. Asynchronous Logging Pipeline

## Current Implementation

Each request:

- opens SQL transaction
- inserts log
- commits immediately

Alerts:

- computed periodically
- scan entire request history

---

## Problems

- High latency
- Database bottleneck
- Large aggregation queries

---

## Production Upgrade

### Queue-Based Logging

Use:

- Redis Streams
- Kafka
- RabbitMQ
- AWS SQS

Flow:

```
API

↓

Message Queue

↓

Background Worker

↓

Batch Insert

↓

Postgres
```

---

### Batch Inserts

Write logs every:

- 5–10 seconds

Batch size:

```
1000 rows
```

---

### Table Partitioning

Partition:

```
request_logs

↓

Daily

or

Weekly
```

Benefits:

- Faster queries
- Easier archival
- Better indexing

---

### Alert Worker

Move alerts into:

- Celery Beat
- Kubernetes CronJob

Maintain aggregates in:

- Redis
- TimescaleDB

instead of scanning raw tables.

---

# 5. Dedicated ML Inference Server

## Current Implementation

FastAPI loads:

- MiniLM
- SentenceTransformer
- Scikit-Learn Regressor

Problems:

- High CPU usage
- Large container size
- Python GIL bottleneck

---

## Production Upgrade

### Option 1

Export models to:

```
ONNX Runtime
```

Benefits:

- Smaller memory footprint
- Faster CPU inference

---

### Option 2

Deploy dedicated inference server.

Examples:

- Triton Inference Server
- vLLM
- BentoML

Communication:

```
FastAPI

↓

gRPC

↓

Inference Server
```

Benefits:

- GPU acceleration
- Independent scaling
- Lower latency

---

# 6. Intelligent Web Search Routing

## Current Implementation

Uses regex rules to determine whether web search is required.

Problems:

False positives.

Example:

```
Design a current-limiting circuit
```

Triggers search because of the word:

```
current
```

---

## Production Upgrade

Train a lightweight classifier.

Predict:

```
Needs Web Search

vs

Reasoning Only
```

Possible models:

- MiniLM
- DistilBERT
- Fine-tuned BERT

Benefits:

- Fewer unnecessary searches
- Lower API costs
- Better routing accuracy

---

# 7. Active Learning Pipeline

Current router uses a static ML model.

Instead:

## Step 1

Collect feedback:

- thumbs up
- thumbs down
- edits
- quality score

---

## Step 2

Detect bad routing decisions.

Example:

Cheap model selected

↓

Poor user feedback

↓

Send to review queue

---

## Step 3

Generate gold labels

Use a stronger frontier model to relabel difficult queries.

---

## Step 4

Monthly Retraining

Automate:

```
Dataset

↓

Training

↓

Validation

↓

CI/CD

↓

Deployment
```

---

# 8. Live Pricing Synchronization

Current pricing comes from static SQL.

Instead:

Schedule a daily job that synchronizes pricing from:

- OpenAI
- Groq
- OpenRouter

Update:

```
model_pricing
```

Benefits:

- Accurate routing
- Better cost optimization

---

# 9. Security Hardening

Current implementation:

Regex-based prompt injection detection.

Problems:

Easy to bypass.

---

## Production Upgrade

Replace regex with:

- Llama Guard
- Lakera Guard
- NeMo Guardrails

Benefits:

- Better jailbreak detection
- Prompt injection protection
- Safer web search

---

# Summary Matrix

| Feature | Current | Production Upgrade | Benefit |
|----------|----------|-------------------|----------|
| Rate Limiter | In-memory | Redis Sliding Window | Horizontal scaling |
| Circuit Breaker | Local state | Shared Redis | Coordinated failover |
| Semantic Cache | Python cosine similarity | pgvector + HNSW | Millisecond search |
| HTTP Clients | Synchronous | Fully async | High concurrency |
| Database | Blocking SQLAlchemy | AsyncIO + asyncpg | Lower latency |
| Logging | Direct SQL writes | Kafka / Redis Streams | Non-blocking API |
| Alerts | In-process scheduler | Celery Beat / CronJob | Reliable alerting |
| ML Inference | CPU inside FastAPI | ONNX / Triton | Faster inference |
| Web Search Routing | Regex | Intent Classifier | Better accuracy |
| Pricing | Static SQL | Daily API sync | Accurate costs |
| Security | Regex detection | Llama Guard | Better protection |

---

# Recommended Production Stack

## API

- FastAPI
- Uvicorn
- Gunicorn

## Load Balancer

- NGINX
- AWS ALB

## Cache

- Redis Cluster

## Database

- PostgreSQL
- pgvector

## Queue

- Redis Streams
- Kafka
- RabbitMQ

## Workers

- Celery
- RQ

## Scheduler

- Celery Beat
- Kubernetes CronJob

## ML

- ONNX Runtime
- Triton Inference Server
- BentoML

## Vector Search

- pgvector
- Pinecone
- Qdrant
- Milvus

## Monitoring

- Prometheus
- Grafana
- Loki

## Deployment

- Docker
- Kubernetes
- Helm

## Security

- Llama Guard
- Lakera Guard
- NeMo Guardrails

---

# Final Goal

Transform RouteWise into a production-ready LLM routing platform capable of:

- Handling **1,000+ RPS**
- Horizontal autoscaling
- Distributed rate limiting
- Shared circuit breakers
- Sub-millisecond semantic caching
- Fully asynchronous request processing
- Dedicated ML inference
- Intelligent web search routing
- Continuous model improvement
- Automated pricing synchronization
- Enterprise-grade security
- Low latency and high availability