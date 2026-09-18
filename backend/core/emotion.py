"""
SAM Ultra — Emotion Detection
Detects user emotional state from text patterns.
Used to adapt SAM's tone and response style.
"""
import re
from models.schemas import EmotionEstimate


EMOTION_PATTERNS = {
    "frustrated": [
        r"\b(ugh|argh|damn|wtf|seriously|ridiculous|stupid|broken|failing|nothing works)\b",
        r"\b(not working|doesn't work|won't work|keeps failing|still broken)\b",
        r"(!!+|\?\?+)",
        r"\b(why (is|does|won't|can't)|how (is|does) this)\b.*\?",
    ],
    "stressed": [
        r"\b(urgent|asap|deadline|emergency|critical|immediately|right now|hurry)\b",
        r"\b(need (this|it) (now|fast|quick|asap))\b",
        r"\b(running out of time|due (today|soon|in an hour))\b",
    ],
    "excited": [
        r"\b(amazing|awesome|incredible|fantastic|wow|love it|this is great|so cool)\b",
        r"(!{2,})",
        r"\b(just (got|found|discovered|built|made|shipped))\b",
        r"(yay|yes+|woo+|let's go)\b",
    ],
    "tired": [
        r"\b(tired|exhausted|sleepy|drained|worn out|can't focus|brain (fog|dead))\b",
        r"\b(so tired|really tired|barely awake|need sleep|been up)\b",
        r"\b(long day|rough day|been a while|been working for)\b",
    ],
    "curious": [
        r"\b(how does|how do|why does|why do|what if|wondering|curious)\b",
        r"\b(explain|tell me (more|about)|help me understand|deep dive)\b",
        r"\b(what would happen|what's the difference|compare|versus|vs\.)\b",
    ],
    "satisfied": [
        r"\b(perfect|great job|well done|exactly|that's it|works|fixed|solved)\b",
        r"\b(thank you|thanks a lot|appreciate it|helpful)\b",
        r"\b(got it|makes sense|clear now|understand)\b",
    ],
}


def detect_emotion(text: str) -> EmotionEstimate:
    """Detect emotional state from user message."""
    text_lower = text.lower()
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}

    for emotion, patterns in EMOTION_PATTERNS.items():
        matches = []
        for pattern in patterns:
            found = re.findall(pattern, text_lower)
            matches.extend(found)

        flat = []
        for m in matches:
            if isinstance(m, str):
                flat.append(m)
            elif isinstance(m, tuple):
                flat.extend(x for x in m if x)
        if flat:
            scores[emotion] = len(flat)
            evidence[emotion] = flat[:3]

    if not scores:
        return EmotionEstimate(mood="neutral", confidence=0.0, evidence=[])

    best_emotion = max(scores, key=lambda k: scores[k])
    total = sum(scores.values())
    confidence = min(scores[best_emotion] / max(total, 1), 1.0)

    return EmotionEstimate(
        mood=best_emotion,
        confidence=round(confidence, 2),
        evidence=evidence.get(best_emotion, []),
    )
