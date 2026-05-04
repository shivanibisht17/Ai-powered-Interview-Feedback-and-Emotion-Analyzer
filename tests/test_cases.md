# AI Interview System - Test Cases

For B.Tech Final Year Project demo and viva.

## 1. Resume Upload

| # | Description | Input | Expected |
|---|-------------|-------|----------|
| 1.1 | Valid PDF upload | Resume PDF file | 200, extracted_text, questions array |
| 1.2 | No file | Empty form | 400, "No PDF file provided" |
| 1.3 | Non-PDF file | .docx or .txt | 400, "File must be a PDF" |

## 2. Submit Answer (Voice Only)

| # | Description | Input | Expected |
|---|-------------|-------|----------|
| 2.1 | Valid audio + question | WebM audio, question text | 200, transcript, voice_analysis, evaluation |
| 2.2 | No audio | Form without audio | 400, "No audio file provided" |
| 2.3 | No question | Audio without question | 400, "Question text is required" |
| 2.4 | Short audio (<0.5s) | Very short recording | 200, nervous_score 50, "Audio too short" |

## 3. Submit Answer (Voice + Webcam)

| # | Description | Input | Expected |
|---|-------------|-------|----------|
| 3.1 | Audio + facial frames | Audio + 3–5 JPEG frames | 200, facial_analysis with confidence/nervousness |
| 3.2 | Audio only (no webcam) | Audio, no frames | 200, facial_analysis with default 50/50 scores |

## 4. Facial Analysis (Standalone)

| # | Description | Input | Expected |
|---|-------------|-------|----------|
| 4.1 | Single image | JPEG/PNG file | 200, confidence_score, nervousness_score |
| 4.2 | Multiple images | Several facial_frames | 200, aggregated per-frame metrics |

## 5. End Interview & Feedback

| # | Description | Input | Expected |
|---|-------------|-------|----------|
| 5.1 | End after answers | POST /end_interview | 200, status ok |
| 5.2 | Get feedback | GET /feedback | 200, interview_confidence_score, strengths, weaknesses |

## 6. Multi-Modal Fusion Verification

| # | Description | Check |
|---|-------------|-------|
| 6.1 | Fusion formula | Interview_Confidence = 0.35*voice_conf + 0.25*facial_conf + 0.4*relevance |
| 6.2 | Score range | 0–100 |
| 6.3 | Breakdown present | fusion_breakdown has voice, facial, answer contributions |

## Demo Flow (Manual)

1. Start backend: `cd backend && python app.py`
2. Start frontend: `cd frontend && npm run dev`
3. Upload resume → Verify questions generated
4. Answer Q1 with webcam on → Verify transcript, voice, facial, evaluation
5. Answer remaining questions
6. View feedback → Verify Interview Confidence Score, fusion breakdown
