"""
ai_engine.py
============
The Hybrid AI Pipeline — the analytical core of the Intelligent Feedback
Analysis System.

A single production-grade wrapper class (`AIEngine`) implements the frozen
four-tier sequential analysis loop:

    Tier A  — spaCy tokenization & cleaning (strip punctuation + stop words)
    Tier B  — DistilBERT sentiment classification (Hugging Face Transformers)
    Tier C  — KeyBERT semantic keyword / theme extraction
    Tier D  — Gemini 1.5 Flash qualitative summarization (async)

Note on how the tiers connect: Tier A produces the normalized string that is
stored for audit, but Tiers B and C read the ORIGINAL sentence. Both are
transformer models, and stop-word removal deletes the negations they depend on
("without much difficulty" -> "difficulty"). See `_analyze_sync`.

Design principles honoured here:
  * Heavy models load ONCE (lazy, at startup) and are reused per-request.
  * The blocking ML calls (Tiers A–C) are executed inside a thread-pool via
    `run_in_executor` so they never stall the FastAPI event loop.
  * No secret keys or endpoints are hardcoded — everything comes from config.
  * Every tier is wrapped in defensive exception handling so one failing
    stage degrades gracefully instead of crashing the request.

The output dictionaries map EXACTLY onto the embedded MongoDB schema:
    sentiment_analysis = {"label": str, "confidence_score": float}
    keywords_extracted = [{"keyword": str, "relevance_score": float}, ...]
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from functools import partial
from typing import Any, Dict, List, Tuple

from ..config import Settings, get_settings
from ..models import (
    AnalysisResult,
    KeywordExtracted,
    SentimentAnalysis,
    SentimentLabel,
)

logger = logging.getLogger("ifas.ai_engine")

# Distinctive Nigerian Pidgin / slang markers. Their presence means the text is
# outside DistilBERT's (English movie-review) training domain, so Tier B is
# unreliable and the sample should be escalated to Gemini regardless of the
# confidence DistilBERT reports. Kept deliberately distinctive to minimise false
# hits on standard English (a false hit only costs one extra Gemini call).
_PIDGIN_MARKERS = frozenset({
    "omo", "wahala", "abeg", "sha", "wetin", "dey", "sef", "jare", "jor", "joor",
    "biko", "oya", "comot", "chop", "gan", "walahi", "wallahi", "kasala", "gbese",
    "yawa", "japa", "mumu", "abi", "shey", "wey", "pikin", "oga", "gbam", "sabi",
    "shakara", "vex", "e be like", "no wahala", "e sweet", "e pain", "e choke",
    "na so", "no be", "dey vex", "as e dey hot", "waec", "jamb",
})
_MARKER_RE = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in sorted(_PIDGIN_MARKERS, key=len, reverse=True)) + r")\b"
)
_MIXED_SENTIMENT_RE = re.compile(
    r"\b(?:but|however|although|though|yet|even so|even though|on the other hand|"
    r"that said|apart from that|except that|whereas|while|"
    r"not what (?:i|we) expected|could be better|nothing special|"
    r"not bad|not great)\b",
    re.IGNORECASE,
)

# Points at which a comment plausibly switches opinion. Used to split feedback
# into clauses that can each be scored on their own, so that praise and
# criticism sitting in one submission can actually be detected rather than
# averaged into a single confident-but-wrong label.
_CLAUSE_SPLIT_RE = re.compile(
    r"(?:[.!?;]+\s+|\s*\n+\s*|"
    r"\s*\b(?:but|however|although|though|yet|even so|even though|"
    r"on the other hand|that said|apart from that|except that|whereas)\b\s*)",
    re.IGNORECASE,
)

# A clause must be at least this long to be scored. Fragments shorter than this
# ("yes", "ok", "the wifi") carry no reliable signal and would otherwise let
# noise flip a submission to NEUTRAL.
_MIN_CLAUSE_CHARS = 12


class AIEngine:
    """
    Stateful wrapper around the hybrid pipeline.

    Instantiate once (see `get_ai_engine`) and call:
        result = await engine.analyze(feedback_text)
        summary = await engine.summarize_negative_cluster(department, comments)
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

        # Lazy-loaded heavy resources (populated by `warm_up`).
        self._nlp = None                 # spaCy Language pipeline (Tier A)
        self._sentiment_pipeline = None  # HF Transformers pipeline (Tier B)
        self._keybert = None             # KeyBERT model (Tier C)
        self._gemini_model = None        # Gemini client handle (Tier D)
        self._ready = False

    # ======================================================================
    # Model loading / warm-up
    # ======================================================================
    def warm_up(self) -> None:
        self._load_spacy()
        self._load_sentiment_pipeline()
        self._load_keybert()
        self._configure_gemini()
        self._ready = True
        logger.info("AIEngine warm-up complete — all tiers ready.")

    def _load_spacy(self) -> None:
        try:
            import spacy

            self._nlp = spacy.load(
                self.settings.spacy_model,
                disable=["parser", "ner"],
            )
            logger.info("spaCy model '%s' loaded (Tier A).", self.settings.spacy_model)
        except OSError as exc:
            logger.error(
                "spaCy model '%s' not found. Run: "
                "python -m spacy download %s",
                self.settings.spacy_model,
                self.settings.spacy_model,
            )
            raise RuntimeError("spaCy model unavailable") from exc

    def _load_sentiment_pipeline(self) -> None:
        """Tier B: load the DistilBERT sentiment-analysis pipeline."""
        try:
            from transformers import pipeline

            self._sentiment_pipeline = pipeline(
                task="sentiment-analysis",
                model=self.settings.sentiment_model,
                tokenizer=self.settings.sentiment_model,
                truncation=True,
                max_length=512,
            )
            logger.info(
                "DistilBERT pipeline '%s' loaded (Tier B).",
                self.settings.sentiment_model,
            )
        except Exception as exc:  # noqa: BLE001 — surface any HF/torch failure
            logger.error("Failed to load sentiment pipeline: %s", exc)
            raise RuntimeError("DistilBERT pipeline unavailable") from exc

    def _load_keybert(self) -> None:
        """Tier C: load the KeyBERT extractor (shares a sentence embedder)."""
        try:
            from keybert import KeyBERT

            self._keybert = KeyBERT(model="all-MiniLM-L6-v2")
            logger.info("KeyBERT model loaded (Tier C).")
        except Exception as exc:  # noqa: BLE001
            logger.warning("KeyBERT unavailable — keyword extraction will stub out: %s", exc)
            self._keybert = None

    def _configure_gemini(self) -> None:
        """Tier D: configure the Gemini client from the environment key."""
        api_key = self.settings.gemini_api_key
        if not api_key:
            logger.warning(
                "GEMINI_API_KEY not set — Tier D summarization will be disabled "
                "until a key is provided in the environment."
            )
            self._gemini_model = None
            return
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            self._gemini_model = genai.GenerativeModel(self.settings.gemini_model)
            logger.info("Gemini model '%s' configured (Tier D).", self.settings.gemini_model)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini configuration failed — Tier D disabled: %s", exc)
            self._gemini_model = None

    # ======================================================================
    # Tier A — Cleaning & normalization (spaCy)
    # ======================================================================
    def _clean_text(self, raw_text: str) -> str:
        if not raw_text or not raw_text.strip():
            return ""

        # Lightweight regex pre-pass (matches Chapter 3.11.1 preprocessing).
        text = raw_text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)   # strip special characters
        text = re.sub(r"\s+", " ", text).strip()   # collapse whitespace

        if self._nlp is None:
            return text  # graceful fallback if spaCy failed to load

        doc = self._nlp(text)
        tokens = [
            token.lemma_
            for token in doc
            if not token.is_stop and not token.is_punct and not token.is_space
        ]
        return " ".join(tokens).strip()

    @staticmethod
    def _model_input(raw_text: str) -> str:
        """Prepare text for the transformer tiers (B and C).

        Deliberately minimal: collapse whitespace and nothing else. Punctuation,
        stop words, negations and casing all carry signal for a transformer and
        must survive. Aggressive cleaning belongs to bag-of-words models, where
        word order is discarded anyway — not here.
        """
        return re.sub(r"\s+", " ", raw_text or "").strip()

    # ======================================================================
    # Tier B — Sentiment classification (DistilBERT)
    # ======================================================================
    def _classify_sentiment(self, text: str) -> SentimentAnalysis:
        if self._sentiment_pipeline is None:
            raise RuntimeError("Sentiment pipeline not initialized.")

        if not text:
            return SentimentAnalysis(label=SentimentLabel.NEUTRAL, confidence_score=0.0)

        prediction: Dict[str, Any] = self._sentiment_pipeline(text)[0]
        raw_label = str(prediction.get("label", "")).upper()
        confidence = round(float(prediction.get("score", 0.0)), 4)

        if confidence < self.settings.neutral_threshold:
            label = SentimentLabel.NEUTRAL
        elif raw_label == "POSITIVE":
            label = SentimentLabel.POSITIVE
        elif raw_label == "NEGATIVE":
            label = SentimentLabel.NEGATIVE
        else:
            label = SentimentLabel.NEUTRAL

        return SentimentAnalysis(label=label, confidence_score=confidence)

    # ======================================================================
    # Tier C — Keyword / theme extraction (KeyBERT)
    # ======================================================================
    @staticmethod
    def _keyword_candidates(text: str) -> List[str]:
        """Build keyphrase candidates that never span a punctuation boundary.

        Left to itself, KeyBERT deletes stop words and then forms n-grams over
        whatever survives, so two words that were never adjacent get welded into
        a phrase the student did not write. "…without much difficulty, and the
        speed…" became "difficulty speed", and "…academic resources without
        unnecessary interruptions" became "resources unnecessary" — both were
        then displayed to staff as themes of the comment, and both reversed its
        meaning.

        So candidates are built here instead, under two rules: an n-gram may not
        cross a punctuation boundary, and it must be contiguous in the original
        sentence. Stop words are kept in place while the n-grams are cut, then
        any phrase merely starting or ending on one is dropped — which yields
        "academic resources" and "unnecessary interruptions" as separate
        phrases, never a splice of the two.
        """
        try:
            from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS as STOP
        except Exception:  # noqa: BLE001 — KeyBERT is optional, so is this
            return []

        candidates: List[str] = []
        seen = set()
        for segment in re.split(r"[.,;:!?\n()\[\]\"]+", text):
            words = re.findall(r"[a-z0-9]+", segment.lower())
            if not words:
                continue
            for size in (1, 2):
                for i in range(len(words) - size + 1):
                    gram = words[i:i + size]
                    # A phrase hinging on a stop word at either end is not a
                    # theme ("the speed", "speed and") — the stop word only
                    # earns its place between two content words.
                    if gram[0] in STOP or gram[-1] in STOP:
                        continue
                    phrase = " ".join(gram)
                    if phrase not in seen:
                        seen.add(phrase)
                        candidates.append(phrase)
        return candidates

    def _extract_keywords(self, text: str, top_n: int = 5) -> List[KeywordExtracted]:

        if not text:
            return []

        if self._keybert is not None:
            try:
                raw_keywords = self._keybert.extract_keywords(
                    text,
                    candidates=self._keyword_candidates(text) or None,
                    keyphrase_ngram_range=(1, 2),
                    stop_words="english",
                    use_mmr=True,
                    diversity=0.6,
                    top_n=top_n,
                )
                return [
                    KeywordExtracted(
                        keyword=str(phrase),
                        relevance_score=round(float(score), 4),
                    )
                    for phrase, score in raw_keywords
                ]
            except Exception as exc:  # noqa: BLE001 — degrade to stub, never crash
                logger.warning("KeyBERT extraction failed, falling back to stub: %s", exc)

        
        candidate_tokens = [tok for tok in text.split() if len(tok) > 3]
        seen: List[str] = []
        for tok in candidate_tokens:
            if tok not in seen:
                seen.append(tok)
            if len(seen) >= top_n:
                break
        
        return [
            KeywordExtracted(
                keyword=token,
                relevance_score=round(max(0.10, 0.90 - (idx * 0.15)), 4),
            )
            for idx, token in enumerate(seen)
        ]

   
    async def analyze(self, raw_text: str) -> AnalysisResult:
        """
        Execute the synchronous ML tiers (A, B, C) inside a worker thread so
        the FastAPI event loop is never blocked, and return a structured
        `AnalysisResult` ready to embed in the feedback document.
        """
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, partial(self._analyze_sync, raw_text))
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI analysis failed for submission.")
            raise RuntimeError("AI analysis pipeline error") from exc

        # Tier B escalation: DistilBERT is confident even when wrong on sarcasm and
        # Nigerian Pidgin/slang (out of its English movie-review domain). For those
        # cases, take a second opinion from Gemini and let it override the label.
        if self._should_escalate(result.sentiment_analysis, raw_text):
            try:
                label, confidence = await self._classify_sentiment_gemini(raw_text)
                logger.info(
                    "Tier B escalated to Gemini: %s (%.2f) -> %s (%.2f)",
                    result.sentiment_analysis.label.value,
                    result.sentiment_analysis.confidence_score,
                    label.value, confidence,
                )
                result.sentiment_analysis = SentimentAnalysis(
                    label=label, confidence_score=confidence, source="gemini"
                )
            except Exception as exc:  # noqa: BLE001 — never fail a submission over the fallback
                logger.warning(
                    "Gemini sentiment fallback failed; keeping DistilBERT label: %s", exc
                )

        # Final rule: a comment that praises one thing and criticises another is
        # NEUTRAL, and stays NEUTRAL. This is applied last, after Gemini, so the
        # outcome does not depend on the network — an unreachable Gemini would
        # otherwise leave mixed feedback labelled POSITIVE or NEGATIVE by
        # DistilBERT, which has no neutral class and must pick a side.
        if result.sentiment_analysis.label is not SentimentLabel.NEUTRAL:
            mixed = await asyncio.get_running_loop().run_in_executor(
                None, partial(self._is_mixed_opinion, raw_text)
            )
            if mixed:
                logger.info(
                    "Mixed opinion detected; %s -> NEUTRAL.",
                    result.sentiment_analysis.label.value,
                )
                result.sentiment_analysis = SentimentAnalysis(
                    label=SentimentLabel.NEUTRAL,
                    # Keep the model's own certainty rather than inventing one;
                    # the label is a rule, the number still describes the text.
                    confidence_score=result.sentiment_analysis.confidence_score,
                    source=result.sentiment_analysis.source,
                )
        return result

    # ------------------------------------------------------------------
    # Tier B escalation helpers
    # ------------------------------------------------------------------
    def _should_escalate(self, sentiment: SentimentAnalysis, raw_text: str) -> bool:
        """Decide whether a Tier-B result warrants a Gemini second opinion."""
        if self._gemini_model is None or not self.settings.gemini_sentiment_fallback:
            return False
        if not raw_text or not raw_text.strip():
            return False
        # (1) DistilBERT is genuinely unsure.
        if sentiment.confidence_score < self.settings.sentiment_escalate_threshold:
            return True
        # (2) Every POSITIVE prediction is double-checked. DistilBERT's confidence
        #     is miscalibrated (near 1.0 even when wrong), and sarcasm's main danger
        #     is angry feedback being scored POSITIVE — so verifying positives with
        #     Gemini catches sarcasm that carries no explicit slang marker.
        if sentiment.label == SentimentLabel.POSITIVE:
            return True
        # DistilBERT has no neutral class and tends to force mixed praise and
        # criticism into NEGATIVE. Ask Gemini to resolve explicit contrasts.
        if self._has_mixed_sentiment(raw_text):
            return True
        # (3) Text carries Nigerian Pidgin / slang markers -> out of Tier B's domain
        #     even though DistilBERT may report high confidence.
        return bool(_MARKER_RE.search(raw_text.lower()))

    @staticmethod
    def _has_mixed_sentiment(raw_text: str) -> bool:
        return bool(_MIXED_SENTIMENT_RE.search(raw_text))

    def _clause_sentiments(self, raw_text: str) -> List[SentimentLabel]:
        """Score each clause of a comment independently with DistilBERT."""
        if self._sentiment_pipeline is None or not raw_text.strip():
            return []

        clauses = [
            c.strip()
            for c in _CLAUSE_SPLIT_RE.split(raw_text)
            if c and len(c.strip()) >= _MIN_CLAUSE_CHARS
        ]
        if len(clauses) < 2:
            return []

        labels: List[SentimentLabel] = []
        # Cap the work: a very long comment should not turn one submission into
        # dozens of model calls.
        for clause in clauses[:8]:
            try:
                pred = self._sentiment_pipeline(clause)[0]
            except Exception as exc:  # noqa: BLE001 — never fail a submission here
                logger.warning("Clause sentiment failed, skipping clause: %s", exc)
                continue
            score = float(pred.get("score", 0.0))
            # Only count a clause when the model is actually sure about it.
            if score < 0.75:
                continue
            raw = str(pred.get("label", "")).upper()
            if raw == "POSITIVE":
                labels.append(SentimentLabel.POSITIVE)
            elif raw == "NEGATIVE":
                labels.append(SentimentLabel.NEGATIVE)
        return labels

    def _contrast_halves_disagree(self, raw_text: str) -> bool:
        """Score the two sides of an explicit contrast against each other.

        Covers "the wifi is good but slow", where each side is too short to pass
        the clause-length bar yet the contrast is unmistakable. Split once, at
        the first marker, so the comparison is genuinely 'before vs after'.
        """
        if self._sentiment_pipeline is None:
            return False
        match = _MIXED_SENTIMENT_RE.search(raw_text)
        if not match:
            return False

        before = raw_text[: match.start()].strip()
        after = raw_text[match.end():].strip()
        # Below this a side is a fragment ("it is", "ok") with no usable signal.
        if len(before) < 8 or len(after) < 8:
            return False

        sides: List[SentimentLabel] = []
        for side in (before, after):
            try:
                pred = self._sentiment_pipeline(side)[0]
            except Exception as exc:  # noqa: BLE001 — never fail a submission here
                logger.warning("Contrast-half sentiment failed: %s", exc)
                return False
            # A looser bar than the clause check: these halves are short, so the
            # model is legitimately less certain, but we still require a side.
            if float(pred.get("score", 0.0)) < 0.60:
                return False
            raw = str(pred.get("label", "")).upper()
            sides.append(
                SentimentLabel.POSITIVE if raw == "POSITIVE" else SentimentLabel.NEGATIVE
            )
        return sides[0] is not sides[1]

    def _is_mixed_opinion(self, raw_text: str) -> bool:
        """True when one comment carries both praise and criticism.

        Two independent signals, either of which is enough:

        1. Clause-level disagreement — the comment splits into clauses that
           DistilBERT confidently scores in opposite directions. This catches
           "The wifi is fast. The library is terrible." which contains no
           contrast word at all.
        2. An explicit contrast whose two sides score in opposite directions.

        Note what is deliberately NOT a signal: the bare presence of a contrast
        word. A complaint that concedes a detail — "the service is not reliable.
        Although the network is available, access does not mean a usable
        connection. The speed fluctuates heavily." — is negative throughout and
        must stay NEGATIVE. Treating "although" alone as mixed relabelled such
        comments NEUTRAL and quietly hid real complaints from the dashboard. A
        contrast marker is grounds to ASK (it still triggers escalation in
        `_should_escalate`); it is not grounds to overrule the answer.
        """
        labels = self._clause_sentiments(raw_text)
        if SentimentLabel.POSITIVE in labels and SentimentLabel.NEGATIVE in labels:
            return True
        return self._contrast_halves_disagree(raw_text)

    async def _classify_sentiment_gemini(self, raw_text: str) -> Tuple[SentimentLabel, float]:
        """Classify sentiment with Gemini, which handles sarcasm + local expressions."""
        prompt = (
            "You are a sentiment classifier for university student feedback about "
            "academic services. The text may use Nigerian English, Nigerian Pidgin, "
            "slang, code-switching, or sarcasm. Determine the writer's TRUE attitude "
            "toward the service, correctly handling sarcasm and local expressions "
            "(e.g. 'e sweet me die' or 'e dey blaze' = very positive; 'wahala', "
            "'e vex me', or sarcasm like 'so fast I spent 5 hours' = negative). "
            "Judge the writer's overall verdict on the service, not the presence of "
            "individual words.\n"
            "Use NEUTRAL only when praise and criticism are genuinely balanced, or "
            "when the text is a purely factual observation with no evaluation. A "
            "complaint that concedes a minor point is still NEGATIVE (e.g. "
            "'the network is available, but it is unusable and keeps cutting out' "
            "= NEGATIVE), and praise that notes a small caveat is still POSITIVE. "
            "Words like 'although', 'but' or 'however' do not by themselves make "
            "feedback neutral.\n"
            "Respond with ONLY a JSON object of the exact form "
            '{"label": "POSITIVE" | "NEGATIVE" | "NEUTRAL", "confidence": <number 0.0-1.0>}.\n\n'
            f'Feedback: "{raw_text.strip()}"'
        )
        # Bounded so a rate-limited/slow Gemini can't stall the submission; on
        # timeout the caller keeps the DistilBERT label.
        response = await asyncio.wait_for(
            self._gemini_model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": 0.0,
                    # 2.5-flash "thinks" before emitting — leave headroom so the
                    # JSON is not truncated mid-object.
                    "max_output_tokens": 1024,
                    "response_mime_type": "application/json",
                },
            ),
            timeout=self.settings.gemini_timeout_seconds,
        )
        text = (getattr(response, "text", "") or "").strip()
        data = json.loads(text)  # raises on malformed output -> caller keeps Tier B
        raw_label = str(data.get("label", "")).upper()
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))

        if raw_label == "POSITIVE":
            label = SentimentLabel.POSITIVE
        elif raw_label == "NEGATIVE":
            label = SentimentLabel.NEGATIVE
        else:
            label = SentimentLabel.NEUTRAL
        return label, round(confidence, 4)

    def _analyze_sync(self, raw_text: str) -> AnalysisResult:
        """Blocking pipeline body (Tier A -> Tier B -> Tier C).

        Tier A's stop-word-stripped, lemmatized output is recorded for audit but
        is NOT what Tiers B and C read. Both are transformer models: they were
        trained on ordinary prose and derive meaning from exactly the words that
        Tier A removes. Feeding them the cleaned string inverted the sentiment of
        any comment built on negation, because spaCy classes `not`, `no`,
        `never` and `without` as stop words — so "connects without much
        difficulty" reached DistilBERT as "connect difficulty" and scored
        NEGATIVE with 99.7% confidence when the raw sentence scores POSITIVE
        with 99.9%. Tiers B and C therefore receive the original sentence.
        """
        cleaned = self._clean_text(raw_text)                 # Tier A (audit record)
        model_input = self._model_input(raw_text)
        sentiment = self._classify_sentiment(model_input)    # Tier B
        keywords = self._extract_keywords(model_input)       # Tier C
        return AnalysisResult(
            sentiment_analysis=sentiment,
            keywords_extracted=keywords,
            cleaned_text=cleaned,
        )

    # ======================================================================
    # Tier D — Qualitative summarization (Gemini 1.5 Flash, async)
    # ======================================================================
    async def summarize_negative_cluster(
        self, department: str, negative_comments: List[str], category: str | None = None
    ) -> str:
        """
        Package a bucket of high-volume negative comments from a single
        department and call the Gemini 1.5 Flash API to synthesize a short,
        highly-readable paragraph of immediate administrative actions.

        The prompt embeds explicit operational constraints so the model
        returns concise, action-oriented guidance — not a generic essay.
        """
        if self._gemini_model is None:
            raise RuntimeError(
                "Gemini (Tier D) is not configured. Set GEMINI_API_KEY in the environment."
            )

        if not negative_comments:
            raise ValueError("No negative comments provided for summarization.")

        prompt = self._build_gemini_prompt(department, negative_comments, category)

        try:
            # The google-generativeai client exposes an async variant that
            # keeps the FastAPI event loop free while awaiting the API.
            response = await self._gemini_model.generate_content_async(
                prompt,
                generation_config={
                    "temperature": 0.3,      # deterministic, low-creativity
                    # Gemini 2.x flash is a "thinking" model — internal reasoning
                    # consumes part of the budget, so keep ample headroom or the
                    # visible summary gets truncated mid-sentence.
                    "max_output_tokens": 1024,
                    "top_p": 0.9,
                },
            )
            summary = (getattr(response, "text", "") or "").strip()
            if not summary:
                raise RuntimeError("Gemini returned an empty summary.")
            return summary
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gemini summarization (Tier D) failed.")
            raise RuntimeError("Gemini summarization error") from exc

    @staticmethod
    def _build_gemini_prompt(
        department: str, comments: List[str], category: str | None
    ) -> str:
        """Construct the constrained action-synthesis prompt template."""
        scope = f"the '{category}' service" if category else "academic services"
        joined = "\n".join(f"- {c.strip()}" for c in comments if c.strip())
        return (
            "You are an academic-quality operations analyst for a university.\n"
            f"The following are negative student feedback comments about {scope} "
            f"in the {department} department.\n\n"
            f"NEGATIVE FEEDBACK BUCKET:\n{joined}\n\n"
            "OPERATIONAL CONSTRAINTS:\n"
            "1. Synthesize ALL complaints into ONE short, highly-readable paragraph.\n"
            "2. Focus strictly on immediate, concrete administrative actions.\n"
            "3. Do not restate every complaint; identify the root theme.\n"
            "4. Keep it under 90 words, professional and directive.\n"
            "5. Do not use markdown, bullet points, or headers — plain prose only.\n\n"
            "IMMEDIATE ACTION SUMMARY:"
        )

    # ======================================================================
    @property
    def is_ready(self) -> bool:
        return self._ready


# --------------------------------------------------------------------------
# Module-level singleton accessor
# --------------------------------------------------------------------------
_engine: AIEngine | None = None


def get_ai_engine() -> AIEngine:
    """Return the shared AIEngine singleton (constructed on first access)."""
    global _engine
    if _engine is None:
        _engine = AIEngine()
    return _engine
