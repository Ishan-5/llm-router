-- Run this once in your Supabase SQL editor.
-- To update a price:  UPDATE model_pricing SET price_per_m_input=X, price_per_m_output=Y, updated_at=NOW() WHERE provider='...' AND model_id='...';
-- To add a new model: INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES (...);
-- To retire a model:  UPDATE model_pricing SET is_active=false WHERE provider='...' AND model_id='...';

CREATE TABLE IF NOT EXISTS model_pricing (
    id SERIAL PRIMARY KEY,
    provider VARCHAR NOT NULL,
    model_id VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    price_per_m_input FLOAT NOT NULL,
    price_per_m_output FLOAT NOT NULL,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_pricing_provider_model ON model_pricing(provider, model_id);

-- ─── Groq ────────────────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('groq', 'llama-3.1-8b-instant',                     'LLaMA 3.1 8B Instant',          0.05,  0.08,  '128k context · 840 TPS'),
('groq', 'llama-3.3-70b-versatile',                  'LLaMA 3.3 70B Versatile',       0.59,  0.79,  '128k context · 394 TPS'),
('groq', 'llama-3.3-70b-specdec',                    'LLaMA 3.3 70B SpecDec',         0.59,  0.99,  'Speculative decoding'),
('groq', 'qwen/qwen3-32b',                           'Qwen3 32B',                     0.29,  0.59,  '131k context · 662 TPS'),
('groq', 'qwen/qwen3.6-27b',                         'Qwen 3.6 27B',                  0.60,  3.00,  '131k context · 500 TPS'),
('groq', 'meta-llama/llama-4-scout-17b-16e-instruct','LLaMA 4 Scout 17Bx16E',         0.11,  0.34,  '128k context · 594 TPS'),
('groq', 'openai/gpt-oss-120b',                      'GPT OSS 120B',                  0.15,  0.60,  '128k context · 500 TPS'),
('groq', 'openai/gpt-oss-20b',                       'GPT OSS 20B',                   0.075, 0.30,  '128k context · 1000 TPS'),
('groq', 'mixtral-8x7b-32768',                       'Mixtral 8x7B',                  0.24,  0.24,  '32k context'),
('groq', 'gemma2-9b-it',                             'Gemma2 9B',                     0.20,  0.20,  NULL);

-- ─── OpenAI ──────────────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('openai', 'gpt-5',          'GPT-5',           1.25,   10.00,  NULL),
('openai', 'gpt-5-mini',     'GPT-5 Mini',      0.25,   2.00,   NULL),
('openai', 'gpt-5-nano',     'GPT-5 Nano',      0.05,   0.40,   NULL),
('openai', 'gpt-5.1',        'GPT-5.1',         1.25,   10.00,  NULL),
('openai', 'gpt-5.2',        'GPT-5.2',         1.75,   14.00,  NULL),
('openai', 'gpt-5.4',        'GPT-5.4',         2.50,   15.00,  'Short context · long context $5/$22.5'),
('openai', 'gpt-5.4-mini',   'GPT-5.4 Mini',    0.75,   4.50,   NULL),
('openai', 'gpt-5.4-nano',   'GPT-5.4 Nano',    0.20,   1.25,   NULL),
('openai', 'gpt-5.5',        'GPT-5.5',         5.00,   30.00,  'Short context · long context $10/$45'),
('openai', 'gpt-5.6-sol',    'GPT-5.6 Sol',     5.00,   30.00,  'Short context · long context $10/$45'),
('openai', 'gpt-5.6-terra',  'GPT-5.6 Terra',   2.50,   15.00,  'Short context · long context $5/$22.5'),
('openai', 'gpt-5.6-luna',   'GPT-5.6 Luna',    1.00,   6.00,   'Short context · long context $2/$9'),
('openai', 'gpt-4o',         'GPT-4o',          2.50,   10.00,  NULL),
('openai', 'gpt-4o-mini',    'GPT-4o Mini',     0.15,   0.60,   NULL),
('openai', 'gpt-4.1',        'GPT-4.1',         2.00,   8.00,   NULL),
('openai', 'gpt-4.1-mini',   'GPT-4.1 Mini',    0.40,   1.60,   NULL),
('openai', 'gpt-4.1-nano',   'GPT-4.1 Nano',    0.10,   0.40,   NULL),
('openai', 'o1',             'o1',              15.00,  60.00,  NULL),
('openai', 'o1-mini',        'o1 Mini',          1.10,   4.40,   NULL),
('openai', 'o3',             'o3',               2.00,   8.00,   NULL),
('openai', 'o3-mini',        'o3 Mini',          1.10,   4.40,   NULL),
('openai', 'o4-mini',        'o4 Mini',          1.10,   4.40,   NULL),
('openai', 'gpt-3.5-turbo',  'GPT-3.5 Turbo',   0.50,   1.50,   NULL);

-- ─── Anthropic ───────────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('anthropic', 'claude-sonnet-5',            'Claude Sonnet 5',       2.00,  10.00, 'Price through Aug 31 2026 · $3/$15 after'),
('anthropic', 'claude-sonnet-4-6',          'Claude Sonnet 4.6',     3.00,  15.00, NULL),
('anthropic', 'claude-sonnet-4-5',          'Claude Sonnet 4.5',     3.00,  15.00, NULL),
('anthropic', 'claude-haiku-4-5',           'Claude Haiku 4.5',      1.00,  5.00,  NULL),
('anthropic', 'claude-opus-4-5',            'Claude Opus 4.5',       5.00,  25.00, NULL),
('anthropic', 'claude-opus-4-6',            'Claude Opus 4.6',       5.00,  25.00, NULL),
('anthropic', 'claude-opus-4-7',            'Claude Opus 4.7',       5.00,  25.00, NULL),
('anthropic', 'claude-opus-4-8',            'Claude Opus 4.8',       5.00,  25.00, NULL),
('anthropic', 'claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet',     3.00,  15.00, NULL),
('anthropic', 'claude-3-5-haiku-20241022',  'Claude 3.5 Haiku',      0.80,  4.00,  NULL),
('anthropic', 'claude-3-opus-20240229',     'Claude 3 Opus',        15.00,  75.00, NULL);

-- ─── Google Gemini ───────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('gemini', 'gemini-3.5-flash',       'Gemini 3.5 Flash',        1.50, 9.00,  NULL),
('gemini', 'gemini-3.1-pro-preview', 'Gemini 3.1 Pro Preview',  2.00, 12.00, 'Short context · long context $4/$18'),
('gemini', 'gemini-3.1-flash-lite',  'Gemini 3.1 Flash Lite',   0.25, 1.50,  NULL),
('gemini', 'gemini-3-flash-preview', 'Gemini 3 Flash Preview',  0.50, 3.00,  NULL),
('gemini', 'gemini-2.5-pro',         'Gemini 2.5 Pro',          1.25, 10.00, 'Short context · long context $2.5/$15'),
('gemini', 'gemini-2.5-flash',       'Gemini 2.5 Flash',        0.30, 2.50,  NULL),
('gemini', 'gemini-2.5-flash-lite',  'Gemini 2.5 Flash Lite',   0.10, 0.40,  NULL),
('gemini', 'gemini-2.0-flash',       'Gemini 2.0 Flash',        0.10, 0.40,  NULL),
('gemini', 'gemini-1.5-pro',         'Gemini 1.5 Pro',          1.25, 5.00,  NULL);

-- ─── DeepSeek ────────────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('deepseek', 'deepseek-v4-pro',   'DeepSeek V4 Pro',   0.435, 0.87,  'Best value'),
('deepseek', 'deepseek-v4-flash', 'DeepSeek V4 Flash', 0.14,  0.28,  NULL),
('deepseek', 'deepseek-v4',       'DeepSeek V4',       0.27,  0.55,  'Base 1T model'),
('deepseek', 'deepseek-r1',       'DeepSeek R1',       0.55,  2.19,  'Reasoning model'),
('deepseek', 'deepseek-chat',     'DeepSeek Chat',     0.27,  1.10,  NULL),
('deepseek', 'deepseek-reasoner', 'DeepSeek Reasoner', 0.55,  2.19,  NULL);

-- ─── Mistral ─────────────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('mistral', 'mistral-medium-3.5', 'Mistral Medium 3.5', 1.50, 7.50, 'Flagship enterprise'),
('mistral', 'mistral-small-4',    'Mistral Small 4',    0.15, 0.60, 'Multimodal, multilingual'),
('mistral', 'mistral-large-3',    'Mistral Large 3',    0.50, 1.50, 'Flagship open-weight'),
('mistral', 'magistral-medium',   'Magistral Medium',   2.00, 5.00, 'Reasoning model'),
('mistral', 'magistral-small',    'Magistral Small',    0.50, 1.50, 'Lightweight reasoning'),
('mistral', 'devstral-2',         'Devstral 2',         0.40, 2.00, 'Coding agent'),
('mistral', 'devstral-small-2',   'Devstral Small 2',   0.10, 0.30, 'Lightweight coding'),
('mistral', 'codestral-latest',   'Codestral',          0.30, 0.90, 'Code completion'),
('mistral', 'ministral-3b',       'Ministral 3B',       0.10, 0.10, 'Edge deployment'),
('mistral', 'ministral-8b',       'Ministral 8B',       0.15, 0.15, 'Edge deployment'),
('mistral', 'ministral-14b',      'Ministral 14B',      0.20, 0.20, 'Edge deployment'),
('mistral', 'mixtral-8x7b',       'Mixtral 8x7B',       0.70, 0.70, 'Sparse MoE'),
('mistral', 'mixtral-8x22b',      'Mixtral 8x22B',      2.00, 6.00, 'Largest open MoE');

-- ─── Perplexity ──────────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('perplexity', 'sonar',               'Sonar',               1.00, 1.00,  '+ request fees apply'),
('perplexity', 'sonar-pro',           'Sonar Pro',           3.00, 15.00, '+ request fees apply'),
('perplexity', 'sonar-reasoning',     'Sonar Reasoning',     1.00, 5.00,  NULL),
('perplexity', 'sonar-reasoning-pro', 'Sonar Reasoning Pro', 2.00, 8.00,  '+ request fees apply'),
('perplexity', 'sonar-deep-research', 'Sonar Deep Research', 2.00, 8.00,  '+ citation/reasoning/search fees');

-- ─── xAI ─────────────────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('xai', 'grok-4.5',               'Grok 4.5',               2.00, 6.00,  'Short context · long context $4/$12'),
('xai', 'grok-4.3',               'Grok 4.3',               1.25, 2.50,  'Short context · long context $2.5/$5'),
('xai', 'grok-4.20-reasoning',    'Grok 4.20 Reasoning',    1.25, 2.50,  'Short context · long context $2.5/$5'),
('xai', 'grok-4.20-non-reasoning','Grok 4.20',              1.25, 2.50,  'Short context · long context $2.5/$5'),
('xai', 'grok-4',                 'Grok 4',                 3.00, 15.00, NULL),
('xai', 'grok-4-heavy',           'Grok 4 Heavy',           8.00, 40.00, NULL);

-- ─── Ollama (local) ──────────────────────────────────────────────────────────
INSERT INTO model_pricing (provider, model_id, display_name, price_per_m_input, price_per_m_output, notes) VALUES
('ollama', 'llama3.2',      'LLaMA 3.2 (local)',       0.00, 0.00, 'Free — runs locally via Ollama'),
('ollama', 'llama3.3',      'LLaMA 3.3 (local)',       0.00, 0.00, 'Free — runs locally via Ollama'),
('ollama', 'qwen2.5-coder', 'Qwen 2.5 Coder (local)',  0.00, 0.00, 'Free — runs locally via Ollama'),
('ollama', 'phi4',          'Phi-4 (local)',            0.00, 0.00, 'Free — runs locally via Ollama'),
('ollama', 'mistral',       'Mistral (local)',          0.00, 0.00, 'Free — runs locally via Ollama');
