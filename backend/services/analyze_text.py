"""Text deepfake / AI-generated text analysis.

Computes perplexity-style and burstiness-style heuristics and flags suspicious
sentences. Also feeds the multi-model ensemble + trust score.
"""
import math
import re
import time
from collections import Counter

from services.ensemble import (build_models, explain_short, reasons_from_features,
                               risk_label, trust_score)


def _tokenize(text):
    return re.findall(r"\b[\w']+\b", text.lower())


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 2]


def _perplexity_heuristic(tokens, n=3):
    """n-gram based perplexity proxy. Higher = more unusual token flow."""
    if len(tokens) < n:
        return 20.0
    grams = Counter(zip(*[tokens[i:] for i in range(n)]))
    freq = Counter(tokens)
    total = len(tokens)
    log_sum = 0.0
    count = 0
    for i in range(len(tokens) - n + 1):
        context = tuple(tokens[i:i + n - 1])
        next_tok = tokens[i + n - 1]
        # P(next | context) estimated with add-one smoothing over bigrams
        ctx_count = sum(1 for j in range(len(tokens) - n + 2)
                        if tuple(tokens[j:j + n - 1]) == context)
        p = (grams[tuple(tokens[i:i + n])] + 1.0) / (ctx_count + len(freq))
        log_sum += -math.log(max(p, 1e-9))
        count += 1
    ppl = math.exp(log_sum / count) if count else 20.0
    return min(ppl, 5000.0)


def _burstiness(tokens):
    """Sentence length variance proxy. Human text is bursty; AI text is uniform."""
    if len(tokens) < 5:
        return 0.0
    lengths = []
    current = 0
    for i, t in enumerate(tokens):
        current += 1
    # simpler: variance across sentence word-counts
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(tokens))
    counts = [len(w.split()) for w in sentences if len(w.split()) > 0]
    if len(counts) < 2:
        return 0.0
    mean = sum(counts) / len(counts)
    var = sum((c - mean) ** 2 for c in counts) / len(counts)
    return var / (mean + 1.0)


def _repetition_score(tokens):
    """Fraction of top-10 most common tokens; AI text repeats connectives."""
    if not tokens:
        return 0.0
    freq = Counter(tokens)
    common = sum(f for _, f in freq.most_common(10))
    return common / len(tokens)


def _sentence_anomaly_scores(text, ppl):
    """Per-sentence suspicion score (0..1) for highlighting."""
    out = []
    for s in _sentences(text):
        st = _tokenize(s)
        if not st:
            continue
        s_ppl = _perplexity_heuristic(st, 3)
        repetition = _repetition_score(st)
        # Short generic transitions and heavy repetition look machine-like.
        suspicion = 0.5 * min(1.0, s_ppl / ppl) + 0.35 * repetition + 0.15 * (len(st) < 8)
        out.append({
            "text": s[:500],
            "score": round(min(1.0, suspicion), 3),
            "perplexity": round(s_ppl, 1),
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def analyze_text(text, filename="text-input.txt"):
    start = time.time()
    tokens = _tokenize(text)
    ppl = _perplexity_heuristic(tokens)
    burst = _burstiness(tokens)
    rep = _repetition_score(tokens)
    avg_len = sum(len(s.split()) for s in _sentences(text)) / max(1, len(_sentences(text)))

    # --------------------------- heuristic --------------------------- #
    # AI text tends to be smooth (low perplexity), low burstiness and repetitive.
    ppl_score = max(0.0, min(1.0, 1.0 - (ppl / 400.0)))
    burst_score = max(0.0, min(1.0, 1.0 - (burst / 2.5)))
    rep_score = max(0.0, min(1.0, (rep - 0.25) / 0.4))

    fake_probability = (0.40 * ppl_score + 0.32 * burst_score + 0.28 * rep_score) * 100

    fake_probability = max(5.0, min(95.0, fake_probability))
    features = {
        "perplexity": round(ppl, 1),
        "burstiness": round(burst, 2),
        "repetition": round(rep, 3),
        "avg_sentence_words": round(avg_len, 1),
    }
    models, _final = build_models("text", fake_probability, filename, spread=4.5)
    result, risk0 = _interpret(fake_probability)
    risk = risk_label(fake_probability)
    reasons = reasons_from_features("text", features, fake_probability)
    trust = trust_score(fake_probability, {
        "perplexity": 1.0 - ppl_score, "burstiness": 1.0 - burst_score,
        "repetition": 1.0 - rep_score,
    })
    sections = _sentence_anomaly_scores(text, max(ppl, 1))

    explanation = explain_short("text", result, fake_probability)
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
            "word_count": len(tokens),
            "sentence_count": len(_sentences(text)),
            "avg_sentence_words": round(avg_len, 1),
            "character_count": len(text),
        },
        "features": features,
        "models": models,
        "reasons": reasons,
        "suspicious_sections": sections,
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
