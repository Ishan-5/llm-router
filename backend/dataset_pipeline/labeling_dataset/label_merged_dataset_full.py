import os
import re
import sys
import time
import pandas as pd
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "llama-3.1-8b-instant" 

LABEL_PROMPT = """You are scoring queries for an LLM cost-routing system. Score how difficult this query is for an AI model to answer well, on a 0-10 scale.

0-2 = trivial: greetings, single fact lookup, basic conversion, simple extraction, casual short creative/subjective requests with no real effort needed (opinions, one-liners, simple preferences)
3-5 = moderate: requires some explanation, a short reasoning chain, small-to-moderate code, summarizing/analyzing a longer passage, or a creative task with a few explicit constraints
6-8 = hard: multi-step reasoning where steps depend on each other, non-trivial code or system design, comparing/synthesizing multiple sources or ideas, long-form writing with many constraints
9-10 = expert: deep domain expertise required, complex multi-part synthesis, research-level problems

CRITICAL RULE: A query having NO single objectively correct answer (an opinion question, a casual creative request, a personal preference question) does NOT make it hard. Score based on how much actual effort/reasoning/generation work is required, not on whether the answer is subjective. "What makes a good parent?" and "design a logo for a band" are casual, low-effort requests -- score them LOW, not high, even though they're open-ended.

Ignore the LENGTH of the query. A long passage to summarize is not automatically hard; a short but genuinely multi-step or technical question can be hard.

Examples:
"What is the capital of France?" -> 0
"Convert 5 miles to km" -> 1
"What makes a good parent?" -> 2
"How do I decorate my new home?" -> 1
"Generate a unique motto for yourself." -> 2
"Design a logo for a rock-and-roll band." -> 3
"Describe what your ideal pet cat would look like." -> 2
"Summarize this paragraph in 2 sentences: [short paragraph]" -> 2
"Explain how binary search works with an example" -> 3
"Write a Python function to check if a string is a palindrome" -> 4
"Extract all person names and organizations from this news article: [article]" -> 4
"Compare functional vs object-oriented programming and recommend one for a given use case" -> 6
"Design a caching layer for a distributed rate limiter" -> 8
"Debug this race condition in my async code: [code]" -> 8
"Write a 1000-word short story with a twist ending" -> 7

Respond with ONLY a single integer from 0 to 10. No words, no explanation.

Query: {query}

Score:"""


class RateLimitStop(Exception):
    """Raised when we hit a rate limit -- stop the run, don't burn retries."""
    pass


def parse_score(raw: str):
    match = re.search(r'\b([0-9]|10)\b', raw.strip())
    return int(match.group(1)) if match else None


def label_query(query: str):
    query = str(query)[:6000]
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=5,
            temperature=0,
            messages=[{"role": "user", "content": LABEL_PROMPT.format(query=query)}],
        )
        raw = response.choices[0].message.content.strip()
        score = parse_score(raw)
        return (score if score is not None else -1), raw, ("model" if score is not None else "parse_failed")
    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate_limit" in msg:
            raise RateLimitStop(msg)
    
        time.sleep(1)
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=5,
                temperature=0,
                messages=[{"role": "user", "content": LABEL_PROMPT.format(query=query)}],
            )
            raw = response.choices[0].message.content.strip()
            score = parse_score(raw)
            return (score if score is not None else -1), raw, ("model" if score is not None else "parse_failed")
        except Exception as e2:
            if "429" in str(e2) or "rate_limit" in str(e2):
                raise RateLimitStop(str(e2))
            return -1, f"ERROR: {e2}", "api_error"


def main(input_path, output_path, checkpoint_every=100, sleep_between=0.15):
    df = pd.read_csv(input_path)

    if os.path.exists(output_path):
        done = pd.read_csv(output_path)
        print(f"Resuming: {len(done)} rows already labeled.")
    else:
        done = pd.DataFrame(columns=["query", "difficulty_score", "raw_response", "label_source"])

    labeled_queries = set(done["query"].astype(str))
    remaining = df[~df["query"].astype(str).isin(labeled_queries)]
    print(f"{len(remaining)} rows remaining out of {len(df)}")

    results = done.to_dict("records")
    buffer = []

    try:
        for i, (_, row) in enumerate(remaining.iterrows()):
            score, raw, source = label_query(row["query"])
            buffer.append({
                "query": row["query"],
                "difficulty_score": score,
                "raw_response": raw,
                "label_source": source,
            })

            if (i + 1) % checkpoint_every == 0:
                results.extend(buffer)
                buffer = []
                pd.DataFrame(results).to_csv(output_path, index=False)
                fails = sum(1 for r in results if r["label_source"] != "model")
                print(f"[{i+1}/{len(remaining)}] checkpointed. non-model labels so far: {fails} ({fails/len(results):.2%})")

            time.sleep(sleep_between)

    except RateLimitStop as e:
        print(f"\n🛑 Hit rate limit, stopping cleanly: {e}")
        print("Progress is saved. Re-run this script later (today's quota reset, or tomorrow) to resume.")

    finally:
        if buffer:
            results.extend(buffer)
        if results:
            pd.DataFrame(results).to_csv(output_path, index=False)
            print(f"\nSaved {len(results)} labeled rows to {output_path}")


if __name__ == "__main__":
    main(
        input_path=r"D:\llm-router\backend\dataset_pipeline\datasets\raw\filtered_queries_6500.csv",
        output_path=r"D:\llm-router\backend\dataset_pipeline\datasets\labeled_dataset\labeled_queries_full.csv",
    )