import os
import pandas as pd
from datasets import load_dataset

# Ensure target directory exists
os.makedirs("eval", exist_ok=True)

# Retrieve prompts dataset from source
ds = load_dataset("fka/prompts.chat", split="train")

# Select a randomized subset of 1,700 samples
sample = ds.shuffle(seed=42).select(range(1700))

# Extract prompt fields to match database query column mapping
df = pd.DataFrame({"query": [x["prompt"] for x in sample]})

# Persist sampled queries to CSV
df.to_csv("eval/prompts_dataset.csv", index=False)

print(f"Success! Saved {len(df)} rows to eval/prompts_dataset.csv")
print(df.head())
