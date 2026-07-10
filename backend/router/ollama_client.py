import ollama

def call_ollama(prompt: str, model: str = "llama3.2") -> dict:
    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
    return {
        "text": response["message"]["content"],
        "tier": "cheap",
        "model_id": f"ollama/{model}",
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }
