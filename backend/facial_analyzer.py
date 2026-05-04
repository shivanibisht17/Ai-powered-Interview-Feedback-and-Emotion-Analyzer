"""
Facial Expression Analysis using OpenCV + MediaPipe Face Mesh.

This module analyzes facial landmarks from webcam frames to detect
emotion indicators: confidence, nervousness, stress, and neutral.

Algorithm: Rule-based heuristics on 468 MediaPipe Face Mesh landmarks.
No deep learning training required - suitable for academic demo.
Heuristics were chosen over ML so the system is explainable and
deterministic (same frame -> same scores) for B.Tech viva.

Key landmark indices (MediaPipe Face Mesh):
- Mouth corners: 61 (left), 291 (right)
- Upper lip: 13, Lower lip: 14
- Left eye: 33, 133, 160, 159, 158, 157, 173
- Right eye: 263, 362, 387, 386, 385, 384, 398
- Cheeks (symmetry): 234 (left), 454 (right), nose tip: 4
"""

try:
    import cv2
except Exception:
    cv2 = None
try:
    import numpy as np
except Exception:
    np = None

from typing import Optional, Dict, Any

# Module-level cache: FaceMesh is created once per process and reused.
# This avoids "per frame" initialization and satisfies MediaPipe best practice.
_FACE_MESH_CACHE = None
_FACE_MESH_INIT_ERROR = None


def _get_mediapipe_face_mesh():
    """
    Return a MediaPipe FaceMesh instance, initialized once per process.

    Uses mp.solutions.face_mesh.FaceMesh(...). If MediaPipe is missing or
    the API is incompatible (e.g. no 'solutions' attribute), returns None
    and does NOT raise - so the Flask app never crashes.
    """
    global _FACE_MESH_CACHE, _FACE_MESH_INIT_ERROR
    if _FACE_MESH_CACHE is not None:
        return _FACE_MESH_CACHE
    if _FACE_MESH_INIT_ERROR is not None:
        return None

    if np is None or cv2 is None:
        _FACE_MESH_INIT_ERROR = "OpenCV/numpy not installed; facial analysis disabled."
        return None

    try:
        import mediapipe as mp
        # Defensive check: some environments have broken or wrong mediapipe;
        # ensure the expected API exists before using it.
        if not hasattr(mp, "solutions"):
            _FACE_MESH_INIT_ERROR = (
                "MediaPipe installed but 'solutions' not found. "
                "Use mediapipe==0.10.9 for Face Mesh compatibility."
            )
            return None
        face_mesh_module = mp.solutions.face_mesh
        if not hasattr(face_mesh_module, "FaceMesh"):
            _FACE_MESH_INIT_ERROR = (
                "MediaPipe face_mesh module has no 'FaceMesh'. "
                "Pin to mediapipe==0.10.9."
            )
            return None
        _FACE_MESH_CACHE = face_mesh_module.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )
        return _FACE_MESH_CACHE
    except ImportError as e:
        _FACE_MESH_INIT_ERROR = f"MediaPipe not installed: {e}. Install with: pip install mediapipe==0.10.9"
        return None
    except AttributeError as e:
        _FACE_MESH_INIT_ERROR = (
            f"MediaPipe API error: {e}. Use mediapipe==0.10.9 for Face Mesh."
        )
        return None
    except Exception as e:
        _FACE_MESH_INIT_ERROR = f"MediaPipe Face Mesh init failed: {e}"
        return None


def _analyze_single_frame(frame_rgb, face_mesh) -> Optional[Dict[str, Any]]:
    """
    Analyze one frame for facial emotion indicators using rule-based heuristics.

    Returns dict with confidence_score, nervousness_score, stress_score,
    dominant_emotion (confident|nervous|stressed|neutral), or None if no face.
    Same input frame always yields same output (deterministic).
    """
    if frame_rgb is None or frame_rgb.size == 0:
        return None

    results = face_mesh.process(frame_rgb)
    if not results.multi_face_landmarks:
        return None

    landmarks = results.multi_face_landmarks[0]
    h, w = frame_rgb.shape[:2]

    # Convert normalized (0-1) landmarks to pixel coordinates (deterministic)
    def pt(i):
        lm = landmarks.landmark[i]
        return np.array([lm.x * w, lm.y * h], dtype=np.float64)

    # -------------------------------------------------------------------------
    # Heuristic 1: Smile ratio -> confidence
    # Chosen because: smiling is a strong, interpretable signal for confidence.
    # Landmarks: 61 (left mouth corner), 291 (right), 13 (upper lip), 14 (lower).
    # When corners rise relative to lip center, we interpret as smile.
    # -------------------------------------------------------------------------
    left_mouth = pt(61)
    right_mouth = pt(291)
    upper_lip = pt(13)
    lower_lip = pt(14)
    mouth_center_y = (upper_lip[1] + lower_lip[1]) / 2
    corner_avg_y = (left_mouth[1] + right_mouth[1]) / 2
    # Normalize by mouth width (more stable than image width).
    mouth_width = float(np.linalg.norm(right_mouth - left_mouth)) + 1e-6
    # Positive when corners are higher than lip center (smile).
    smile_lift = float((mouth_center_y - corner_avg_y) / mouth_width)
    # Map small lifts to a wider 0–100 range (empirically more responsive).
    smile_score = min(100.0, max(0.0, 55.0 + smile_lift * 220.0))

    # -------------------------------------------------------------------------
    # Heuristic 2: Eye Aspect Ratio (EAR) -> stress
    # Chosen because: squinting / closed eyes correlate with stress; EAR is
    # a standard, lightweight measure. Formula: (||p2-p6|| + ||p3-p5||) / (2*||p1-p4||).
    # Landmarks: left 33,160,158,133,153,144; right 263,387,385,362,380,373.
    # -------------------------------------------------------------------------
    def ear(eye_indices):
        p1, p2, p3, p4, p5, p6 = [pt(i) for i in eye_indices]
        v1 = np.linalg.norm(p2 - p6)
        v2 = np.linalg.norm(p3 - p5)
        v3 = 2 * np.linalg.norm(p1 - p4) + 1e-6
        return (v1 + v2) / v3

    left_eye_idx = [33, 160, 158, 133, 153, 144]
    right_eye_idx = [263, 387, 385, 362, 380, 373]
    ear_left = ear(left_eye_idx)
    ear_right = ear(right_eye_idx)
    ear_avg = (ear_left + ear_right) / 2
    # Typical EAR ~0.2-0.4; lower = more squint -> higher stress score
    # Rescaled so normal open eyes ~20–40 stress, strong squint pushes higher.
    stress_from_eyes = max(0.0, min(100.0, 30.0 + (0.30 - float(ear_avg)) * 420.0))

    # -------------------------------------------------------------------------
    # Heuristic 3: Mouth openness + facial symmetry -> nervousness
    # Chosen because: excessive mouth opening and asymmetry can indicate
    # nervousness; no ML needed, just geometry on landmarks 13, 14 and 4, 234, 454.
    # -------------------------------------------------------------------------
    mouth_open = np.linalg.norm(upper_lip - lower_lip) / (h * 0.05 + 1e-6)
    mouth_nervous = min(100.0, mouth_open * 30.0)

    left_cheek = pt(234)
    right_cheek = pt(454)
    nose_tip = pt(4)
    sym_left = np.linalg.norm(nose_tip - left_cheek)
    sym_right = np.linalg.norm(nose_tip - right_cheek)
    sym_ratio = min(sym_left, sym_right) / (max(sym_left, sym_right) + 1e-6)
    asymmetry_stress = max(0.0, (1.0 - sym_ratio) * 50.0)

    # Composite scores (0-100), deterministic
    confidence_score = smile_score * 0.7 + (100.0 - stress_from_eyes) * 0.3
    confidence_score = min(100.0, max(0.0, confidence_score))

    nervousness_score = mouth_nervous * 0.5 + asymmetry_stress * 0.5
    nervousness_score = min(100.0, max(0.0, nervousness_score))

    stress_score = stress_from_eyes * 0.6 + asymmetry_stress * 0.4
    stress_score = min(100.0, max(0.0, stress_score))

    # Dominant emotion:
    # - Choose "neutral" only when signals are weak (otherwise it dominates too often).
    max_signal = max(confidence_score, nervousness_score, stress_score)
    if max_signal < 55.0:
        dominant = "neutral"
    else:
        dominant = max(
            {"confident": confidence_score, "nervous": nervousness_score, "stressed": stress_score},
            key=lambda k: {"confident": confidence_score, "nervous": nervousness_score, "stressed": stress_score}[k],
        )

    return {
        "confidence_score": int(round(min(100, max(0, confidence_score)))),
        "nervousness_score": int(round(min(100, max(0, nervousness_score)))),
        "stress_score": int(round(min(100, max(0, stress_score)))),
        "dominant_emotion": dominant,
        "is_fallback": False,
        "smile_indicator": round(smile_lift, 4),
        "smile_score": round(float(smile_score), 1),
        "eye_openness_ear": round(ear_avg, 3),
    }


def _decode_frame_from_bytes(data: bytes):
    """Decode image bytes (JPEG/PNG) to OpenCV BGR format."""
    if not data or len(data) < 100:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _fallback_response(note: str) -> dict:
    """Return the standard fallback payload when no face or no MediaPipe."""
    return {
        "confidence_score": 50,
        "nervousness_score": 50,
        "stress_score": 50,
        "dominant_emotion": "neutral",
        "is_fallback": True,
        "note": note,
        "frames_analyzed": 0,
        "summary": note,
    }


def analyze_facial_frames(frames: list) -> dict:
    """
    Analyze multiple frames and return aggregated facial metrics.

    Fallback values (50, 50, 50, neutral) are used ONLY when:
    - MediaPipe fails to initialize, or
    - No face landmarks are detected in any frame.

    When landmarks are available, real rule-based scores are computed.
    Output is deterministic: same frames -> same scores.

    Returns:
        dict with: confidence_score, nervousness_score, stress_score (int 0-100),
        dominant_emotion ("confident"|"nervous"|"stressed"|"neutral"),
        is_fallback (bool), note (optional str), frames_analyzed, summary, per_frame.
    """
    face_mesh = _get_mediapipe_face_mesh()
    if face_mesh is None:
        note = _FACE_MESH_INIT_ERROR or "MediaPipe not available; using default scores."
        return _fallback_response(note)

    results_list = []
    decoded = []
    for frame in frames:
        if frame is None:
            continue
        if isinstance(frame, bytes):
            frame = _decode_frame_from_bytes(frame)
        if frame is None:
            continue
        decoded.append(frame)

    for frame in decoded:
        if len(frame.shape) == 2:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        else:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        try:
            r = _analyze_single_frame(frame_rgb, face_mesh)
        except Exception:
            r = None
        if r is not None:
            results_list.append(r)

    # Do not close the cached FaceMesh so it can be reused
    # face_mesh.close()  # removed: we use module-level cache

    if not results_list:
        return _fallback_response("No face detected in captured frames.")

    # Aggregate: median for stability; deterministic
    confidences = [x["confidence_score"] for x in results_list]
    nervousness = [x["nervousness_score"] for x in results_list]
    stresses = [x["stress_score"] for x in results_list]
    avg_conf = int(round(np.median(confidences)))
    avg_nerv = int(round(np.median(nervousness)))
    avg_stress = int(round(np.median(stresses)))

    # Dominant emotion aggregation:
    # If we have enough "signal" frames (non-neutral), pick the most common among those.
    # Otherwise fall back to neutral (prevents always-neutral bias when signals are weak).
    from collections import Counter

    def _frame_signal(x: dict) -> float:
        return float(max(x.get("confidence_score", 0), x.get("nervousness_score", 0), x.get("stress_score", 0)))

    signal_frames = [x for x in results_list if _frame_signal(x) >= 55.0 and x.get("dominant_emotion") != "neutral"]
    if len(signal_frames) >= max(2, int(0.2 * len(results_list))):
        dominant = Counter([x["dominant_emotion"] for x in signal_frames]).most_common(1)[0][0]
    else:
        dominant = "neutral"

    summary = (
        f"Analyzed {len(results_list)} frame(s). "
        f"Avg confidence: {avg_conf}/100, nervousness: {avg_nerv}/100, "
        f"stress: {avg_stress}/100. Dominant: {dominant}."
    )
    return {
        "confidence_score": avg_conf,
        "nervousness_score": avg_nerv,
        "stress_score": avg_stress,
        "dominant_emotion": dominant,
        "is_fallback": False,
        "note": summary,
        "frames_analyzed": len(results_list),
        "per_frame": results_list,
        "summary": summary,
    }
