
import os
import re
import time
import pandas as pd
from groq import Groq
from dotenv import load_dotenv
from scipy.stats import spearmanr

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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

MODEL = "openai/gpt-oss-20b"


def parse_score(raw: str):
    match = re.search(r'\b([0-9]|10)\b', raw.strip())
    return int(match.group(1)) if match else None


def label_query(query: str, retries: int = 2):
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=5,
                temperature=0,
                messages=[{"role": "user", "content": LABEL_PROMPT.format(query=query)}],
            )
            raw = response.choices[0].message.content.strip()
            score = parse_score(raw)
            if score is not None:
                return score, raw
        except Exception as e:
            print(f"  API error (attempt {attempt+1}): {e}")
            time.sleep(2)
    return None, "PARSE_FAILED"


def main():
    gold = pd.read_csv("D:\llm-router\backend\dataset_pipeline\datasets\labeled_dataset\gold_labeled_queries.csv")

    model_scores, raws = [], []
    for i, row in gold.iterrows():
        score, raw = label_query(str(row["query"]))
        model_scores.append(score if score is not None else -1)
        raws.append(raw)
        if i % 20 == 0:
            print(f"{i}/{len(gold)}")
        time.sleep(0.25)

    gold["model_score"] = model_scores
    gold["model_raw"] = raws
    gold.to_csv("D:\llm-router\dataset_pipeline\datasets\gold_validation_results.csv", index=False)

    valid = gold[gold["model_score"] >= 0].copy()
    parse_fail_rate = 1 - len(valid) / len(gold)
    mae = (valid["gold_score"] - valid["model_score"]).abs().mean()
    within_1 = (valid["gold_score"] - valid["model_score"]).abs().le(1).mean()
    within_2 = (valid["gold_score"] - valid["model_score"]).abs().le(2).mean()
    rho, pval = spearmanr(valid["gold_score"], valid["model_score"])

    print("\n" + "=" * 50)
    print(f"Parse failure rate: {parse_fail_rate:.2%}")
    print(f"MAE: {mae:.2f}")
    print(f"% within 1 point:  {within_1:.1%}")
    print(f"% within 2 points: {within_2:.1%}")
    print(f"Spearman correlation: {rho:.3f} (p={pval:.4f})")
    print("=" * 50)

    if mae > 1.5 or rho < 0.6:
        print("\n⚠️  Agreement is weak. Fix the prompt before labeling the full 10k.")
        print("Inspect gold_validation_results.csv for the worst-disagreement rows:")
        worst = valid.assign(diff=(valid["gold_score"] - valid["model_score"]).abs())
        worst = worst.sort_values("diff", ascending=False).head(15)
        print(worst[["query", "gold_score", "model_score"]].to_string())
    else:
        print("\n✅ Agreement looks acceptable. Safe to proceed to full labeling.")


if __name__ == "__main__":
    main()