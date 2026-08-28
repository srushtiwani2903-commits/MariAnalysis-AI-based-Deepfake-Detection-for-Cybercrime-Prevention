"""Text deepfake / AI-generated text analysis.

Computes perplexity-style and burstiness-style heuristics and flags suspicious
sentences. Also feeds the multi-model ensemble + trust score. All feature
values returned in the result are normalised 0..1 suspicion scores (higher =
more likely machine written), so the results page, PDF and XAI checklist
render them consistently.
"""
import math
import re
import time
from collections import Counter

from config import Config
from services.ensemble import (append_real_models, build_models, explain_short,
                               reasons_from_features, risk_label, trust_score)
from services.model_providers import blend_scores, gemini_score, local_score, score_reason

_COMMON_STOPWORDS = frozenset("""
the a an and or but of to in for on with as by at from be is are was were it its
this that these those they their them he she his her we our you your i my me not
no yes so if then than there here all any some more most which who whom what when
where how why have has had will would can could should may might do does did been
being about into over under after before while during also just very too much many
each other another between among against through across beyond per via s t d
""".split())

_GPT_SIGNALS = (
    "it is important to", "it is worth noting", "worth noting that",
    "in conclusion", "to conclude", "in summary", "in essence",
    "furthermore", "moreover", "additionally", "consequently", "therefore,",
    "in today's", "in the modern era", "in the modern world", "in the digital age",
    "in recent years", "in today's fast-paced world",
    "plays a crucial role", "plays a vital role", "plays a significant role",
    "a wide range of", "when it comes to", "in this essay", "this essay will",
    "it is essential", "it is crucial", "it is paramount", "it is vital",
    "to sum up", "as a result", "first and foremost", "it is clear that",
    "it is evident that", "overall,", "lastly,", "finally,", "delve into",
    "deep dive", "in our daily lives", "in our everyday lives",
    "both the opportunities", "the challenges they", "continue to evolve",
    "in the years ahead", "not only", "but also", "game changer",
    "game-changer", "cutting-edge", "stay ahead", "unlock the",
    "ever-changing", "a plethora of", "in the realm", "in the world of",
    "navigat", "leverag", "robust", "seamless", "when it comes",
)

_GPT_STRICT_PAIRS = (("not only", "but also"),)


def _clamp01(x):
    return max(0.0, min(1.0, x))


def _tokenize(text):
    return re.findall(r"\b[\w']+\b", text.lower())


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 2]


def _perplexity_raw(tokens, n=3):
    """n-gram based perplexity proxy. Lower = smoother/more repetitive."""
    if len(tokens) < n:
        return 0.0
    rows = list(zip(*[tokens[i:] for i in range(n)]))
    if not rows:
        return 0.0
    grams = Counter(rows)
    contexts = Counter(r[:-1] for r in rows)
    freq = Counter(tokens)
    log_sum = 0.0
    for tri in rows:
        p = (grams[tri] + 1.0) / (contexts[tri[:-1]] + len(freq))
        log_sum += -math.log(max(p, 1e-9))
    return min(math.exp(log_sum / len(rows)), 5000.0)


def _perplexity_suspicion(ppl):
    """Raw within-text perplexity is dominated by vocabulary size, so only
    clearly smooth / repetitive text scores high; ordinary prose is neutral."""
    if ppl <= 0:
        return 1.0
    return _clamp01((40.0 - ppl) / 28.0)


def _burstiness(text):
    """Variance of sentence word-counts (on real sentences, not tokens)."""
    counts = [len(_tokenize(s)) for s in _sentences(text)]
    if len(counts) < 3:
        return 0.0, len(counts)
    mean = sum(counts) / len(counts)
    var = sum((c - mean) ** 2 for c in counts) / len(counts)
    return var / (mean + 1.0), len(counts)


def _burstiness_suspicion(burst, n_sent):
    score = _clamp01(1.0 - burst / 5.0)
    score *= min(1.0, n_sent / 5.0)
    return score


def _content_repetition(tokens):
    """Content-word repetition after removing common function words."""
    if len(tokens) < 8:
        return 0.0
    content = [t for t in tokens if t not in _COMMON_STOPWORDS]
    if len(content) < 4:
        return 0.0
    repeats = sum(c for _, c in Counter(content).items() if c >= 2)
    return _clamp01(repeats / len(content))


def _ngram_repeat_rate(tokens, n=3):
    """Fraction of positions that continue an already-seen n-gram."""
    if len(tokens) < 2 * n:
        return 0.0
    seen = set()
    repeats = 0
    total = 0
    for i in range(len(tokens) - n + 1):
        gram = tuple(tokens[i:i + n])
        if gram in seen:
            repeats += 1
        else:
            seen.add(gram)
        total += 1
    return repeats / total if total else 0.0


def _gpt_suspicion(text):
    low = " " + text.lower() + " "
    hits = sum(1 for phrase in _GPT_SIGNALS if phrase in low)
    for pair in _GPT_STRICT_PAIRS:
        if all(p in low for p in pair):
            hits += 1
    return _clamp01(hits / 2.5)


def _sentence_anomaly_scores(text, ppl_susp):
    """Per-sentence suspicion score (0..1) for highlighting."""
    out = []
    for s in _sentences(text):
        st = _tokenize(s)
        if not st:
            continue
        s_susp = _perplexity_suspicion(_perplexity_raw(st, 3))
        repetition = _content_repetition(st)
        suspicion = 0.5 * s_susp + 0.35 * repetition + 0.15 * (len(st) < 8)
        out.append({
            "text": s[:500],
            "score": round(_clamp01(suspicion), 3),
            "perplexity": round(_perplexity_raw(st, 3), 1),
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def analyze_text(text, filename="text-input.txt"):
    start = time.time()
    text = text or ""
    tokens = _tokenize(text)
    num_tokens = len(tokens)

    ppl_raw = _perplexity_raw(tokens)
    ppl_susp = _perplexity_suspicion(ppl_raw)
    burst_raw, n_sent = _burstiness(text)
    burst_susp = _burstiness_suspicion(burst_raw, n_sent)
    rep_susp = _content_repetition(tokens)
    repeat_susp = _ngram_repeat_rate(tokens)
    gpt_susp = _gpt_suspicion(text)
    avg_len = sum(len(_tokenize(s)) for s in _sentences(text)) / max(1, len(_sentences(text)))

    fake_probability = 100.0 * (
        0.20 * ppl_susp
        + 0.24 * burst_susp
        + 0.16 * rep_susp
        + 0.12 * repeat_susp
        + 0.28 * gpt_susp
    )

    template_bias = _clamp01((12.0 - avg_len) / 8.0) * burst_susp * max(ppl_susp, rep_susp)
    fake_probability += 18.0 * template_bias

    if num_tokens < 8:
        fake_probability = 50.0
    elif num_tokens < 24:
        evidence = (num_tokens - 8) / 16.0
        fake_probability = 50.0 + (fake_probability - 50.0) * evidence

    fake_probability = max(0.0, min(100.0, fake_probability))

    gemini = local = None
    if num_tokens >= 25:
        gemini = gemini_score("text", text=text)
        local = local_score("text", text=text)
    blended = blend_scores(fake_probability, gemini, local)
    fake_probability = max(0.0, min(100.0, blended))
    provider_note = score_reason(gemini, "text") + score_reason(local, "text")

    features = {
        "perplexity": round(ppl_susp, 3),
        "burstiness": round(burst_susp, 3),
        "repetition": round(rep_susp, 3),
        "repetition_rate": round(repeat_susp, 3),
        "ai_style_patterns": round(gpt_susp, 3),
        "sentence_diversity": round(1.0 - burst_susp, 3),
        "avg_sentence_words": round(avg_len, 1),
    }
    models, _final = build_models("text", fake_probability, filename, spread=4.5)
    models = append_real_models(models, [
        (gemini, f"Gemini ({Config.GEMINI_MODEL})"),
        (local, "Local RoBERTa (openai-detector)"),
    ])
    result, risk0 = _interpret(fake_probability)
    risk = risk_label(fake_probability)
    reasons = reasons_from_features("text", features, fake_probability)
    trust = trust_score(fake_probability, {
        "perplexity": 1.0 - ppl_susp, "burstiness": 1.0 - burst_susp,
        "repetition": 1.0 - rep_susp,
    })
    sections = _sentence_anomaly_scores(text, ppl_susp)

    explanation = explain_short("text", result, fake_probability) + provider_note
    explanation += (
        f" Perplexity {ppl_raw:.1f}, sentence-length burstiness {burst_raw:.2f}, "
        f"average sentence length {avg_len:.1f} words."
    )
    recommendations = _recommendations(result)
    elapsed = int((time.time() - start) * 1000)

    return {
        "scan_type": "text",
        "filename": filename,
        "result": result,
        "confidence": 100.0 - abs(fake_probability - (100 if result == "fake" else 0)),
        "fake_probability": round(fake_probability, 1),
        "trust_score": trust,
        "risk_level": risk,
        "explanation": explanation,
        "recommendations": recommendations,
        "processing_time_ms": elapsed,
        "metadata": {
            "word_count": num_tokens,
            "sentence_count": len(_sentences(text)),
            "avg_sentence_words": round(avg_len, 1),
            "character_count": len(text),
        },
        "features": features,
        "models": models,
        "reasons": reasons,
        "suspicious_sections": sections,
        "ai_providers": {"gemini": gemini, "local": local},
        "model": "heuristic-nlp-v1",
    }


def _interpret(prob):
    if prob >= 62:
        return "fake", "high"
    if prob >= 42:
        return "inconclusive", "medium"
    return "authentic", "low"


def _explain_text(result, prob, ppl, burst, rep, avg_len):
    head = ("This text exhibits patterns typical of AI-generated writing. " if result == "fake"
            else "This text displays human-like variability in its writing. ")
    detail = (
        f"Perplexity {ppl:.1f}, burstiness {burst:.2f}, repetition {rep:.3f}, "
        f"average sentence length {avg_len:.1f} words. Overall AI probability {prob:.1f}%."
    )
    return head + detail


def _recommendations(result):
    base = ["Use an AI-text detector (GPTZero, Turnitin) to cross-check",
            "Ask for authorship proof / timestamps of drafting",
            "Check citations and factual claims for fabrication"]
    if result == "fake":
        return "\n".join(["Do not republish or rely on the text as factual.",
                          "Verify claims with primary sources.",
                          "Flag the account/content for review."] + base[:2])
    return "\n".join(base)