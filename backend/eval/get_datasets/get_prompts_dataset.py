import os
import pandas as pd
from datasets import load_dataset

# 1. Create the directory to avoid OSError
os.makedirs("eval", exist_ok=True)

# 2. Load the dataset
ds = load_dataset("fka/prompts.chat", split="train")

# 3. Shuffle and select 1,700 samples
sample = ds.shuffle(seed=42).select(range(1700))

# 4. Use 'prompt' from the dataset as the 'query' column
df = pd.DataFrame({"query": [x["prompt"] for x in sample]})

# 5. Save to the folder
df.to_csv("eval/prompts_dataset.csv", index=False)

print(f"Success! Saved {len(df)} rows to eval/prompts_dataset.csv")
print(df.head())
