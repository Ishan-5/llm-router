from datasets import load_dataset

ds = load_dataset("databricks/databricks-dolly-15k", split="train")
sample = ds.shuffle(seed=42).select(range(2500))

import pandas as pd
df = pd.DataFrame({"query": [x["instruction"] for x in sample]})
df.to_csv("eval/dolly_dataset.csv", index=False)
print(df.head())
print(f"Total queries: {len(df)}")