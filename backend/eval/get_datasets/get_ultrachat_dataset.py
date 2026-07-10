from datasets import load_dataset

ds = load_dataset("openbmb/UltraChat", split="train")
sample = ds.shuffle(seed=42).select(range(3000))

import pandas as pd
df = pd.DataFrame({"query": [x["data"] for x in sample]})
df.to_csv("eval/ultrachat_dataset.csv", index=False)
print(df.head())
print(f"Total queries: {len(df)}")