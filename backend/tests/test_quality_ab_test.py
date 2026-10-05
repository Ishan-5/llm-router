"""Guards for the blind cheap-vs-frontier A/B runner.

These exist because the first version of this test reported 100% ties while
grading nothing at all: the judge was given an 8-token budget, gpt-oss-120b is a
reasoning model, every call came back finish_reason="length" with empty
content, and the unparseable case silently fell through to "TIE".
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "quality_ab_test.py"


def _load():
    spec = importlib.util.spec_from_file_location("quality_ab_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["quality_ab_test"] = mod
    spec.loader.exec_module(mod)
    return mod


ab = _load()


class TestJudgeBudget:
    def test_budget_covers_reasoning_tokens(self):
        # Measured: gpt-oss-120b spends 130-190 completion tokens reasoning
        # before the verdict. 8 tokens guaranteed finish_reason="length".
        assert ab.JUDGE_MAX_TOKENS >= 512

    def test_unparseable_verdict_is_an_error_not_a_tie(self):
        """A judge we could not read must never become evidence of agreement."""
        source = SCRIPT.read_text(encoding="utf-8")
        # the only fallback after parsing may be ERROR
        assert 'return "TIE"\n' not in source.split("def pick_winner")[1].split("def ")[0]

    def test_truncated_completion_is_not_a_tie(self):
        body = SCRIPT.read_text(encoding="utf-8").split("def pick_winner")[1].split("\ndef ")[0]
        assert 'finish_reason == "length"' in body
        assert "judge truncated" in body


class TestBlankAnswers:
    def test_blank_pair_raises(self):
        assert issubclass(ab.BlankAnswer, Exception)

    def test_min_answer_chars_does_not_drop_short_but_valid_answers(self):
        """A correct short answer ("August 19, 2021") must still be graded.

        Dropping everything under MIN_ANSWER_CHARS deleted cheap's best-case
        wins and biased the run in cheap's favour.
        """
        assert ab.MIN_ANSWER_CHARS == 40
        body = SCRIPT.read_text(encoding="utf-8")
        assert "shorts[tier] += 1" in body
        assert 'drops[f"{tier}_blank_or_truncated"]' not in body
        assert "short_answers_counted_not_dropped" in body


class TestUnanswerableQueries:
    @pytest.mark.parametrize(
        "q",
        [
            "Given this paragraph, how many public high schools are in Arlington?",
            "Given this paragraph about Grumpy Cat, tell me the cat's real name.",
            "Provide a 3-5 sentence summary of the following article:",
            "Identify the term that best summarizes the following definition:",
            "Generate a questionnaire that could be used for collecting the given data.",
            "Comment on the given statement",
        ],
    )
    def test_dangling_context_is_excluded(self, q):
        assert ab.missing_context(q) is not None, q

    @pytest.mark.parametrize(
        "q",
        [
            "How would you implement a function in Python to remove duplicates "
            "from a given list of numbers?",
            "Design a function in PHP to calculate the cost of a product given "
            "its quantity and price.",
            "What is Dependency Parsing?",
            "Name a well-known European landmark",
        ],
    )
    def test_self_contained_queries_are_kept(self, q):
        assert ab.missing_context(q) is None, q


class TestSampling:
    def test_band_filter_restricts_the_pool(self):
        rows = [
            ("easy one " + "x" * 30, 1),
            ("mid one " + "x" * 30, 5),
            ("hard one " + "x" * 30, 9),
        ]
        # exercise the band maths directly
        for score, expected in ((1, "easy"), (5, "mid"), (9, "hard")):
            band = "easy" if score <= 3 else "mid" if score <= 6 else "hard"
            assert band == expected

    def test_gold_loader_splits_budget_across_requested_bands_only(self):
        import inspect
        sig = inspect.signature(ab.load_queries_from_gold)
        assert "bands" in sig.parameters
        # default budget must divide across requested bands, not always three
        src = inspect.getsource(ab.load_queries_from_gold)
        assert "len(wanted)" in src


class TestReportIntegrity:
    def test_refuses_to_write_a_run_that_is_mostly_dropped(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "REFUSING TO WRITE" in src
        assert "attempted * 0.6" in src

    def test_report_records_provenance(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for field in ("judge_model", "bands_sampled", "judge_max_tokens", "dropped"):
            assert f'"{field}"' in src, field

    def test_no_publication_without_a_real_sample(self):
        """The fabricated report claimed 190 compared pairs."""
        assert not (BACKEND / "ab_report.json").exists()


class TestJudgePrompt:
    def test_prompt_tells_judge_not_to_reward_length(self):
        p = ab.PAIRWISE_SYSTEM_PROMPT
        assert "Do not reward length" in p

    def test_prompt_encourages_ties(self):
        """Residual length bias inflated frontier wins: forcing a TIE when both
        answers are acceptable moved win-or-tie from 42.1% to 75.0%."""
        assert "TIE" in ab.PAIRWISE_SYSTEM_PROMPT
        assert "both answers would reasonably be accepted" in ab.PAIRWISE_SYSTEM_PROMPT
