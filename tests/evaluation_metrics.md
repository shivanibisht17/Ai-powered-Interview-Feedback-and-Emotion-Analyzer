# Evaluation Metrics - AI Interview Emotion Analyzer

Academic demo metrics for B.Tech Final Year Project documentation.

## 1. Multi-Modal Fusion Formula

```
Interview_Confidence_Score = w1 × (100 - Voice_Nervous) + w2 × Facial_Confidence + w3 × Answer_Relevance

Weights: w1 = 0.35 (voice), w2 = 0.25 (facial), w3 = 0.40 (answer)
```

## 2. Voice Analysis Metrics

| Metric | Source | Range | Interpretation |
|--------|--------|-------|----------------|
| nervous_score | Librosa pitch variance + silence ratio | 0–100 | Higher = more nervous |
| pitch_mean_hz | piptrack | 0–500 | Typical speech 85–255 Hz |
| silence_ratio | onset/split | 0–1 | Higher = more pauses |
| energy | RMS | 0–1 | Higher = louder |

## 3. Facial Analysis Metrics

| Metric | Source | Range | Interpretation |
|--------|--------|-------|----------------|
| confidence_score | Smile + eye openness heuristics | 0–100 | Higher = more confident |
| nervousness_score | Mouth openness + asymmetry | 0–100 | Higher = more nervous |
| stress_score | Eye aspect ratio + asymmetry | 0–100 | Higher = more stress |
| dominant_emotion | argmax(confidence, nervous, stress, neutral) | enum | Primary detected emotion |

## 4. Answer Relevance Metrics

| Metric | Source | Range | Interpretation |
|--------|--------|-------|----------------|
| relevance_score | TF-IDF cosine similarity (Q, R, A) | 0–100 | Higher = more relevant |
| clarity | Word count, filler words | poor/fair/good | Subjective quality |
| detected_keywords | Resume keyword match | list | Resume terms in answer |

## 5. Comparison / Accuracy (Demo)

For academic reporting, the following are suitable as “evaluation”:

- **Fusion consistency**: Same inputs → same output (deterministic)
- **Metric correlation**: Voice nervous ↑ → Confidence score ↓ (expected)
- **Face detection**: MediaPipe Face Mesh ~95%+ on frontal faces
- **Relevance alignment**: TF-IDF + cosine similarity standard for text similarity

## 6. Sample Baseline

| Scenario | Voice Nervous | Facial Conf | Relevance | Expected Fusion |
|----------|---------------|-------------|-----------|-----------------|
| Confident answer | 30 | 70 | 80 | ~67 |
| Nervous answer | 70 | 40 | 60 | ~42 |
| Mixed | 50 | 50 | 50 | 50 |

Formula check: 0.35×(100-50) + 0.25×50 + 0.4×50 = 17.5 + 12.5 + 20 = 50 ✓
