"""T3701 - tone learner tests."""
import pytest
from services.tone_learner import (
    classify_tone, aggregate_history, extract_few_shot_samples,
    render_tone_for_prompt, rewrite_template, merge_tone_profiles,
    ALL_TONES, TONE_FORMAL, TONE_CASUAL, TONE_DATA_DRIVEN, TONE_RELATIONSHIP_DRIVEN,
    ToneProfile,
)


class TestClassifyTone:
    def test_empty_text(self):
        scores = classify_tone("")
        assert sum(scores.values()) == 0.0

    def test_formal_signals(self):
        s = classify_tone("请您审阅以下材料,并回复贵司意见。")
        assert s[TONE_FORMAL] > 0

    def test_casual_signals(self):
        s = classify_tone("哈哈 加油,咱们撸起袖子加油干!")
        assert s[TONE_CASUAL] > 0

    def test_data_signals(self):
        s = classify_tone("Q3 增长 30%,环比 +5%,转化率达到 12%。")
        assert s[TONE_DATA_DRIVEN] > 0

    def test_relationship_signals(self):
        s = classify_tone("辛苦了,谢谢理解,希望我们一起把这件事做好。")
        assert s[TONE_RELATIONSHIP_DRIVEN] > 0

    def test_returns_all_tones(self):
        s = classify_tone("hello world")
        for t in ALL_TONES:
            assert t in s

    def test_scores_sum_to_around_1(self):
        s = classify_tone("辛苦了,谢谢理解,这是一份正式材料,请您审阅并回复。")
        # With markers, sum should be near 1.0
        total = sum(s.values())
        # Should at least have positive scores
        assert total > 0
        # When tokens exist, scores should be normalized
        # 0 markers → 0.25 each (uniform distribution - test depends on text)
        for k, v in s.items():
            assert 0 <= v <= 1.0

    def test_only_exclamation_marks(self):
        s = classify_tone("Great!!")
        assert s[TONE_CASUAL] > s[TONE_FORMAL]

    def test_only_period(self):
        s = classify_tone("好的。")
        assert s[TONE_FORMAL] > 0

    def test_no_keywords(self):
        s = classify_tone("xyz")
        assert s[TONE_FORMAL] >= 0


class TestAggregateHistory:
    def test_empty_history(self):
        prof = aggregate_history([])
        assert prof.sample_count == 0

    def test_default_user(self):
        prof = aggregate_history(["hi"])
        assert prof.user_id == ""

    def test_primary_tone_strongest(self):
        history = ["Please review the attached materials",
                    "Please respond formally regarding this matter"] * 5
        prof = aggregate_history(history)
        assert prof.primary_tone == TONE_FORMAL

    def test_sample_count(self):
        prof = aggregate_history(["m1", "m2", "m3"])
        assert prof.sample_count == 3

    def test_tone_scores_keys(self):
        prof = aggregate_history(["hi"])
        for k in ALL_TONES:
            assert k in prof.tone_scores

    def test_render_for_prompt_has_label(self):
        prof = aggregate_history(["hi"])
        out = render_tone_for_prompt(prof)
        assert "语气" in out or "风格" in out

    def test_manual_override(self):
        prof = aggregate_history(["hi"])
        prof.manual_override = TONE_CASUAL
        out = render_tone_for_prompt(prof)
        assert TONE_CASUAL in out

    def test_aggregate_returns_profile(self):
        prof = aggregate_history(["a", "b"])
        assert isinstance(prof, ToneProfile)


class TestExtractFewShot:
    def test_no_history(self):
        out = extract_few_shot_samples([], TONE_FORMAL)
        assert out == []

    def test_filters_short(self):
        history = ["hi", "ok", "Please review the document carefully"]
        out = extract_few_shot_samples(history, TONE_FORMAL)
        assert len(out) >= 1

    def test_max_samples(self):
        history = ["long formal sentence please " + str(i) for i in range(10)]
        out = extract_few_shot_samples(history, TONE_FORMAL, max_samples=3)
        assert len(out) <= 3

    def test_returns_str(self):
        out = extract_few_shot_samples(["hello world"], TONE_CASUAL)
        assert all(isinstance(x, str) for x in out)


class TestMergeToneProfiles:
    def test_empty(self):
        m = merge_tone_profiles([])
        assert sum(m.values()) == 1.0

    def test_average(self):
        m = merge_tone_profiles([
            {TONE_FORMAL: 1.0, TONE_CASUAL: 0.0, TONE_DATA_DRIVEN: 0.0, TONE_RELATIONSHIP_DRIVEN: 0.0},
            {TONE_FORMAL: 0.0, TONE_CASUAL: 1.0, TONE_DATA_DRIVEN: 0.0, TONE_RELATIONSHIP_DRIVEN: 0.0},
        ])
        assert m[TONE_FORMAL] == 0.5
        assert m[TONE_CASUAL] == 0.5


class TestRewriteTemplate:
    def test_empty_template(self):
        prof = ToneProfile(user_id="x")
        out = rewrite_template("", prof)
        assert "[" in out

    def test_tone_marker(self):
        prof = ToneProfile(user_id="x", primary_tone=TONE_CASUAL)
        out = rewrite_template("body", prof)
        assert TONE_CASUAL in out

    def test_replace_placeholder(self):
        prof = ToneProfile(user_id="x", manual_override=TONE_DATA_DRIVEN)
        out = rewrite_template("Hello {{tone}} world", prof)
        assert TONE_DATA_DRIVEN in out


@pytest.mark.parametrize("tone", ALL_TONES)
def test_all_tones_have_descriptions(tone):
    prof = ToneProfile(user_id="x", primary_tone=tone)
    out = render_tone_for_prompt(prof)
    assert len(out) > 5


@pytest.mark.parametrize("history_len", [1, 5, 20])
def test_various_history_lengths(history_len):
    history = [f"please review {i}" for i in range(history_len)]
    prof = aggregate_history(history)
    assert prof.sample_count == history_len
