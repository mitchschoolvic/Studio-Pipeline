/**
 * KioskWaveform - Canvas-based waveform visualization
 * 
 * Zero-dependency replacement for WaveSurfer.js.
 * Only draws pre-generated peaks and syncs progress — no audio loading.
 * 
 * Features:
 * - Pre-generated peaks from backend
 * - Click-to-seek
 * - Progress sync with video player
 * - Responsive resize via ResizeObserver
 */

import { useRef, useEffect, useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';

// Fetch waveform data
async function fetchWaveform(fileId) {
    const response = await fetch(`/api/waveforms/${fileId}`);
    if (response.status === 202) {
        throw new Error('GENERATING');
    }
    if (!response.ok) {
        throw new Error('Failed to fetch waveform');
    }
    return response.json();
}

// --- Canvas drawing ---

const BAR_WIDTH = 2;
const BAR_GAP = 1;
const BAR_RADIUS = 1;
const WAVE_COLOR = '#4a5568';
const PROGRESS_COLOR = '#3b82f6';
const CURSOR_COLOR = '#fff';
const CURSOR_WIDTH = 2;

function drawWaveform(canvas, peaks, progress) {
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.scale(dpr, dpr);

    const step = BAR_WIDTH + BAR_GAP;
    const barCount = Math.floor(w / step);
    const centerY = h / 2;
    const maxBarH = h * 0.9; // leave a bit of padding

    // Resample peaks to match bar count
    const resampled = resamplePeaks(peaks, barCount);
    const progressX = progress * w;

    for (let i = 0; i < barCount; i++) {
        const x = i * step;
        const peak = resampled[i];
        const barH = Math.max(2, peak * maxBarH);
        const y = centerY - barH / 2;

        ctx.fillStyle = x + BAR_WIDTH <= progressX ? PROGRESS_COLOR : WAVE_COLOR;
        roundRect(ctx, x, y, BAR_WIDTH, barH, BAR_RADIUS);
    }

    // Draw cursor line at progress position
    if (progress > 0 && progress < 1) {
        ctx.fillStyle = CURSOR_COLOR;
        ctx.fillRect(Math.round(progressX) - CURSOR_WIDTH / 2, 0, CURSOR_WIDTH, h);
    }

    ctx.restore();
}

function resamplePeaks(peaks, targetCount) {
    if (!peaks || peaks.length === 0 || targetCount <= 0) return [];
    const result = new Array(targetCount);
    const ratio = peaks.length / targetCount;
    for (let i = 0; i < targetCount; i++) {
        const start = Math.floor(i * ratio);
        const end = Math.min(Math.floor((i + 1) * ratio), peaks.length);
        let max = 0;
        for (let j = start; j < end; j++) {
            const v = Math.abs(peaks[j]);
            if (v > max) max = v;
        }
        result[i] = max;
    }
    return result;
}

function roundRect(ctx, x, y, w, h, r) {
    if (h < r * 2) r = h / 2;
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.arcTo(x + w, y, x + w, y + r, r);
    ctx.lineTo(x + w, y + h - r);
    ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
    ctx.lineTo(x + r, y + h);
    ctx.arcTo(x, y + h, x, y + h - r, r);
    ctx.lineTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.fill();
}

// --- Component ---

export function KioskWaveform({ fileId, videoPlayerRef, duration = 0, onSeek }) {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const [size, setSize] = useState({ width: 0, height: 0 });

    // Fetch waveform data
    const { data: waveformData, isLoading, error, refetch } = useQuery({
        queryKey: ['waveform', fileId],
        queryFn: () => fetchWaveform(fileId),
        enabled: !!fileId,
        retry: (failureCount, error) => {
            if (error?.message === 'GENERATING') {
                return failureCount < 60; // up to 60s for on-demand generation
            }
            return failureCount < 3;
        },
        retryDelay: 1000,
        staleTime: Infinity,
    });

    // Observe container size for responsive canvas
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const measure = () => {
            // Use clientWidth/Height for the actual visible area
            // Subtract 1rem (16px) total padding (0.5rem inset on each side)
            const w = container.clientWidth - 16;
            const h = container.clientHeight - 16;
            if (w > 0 && h > 0) {
                setSize({ width: w, height: h });
            }
        };

        // Initial measurement
        measure();

        const ro = new ResizeObserver(() => measure());
        ro.observe(container);
        return () => ro.disconnect();
    }, []);

    // Size canvas to container (retina-aware)
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || size.width === 0) return;
        const dpr = window.devicePixelRatio || 1;
        canvas.width = size.width * dpr;
        canvas.height = size.height * dpr;
        canvas.style.width = size.width + 'px';
        canvas.style.height = size.height + 'px';
    }, [size]);

    // 60fps canvas drawing via requestAnimationFrame
    // Reads currentTime directly from video player ref — no React state/re-renders
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || !waveformData?.peaks || size.width === 0) return;

        let rafId;
        let lastDrawnTime = -1;

        const tick = () => {
            const time = videoPlayerRef?.current?.currentTime ?? 0;
            // Use video player duration as truth (handles gesture-trimmed videos)
            const totalDuration = duration || waveformData.duration || 0;

            // Only redraw when time actually changes (saves CPU when paused)
            if (time !== lastDrawnTime || lastDrawnTime === -1) {
                lastDrawnTime = time;
                const progress = totalDuration > 0 ? Math.max(0, Math.min(1, time / totalDuration)) : 0;
                drawWaveform(canvas, waveformData.peaks, progress);
            }
            rafId = requestAnimationFrame(tick);
        };

        rafId = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(rafId);
    }, [waveformData, duration, size, videoPlayerRef]);

    // Seek from pointer/touch position — uses video player duration as truth
    const seekFromEvent = useCallback((e) => {
        const canvas = canvasRef.current;
        if (!canvas || !waveformData) return;
        const rect = canvas.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const relativeX = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const totalDuration = duration || waveformData.duration || 0;
        onSeek?.(relativeX * totalDuration);
    }, [waveformData, duration, onSeek]);

    // Drag/touch-to-seek for touchscreen kiosk
    const isDragging = useRef(false);

    const handlePointerDown = useCallback((e) => {
        isDragging.current = true;
        seekFromEvent(e);
        // Capture so we get move/up even outside the element
        e.target.setPointerCapture?.(e.pointerId);
    }, [seekFromEvent]);

    const handlePointerMove = useCallback((e) => {
        if (!isDragging.current) return;
        seekFromEvent(e);
    }, [seekFromEvent]);

    const handlePointerUp = useCallback(() => {
        isDragging.current = false;
    }, []);

    // Render states — always render container+canvas so ResizeObserver attaches on mount.
    // Loading/error are overlaid on top; without this the canvas is only in the DOM
    // after data loads, so the [] ResizeObserver effect misses it and size stays 0×0.
    if (!fileId) return null;

    const showLoading = isLoading || error?.message === 'GENERATING';
    const showError = error && error.message !== 'GENERATING';

    return (
        <>
            <div
              ref={containerRef}
              className="waveform-container"
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
            >
                <canvas ref={canvasRef} />
                {showLoading && (
                    <div className="waveform-overlay waveform-loading">
                        <div className="waveform-loading-bar" />
                        <span>Generating waveform...</span>
                    </div>
                )}
                {showError && (
                    <div className="waveform-overlay waveform-error">
                        Waveform unavailable
                        <button
                            onClick={() => refetch()}
                            style={{
                                marginLeft: '0.5rem',
                                padding: '0.2rem 0.5rem',
                                fontSize: '0.75rem',
                                background: '#333',
                                color: '#aaa',
                                border: '1px solid #555',
                                borderRadius: '4px',
                                cursor: 'pointer',
                            }}
                        >
                            Retry
                        </button>
                    </div>
                )}
            </div>
            <style>{`
        .waveform-container {
          width: 100%;
          height: 100%;
          cursor: pointer;
          box-sizing: border-box;
          position: relative;
          touch-action: none;
          user-select: none;
        }
        .waveform-container canvas {
          display: block;
          position: absolute;
          inset: 0.5rem;
        }
        .waveform-overlay {
          position: absolute;
          inset: 0;
          z-index: 1;
          background: rgba(10,10,10,0.85);
        }
        .waveform-loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100%;
          gap: 0.5rem;
          color: #666;
        }
        .waveform-loading-bar {
          width: 60%;
          height: 4px;
          background: #333;
          border-radius: 2px;
          overflow: hidden;
        }
        .waveform-loading-bar::after {
          content: '';
          display: block;
          width: 40%;
          height: 100%;
          background: #3b82f6;
          animation: waveform-loading 1.5s ease-in-out infinite;
        }
        @keyframes waveform-loading {
          0%, 100% { transform: translateX(-100%); }
          50% { transform: translateX(250%); }
        }
        .waveform-error {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: #666;
        }
      `}</style>
        </>
    );
}
