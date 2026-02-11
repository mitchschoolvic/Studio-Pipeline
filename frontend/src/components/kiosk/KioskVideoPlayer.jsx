/**
 * KioskVideoPlayer - Video.js-based player component
 * 
 * Features:
 * - Byte-range streaming for smooth scrubbing
 * - Clean playback controls
 * - Fullscreen optimized
 */

import { useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';

export const KioskVideoPlayer = forwardRef(function KioskVideoPlayer(
    { file, onTimeUpdate, onDurationChange, onPlayStateChange },
    ref
) {
    const videoContainerRef = useRef(null);
    const playerRef = useRef(null);
    const videoElementRef = useRef(null);

    // Expose video element methods via ref
    useImperativeHandle(ref, () => ({
        get currentTime() {
            return playerRef.current?.currentTime() ?? 0;
        },
        set currentTime(time) {
            if (playerRef.current) {
                playerRef.current.currentTime(time);
            }
        },
        play() {
            playerRef.current?.play();
        },
        pause() {
            playerRef.current?.pause();
        },
        paused() {
            return playerRef.current?.paused() ?? true;
        }
    }));

    // Initialize Video.js player
    useEffect(() => {
        if (!videoContainerRef.current) return;

        // Create video element if not exists
        if (!videoElementRef.current) {
            const videoElement = document.createElement('video');
            videoElement.className = 'video-js vjs-big-play-centered vjs-theme-city';
            videoContainerRef.current.appendChild(videoElement);
            videoElementRef.current = videoElement;
        }

        // Initialize player
        const player = videojs(videoElementRef.current, {
            controls: true,
            fluid: false,
            fill: true,
            preload: 'metadata',
            playbackRates: [0.5, 0.75, 1, 1.25, 1.5, 2],
            controlBar: {
                volumePanel: { inline: false },
                pictureInPictureToggle: false,
            }
        });

        playerRef.current = player;

        // Time update events
        player.on('timeupdate', () => {
            onTimeUpdate?.(player.currentTime());
        });

        player.on('loadedmetadata', () => {
            onDurationChange?.(player.duration());
        });

        player.on('play', () => {
            onPlayStateChange?.(true);
        });

        player.on('pause', () => {
            onPlayStateChange?.(false);
        });

        player.on('ended', () => {
            onPlayStateChange?.(false);
        });

        return () => {
            if (playerRef.current) {
                playerRef.current.dispose();
                playerRef.current = null;
                videoElementRef.current = null;
            }
        };
    }, []);

    // Update source when file changes
    useEffect(() => {
        if (playerRef.current && file) {
            playerRef.current.src({
                type: 'video/mp4',
                src: `/api/videos/${file.id}/stream`
            });

            // Auto-play on file selection
            playerRef.current.play().catch(() => {
                // Autoplay may be blocked by browser
                console.log('Autoplay blocked, user must interact');
            });
        }
    }, [file?.id]);

    return (
        <>
            <div
                ref={videoContainerRef}
                className="kiosk-video-container"
                data-vjs-player
            />
            <style>{`
        .kiosk-video-container {
          width: 100%;
          height: 100%;
        }
        
        .kiosk-video-container .video-js {
          width: 100%;
          height: 100%;
          background: transparent;
          border-radius: 8px;
          overflow: hidden;
        }
        
        /* Custom theme overrides */
        .kiosk-video-container .vjs-control-bar {
          background: linear-gradient(transparent, rgba(0,0,0,0.8));
          height: 50px;
          padding: 0 1rem;
        }
        
        .kiosk-video-container .vjs-big-play-button {
          background: rgba(255,255,255,0.2);
          border: 2px solid white;
          border-radius: 50%;
          font-size: 3rem;
          width: 80px;
          height: 80px;
          line-height: 76px;
        }
        
        .kiosk-video-container .vjs-big-play-button:hover {
          background: rgba(255,255,255,0.3);
        }
        
        .kiosk-video-container .vjs-progress-holder {
          height: 6px;
          border-radius: 3px;
        }
        
        .kiosk-video-container .vjs-play-progress {
          background: #3b82f6;
          border-radius: 3px;
        }
        
        .kiosk-video-container .vjs-load-progress {
          background: rgba(255,255,255,0.2);
        }
      `}</style>
        </>
    );
});
