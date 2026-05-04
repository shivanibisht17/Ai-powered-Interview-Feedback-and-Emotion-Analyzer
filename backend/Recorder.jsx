/**
 * Recorder — single getUserMedia stream; MediaRecorder for final answer blob;
 * JPEG frames every 2s for submit_answer; realtime ping every 3s with last audio chunk + frame.
 */

import { useState, useRef, useCallback, useEffect } from "react";

const FRAME_INTERVAL_MS = 2000;
const REALTIME_INTERVAL_MS = 3000;
const JPEG_QUALITY = 0.85;
/** Smaller internal chunks help assemble the final recording; realtime uses its own 3s cadence. */
const MEDIA_RECORDER_TIMESLICE_MS = 1000;

export default function Recorder({
  onComplete,
  disabled,
  maxDurationSeconds = 75,
  onRealtimeUpdate,
  onRecordingChange,
}) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const secondsRef = useRef(0);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const frameIntervalRef = useRef(null);
  const realtimeIntervalRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const facialFramesRef = useRef([]);
  const lastAudioChunkRef = useRef(null);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2 || video.videoWidth === 0) return null;
    const ctx = canvas.getContext("2d");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0);
    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), "image/jpeg", JPEG_QUALITY);
    });
  }, []);

  const stopRecording = useCallback(() => {
    if (!recording) return;
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current);
      frameIntervalRef.current = null;
    }
    if (realtimeIntervalRef.current) {
      clearInterval(realtimeIntervalRef.current);
      realtimeIntervalRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") rec.stop();
    recorderRef.current = null;
  }, [recording]);

  useEffect(() => {
    return () => {
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
      if (realtimeIntervalRef.current) clearInterval(realtimeIntervalRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (typeof onRecordingChange === "function") onRecordingChange(recording);
  }, [recording, onRecordingChange]);

  const startRecording = useCallback(async () => {
    if (disabled || recording) return;
    chunksRef.current = [];
    facialFramesRef.current = [];
    lastAudioChunkRef.current = null;

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: true,
    });
    streamRef.current = stream;
    if (videoRef.current) videoRef.current.srcObject = stream;

    // Record audio-only for maximum backend decode compatibility.
    // We still keep the video track in `stream` for webcam preview + frame capture.
    const audioOnlyStream = new MediaStream(stream.getAudioTracks());
    const preferredMimeTypes = ["audio/webm;codecs=opus", "audio/webm", "video/webm;codecs=vp8,opus", "video/webm"];
    const selectedMimeType = preferredMimeTypes.find((t) => {
      try {
        return typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t);
      } catch {
        return false;
      }
    });
    const recorder = selectedMimeType
      ? new MediaRecorder(audioOnlyStream, { mimeType: selectedMimeType })
      : new MediaRecorder(audioOnlyStream);
    recorderRef.current = recorder;
    const chunks = [];
    chunksRef.current = chunks;

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        chunks.push(e.data);
        lastAudioChunkRef.current = e.data;
      }
    };

    recorder.onstop = () => {
      const mime = recorder.mimeType || selectedMimeType || "audio/webm";
      const audioBlob = new Blob(chunks, { type: mime });
      onComplete(audioBlob, facialFramesRef.current, { timeTaken: secondsRef.current });
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      setRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
      if (realtimeIntervalRef.current) clearInterval(realtimeIntervalRef.current);
    };

    recorder.start(MEDIA_RECORDER_TIMESLICE_MS);
    setRecording(true);
    setSeconds(0);
    secondsRef.current = 0;
    timerRef.current = setInterval(() => {
      setSeconds((s) => {
        const next = s + 1;
        secondsRef.current = next;
        if (next >= maxDurationSeconds) {
          stopRecording();
        }
        return next;
      });
    }, 1000);

    frameIntervalRef.current = setInterval(async () => {
      const blob = await captureFrame();
      if (blob) facialFramesRef.current.push(blob);
    }, FRAME_INTERVAL_MS);

    if (typeof onRealtimeUpdate === "function") {
      realtimeIntervalRef.current = setInterval(async () => {
        const frameBlob = await captureFrame();
        const chunk = lastAudioChunkRef.current;
        onRealtimeUpdate(chunk, frameBlob);
      }, REALTIME_INTERVAL_MS);
    }

  }, [disabled, recording, onComplete, captureFrame, onRealtimeUpdate, maxDurationSeconds, stopRecording]);

  return (
    <div className="flex flex-col gap-3 items-start">
      <div className="relative rounded-xl overflow-hidden border border-slate-700 bg-surface-800 shadow-lg max-w-md w-full aspect-video">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={recording ? "w-full h-full object-cover" : "hidden"}
        />
        <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
        {recording && (
          <div className="absolute top-2 left-2 px-2 py-1 rounded-md bg-red-600/90 text-xs font-semibold tracking-wide">
            REC
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {recording ? (
          <>
            <span className="text-lg font-mono text-accent tabular-nums">
              {seconds}s / {maxDurationSeconds}s
            </span>
            <button
              type="button"
              className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-sm font-medium transition"
              onClick={stopRecording}
            >
              Stop
            </button>
          </>
        ) : (
          <button
            type="button"
            className="px-5 py-2.5 rounded-lg bg-accent hover:bg-accent-dim text-surface-900 font-semibold text-sm transition shadow-lg shadow-sky-500/20"
            onClick={startRecording}
            disabled={disabled}
            aria-label="Start recording"
          >
            Record Answer
          </button>
        )}
      </div>
    </div>
  );
}
