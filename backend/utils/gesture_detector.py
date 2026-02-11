"""
Gesture Detector - Closed Fist Detection for Video Trimming

Uses MediaPipe Hands to detect closed fist gestures at the end of videos.
Designed to run on CPU to avoid GPU contention with AI workers.

The closed fist gesture is used by presenters to signal "stop recording"
in the video studio. This module detects that gesture and determines
the appropriate trim point.

Compatible with MediaPipe 0.10.x (Tasks API).
"""
import cv2
import numpy as np
import sys
from pathlib import Path
from typing import Optional, Tuple, List
import logging
import urllib.request
import os

logger = logging.getLogger(__name__)

# Try to import MediaPipe - detect which API is available
MEDIAPIPE_AVAILABLE = False
MEDIAPIPE_NEW_API = False

try:
    import mediapipe as mp
    # Check if we have the new Tasks API (0.10.x+)
    if hasattr(mp, 'tasks'):
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        MEDIAPIPE_AVAILABLE = True
        MEDIAPIPE_NEW_API = True
        logger.debug("MediaPipe Tasks API (0.10.x+) detected")
    elif hasattr(mp, 'solutions'):
        # Legacy API (pre-0.10)
        MEDIAPIPE_AVAILABLE = True
        MEDIAPIPE_NEW_API = False
        logger.debug("MediaPipe Solutions API (legacy) detected")
    else:
        logger.warning("MediaPipe installed but no recognized API found")
except ImportError as e:
    logger.warning(f"MediaPipe not available: {e}")


class GestureDetector:
    """
    Detects closed fist gestures to determine video trim points.
    
    Algorithm:
    1. Check last 3 frames (at 1-second intervals) for closed fist
    2. If no fist detected → return None (no trim needed)
    3. If fist detected → search backwards for gesture boundary
    4. Find 5 consecutive non-fist frames to establish trim point
    5. Return timestamp of last fist frame + small buffer
    
    Usage:
        detector = GestureDetector()
        trim_time = detector.find_trim_point(video_path)
        if trim_time is not None:
            # Trim video at trim_time seconds
    """
    
    # Detection thresholds
    MIN_DETECTION_CONFIDENCE = 0.5  # Lowered from 0.7 for better detection
    MIN_TRACKING_CONFIDENCE = 0.5
    CONSECUTIVE_NON_FIST_REQUIRED = 5
    FRAME_SAMPLE_INTERVAL_SEC = 0.5
    INITIAL_CHECK_OFFSETS_SEC = [0.1, 0.3, 0.5, 1.0]  # Check closer to end of video
    MIN_VIDEO_DURATION_SEC = 5.0  # Skip very short videos
    TRIM_BUFFER_SEC = 0.1  # Small buffer after last fist frame
    EXTRA_TRIM_FRAMES_30FPS = 5   # Extra frames to remove for videos <= 30fps
    EXTRA_TRIM_FRAMES_HIGH_FPS = 10  # Extra frames to remove for videos > 30fps
    
    def __init__(self):
        """Initialize MediaPipe Hands detector (CPU mode)."""
        if not MEDIAPIPE_AVAILABLE:
            raise ImportError(
                "MediaPipe is not installed. "
                "Install with: pip install mediapipe opencv-python-headless"
            )
        
        self._use_new_api = MEDIAPIPE_NEW_API
        self._model_path = None
        self._hands = None       # For legacy API
        self._landmarker = None  # For new Tasks API (persistent)
        
        if self._use_new_api:
            # Download model for Tasks API
            self._model_path = self._ensure_hand_model()
            # Create HandLandmarker ONCE and reuse across all frames/files.
            # Previously this was created per-frame in a `with` block, adding
            # significant overhead for model loading on every detection call.
            self._landmarker = self._create_hand_landmarker()
            logger.info("✋ GestureDetector initialized (MediaPipe Tasks API, CPU mode)")
        else:
            # Legacy API initialization
            self.mp_hands = mp.solutions.hands
            self._hands = self.mp_hands.Hands(
                static_image_mode=True,
                max_num_hands=2,
                min_detection_confidence=self.MIN_DETECTION_CONFIDENCE,
                min_tracking_confidence=self.MIN_TRACKING_CONFIDENCE
            )
            logger.info("✋ GestureDetector initialized (MediaPipe Legacy API, CPU mode)")
    
    def _create_hand_landmarker(self):
        """Create a persistent HandLandmarker instance for the Tasks API."""
        base_options = mp_python.BaseOptions(model_asset_path=self._model_path)
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=2,
            min_hand_detection_confidence=self.MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=self.MIN_TRACKING_CONFIDENCE
        )
        return mp_vision.HandLandmarker.create_from_options(options)
    
    def _ensure_hand_model(self) -> str:
        """Get the MediaPipe hand landmarker model path (bundled or cached)."""
        # First, check for bundled model (in packaged app)
        bundled_paths = []
        
        # PyInstaller bundled location (use _MEIPASS if available)
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller sets _MEIPASS to the temp extraction directory
            bundled_paths.append(Path(sys._MEIPASS) / "models" / "hand_landmarker.task")
        
        # Also check relative to executable (for onedir mode)
        bundled_paths.append(Path(sys.executable).parent / "_internal" / "models" / "hand_landmarker.task")
        
        # Development location (PROJECT_ROOT/models)
        bundled_paths.append(Path(__file__).parent.parent.parent / "models" / "hand_landmarker.task")
        
        for bundled_path in bundled_paths:
            logger.debug(f"Checking for model at: {bundled_path}")
            if bundled_path.exists():
                logger.info(f"✅ Using bundled hand model: {bundled_path}")
                return str(bundled_path)
        
        # Log all paths we checked
        logger.warning(f"Bundled model not found. Checked: {[str(p) for p in bundled_paths]}")
        
        # Fall back to cached model (download if needed)
        cache_dir = Path.home() / ".cache" / "mediapipe"
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_path = cache_dir / "hand_landmarker.task"
        
        if not model_path.exists():
            model_url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            logger.info(f"📥 Downloading MediaPipe hand model...")
            try:
                urllib.request.urlretrieve(model_url, model_path)
                logger.info(f"✅ Model saved to {model_path}")
            except Exception as e:
                logger.error(f"Failed to download hand model: {e}")
                raise RuntimeError(
                    f"Hand landmarker model not found and download failed. "
                    f"Please manually download from {model_url} to {model_path}"
                )
        
        return str(model_path)
    
    def find_trim_point(self, video_path: Path) -> Optional[float]:
        """
        Analyze video and find the trim point where gesture ends.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Trim timestamp in seconds, or None if no gesture detected
        """
        video_path = Path(video_path)
        
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return None
        
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            logger.error(f"Cannot open video: {video_path}")
            return None
        
        try:
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            
            logger.info(
                f"🔍 Analyzing video: {video_path.name} "
                f"({duration:.1f}s, {fps:.1f}fps, {total_frames} frames)"
            )
            
            # Skip very short videos
            if duration < self.MIN_VIDEO_DURATION_SEC:
                logger.info(f"Video too short ({duration:.1f}s), skipping gesture detection")
                return None
            
            # Step 1: Quick check - look for fist in last 3 frames
            fist_found_in_initial = False
            initial_fist_times = []
            
            for offset in self.INITIAL_CHECK_OFFSETS_SEC:
                check_time = duration - offset
                if check_time < 0:
                    continue
                
                frame = self._extract_frame_at_time(cap, check_time)
                if frame is None:
                    continue
                
                has_fist, hand_count = self._detect_closed_fist(frame)
                logger.debug(
                    f"Frame at {check_time:.1f}s: "
                    f"hands={hand_count}, fist={has_fist}"
                )
                
                if has_fist:
                    fist_found_in_initial = True
                    initial_fist_times.append(check_time)
            
            if not fist_found_in_initial:
                logger.info("✅ No closed fist detected in last 3 seconds - no trim needed")
                return None
            
            logger.info(
                f"✋ Closed fist detected at times: {initial_fist_times} - "
                f"searching for gesture boundary..."
            )
            
            # Step 2: Binary search backwards to find gesture start
            # Start from the earliest fist detection and go back
            search_start = min(initial_fist_times)
            trim_point = self._find_gesture_boundary(cap, search_start, duration)
            
            if trim_point is not None:
                logger.info(f"✂️  Trim point found at {trim_point:.2f}s")
            else:
                # Fist detected but couldn't find clear boundary
                # Use earliest detection minus buffer
                trim_point = search_start - self.TRIM_BUFFER_SEC
                logger.info(f"⚠️  Using fallback trim point at {trim_point:.2f}s")
            
            return trim_point
            
        finally:
            cap.release()
    
    def _find_gesture_boundary(
        self, 
        cap: cv2.VideoCapture, 
        start_time: float,
        video_duration: float
    ) -> Optional[float]:
        """
        Search backwards from start_time to find where gesture begins.
        
        Uses two-phase approach:
        1. Coarse search (0.5s intervals) to find approximate boundary
        2. Fine binary search to find exact frame
        
        Args:
            cap: OpenCV video capture object
            start_time: Time to start searching backwards from
            video_duration: Total video duration
            
        Returns:
            Trim timestamp, or None if boundary not found
        """
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_duration = 1.0 / fps if fps > 0 else 0.0167
        
        # Phase 1: Coarse search to find approximate boundary
        # Find a time range [no_fist_time, fist_time] where transition occurs
        fist_time = start_time
        no_fist_time = None
        
        current_time = start_time
        min_time = max(0, start_time - 30.0)
        
        while current_time > min_time:
            current_time -= self.FRAME_SAMPLE_INTERVAL_SEC
            
            if current_time < 0:
                break
            
            frame = self._extract_frame_at_time(cap, current_time)
            if frame is None:
                continue
            
            has_fist, _ = self._detect_closed_fist(frame)
            
            if has_fist:
                fist_time = current_time
            else:
                no_fist_time = current_time
                break  # Found approximate boundary
        
        if no_fist_time is None:
            # Fist present for entire search - trim at earliest fist
            logger.debug(f"Fist present for entire search range, trimming at {fist_time:.3f}s")
            return fist_time
        
        logger.debug(f"Coarse boundary: no_fist={no_fist_time:.3f}s, fist={fist_time:.3f}s")
        
        # Phase 2: Binary search for frame-precise boundary
        # Search between no_fist_time and fist_time
        low_time = no_fist_time
        high_time = fist_time
        
        # Binary search until we're within 1 frame
        while (high_time - low_time) > frame_duration * 1.5:
            mid_time = (low_time + high_time) / 2
            
            frame = self._extract_frame_at_time(cap, mid_time)
            if frame is None:
                # Can't read frame, narrow from high side
                high_time = mid_time
                continue
            
            has_fist, _ = self._detect_closed_fist(frame)
            
            if has_fist:
                high_time = mid_time
            else:
                low_time = mid_time
        
        # high_time is now the first fist frame (within 1-2 frames)
        # Trim point should be just before the fist appears, minus extra buffer frames
        # Use more frames for high FPS videos (>30fps)
        extra_frames = self.EXTRA_TRIM_FRAMES_HIGH_FPS if fps > 30 else self.EXTRA_TRIM_FRAMES_30FPS
        extra_buffer = extra_frames * frame_duration
        trim_point = high_time - frame_duration - extra_buffer
        
        logger.debug(
            f"Binary search complete: first_fist={high_time:.3f}s, "
            f"trim_point={trim_point:.3f}s (includes {extra_frames} extra frames for {fps:.1f}fps)"
        )
        
        return trim_point
    
    def _detect_closed_fist(self, frame: np.ndarray) -> Tuple[bool, int]:
        """
        Detect if any hand in the frame is showing a closed fist.
        
        Args:
            frame: RGB image as numpy array
            
        Returns:
            Tuple of (is_closed_fist, num_hands_detected)
        """
        if self._use_new_api:
            return self._detect_closed_fist_new_api(frame)
        else:
            return self._detect_closed_fist_legacy(frame)
    
    def _detect_closed_fist_new_api(self, frame: np.ndarray) -> Tuple[bool, int]:
        """Detect closed fist using MediaPipe Tasks API (0.10.x+).
        
        Uses the persistent HandLandmarker created in __init__ to avoid
        the cost of model loading on every frame.
        """
        try:
            if self._landmarker is None:
                return False, 0
            
            # Convert numpy array to MediaPipe Image
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            
            # Detect hands using persistent landmarker
            result = self._landmarker.detect(mp_image)
            
            if not result.hand_landmarks:
                return False, 0
            
            num_hands = len(result.hand_landmarks)
            
            # Check each hand for closed fist
            for landmarks in result.hand_landmarks:
                if self._is_closed_fist_from_landmarks(landmarks):
                    return True, num_hands
            
            return False, num_hands
                
        except Exception as e:
            logger.warning(f"Hand detection failed: {e}")
            return False, 0
    
    def _detect_closed_fist_legacy(self, frame: np.ndarray) -> Tuple[bool, int]:
        """Detect closed fist using legacy MediaPipe API."""
        results = self._hands.process(frame)
        
        if not results.multi_hand_landmarks:
            return False, 0
        
        num_hands = len(results.multi_hand_landmarks)
        
        for hand_landmarks in results.multi_hand_landmarks:
            if self._is_closed_fist(hand_landmarks):
                return True, num_hands
        
        return False, num_hands
    
    def _is_closed_fist_from_landmarks(self, landmarks) -> bool:
        """
        Determine if hand landmarks represent a closed fist (Tasks API).
        
        Args:
            landmarks: List of NormalizedLandmark objects from Tasks API
            
        Returns:
            True if hand is a closed fist
        """
        # Landmark indices (same as legacy)
        fingertip_ids = [8, 12, 16, 20]  # Index, Middle, Ring, Pinky tips
        mcp_ids = [5, 9, 13, 17]         # Corresponding MCP joints
        
        curled_count = 0
        for tip_id, mcp_id in zip(fingertip_ids, mcp_ids):
            tip_y = landmarks[tip_id].y
            mcp_y = landmarks[mcp_id].y
            
            # Fingertip below MCP means finger is curled
            if tip_y > mcp_y:
                curled_count += 1
        
        # Thumb check
        thumb_tip = landmarks[4]
        index_mcp = landmarks[5]
        thumb_ip = landmarks[3]
        
        thumb_horizontal_dist = abs(thumb_tip.x - index_mcp.x)
        thumb_tucked = thumb_horizontal_dist < 0.12
        thumb_curled = thumb_tip.y > thumb_ip.y
        
        is_fist = curled_count >= 4 and (thumb_tucked or thumb_curled)
        
        if is_fist:
            logger.debug(
                f"Closed fist detected: curled={curled_count}/4, "
                f"thumb_tucked={thumb_tucked}, thumb_curled={thumb_curled}"
            )
        
        return is_fist
    
    def _is_closed_fist(self, hand_landmarks) -> bool:
        """
        Determine if hand landmarks represent a closed fist (Legacy API).
        
        A closed fist is detected when:
        - All 4 fingertips (index, middle, ring, pinky) are below their MCP joints
        - Thumb tip is close to the palm (tucked in)
        
        MediaPipe Hand Landmarks:
        - 0: WRIST
        - 4: THUMB_TIP
        - 8: INDEX_FINGER_TIP  
        - 12: MIDDLE_FINGER_TIP
        - 16: RING_FINGER_TIP
        - 20: PINKY_TIP
        - 5, 9, 13, 17: MCP joints (knuckles)
        
        Args:
            hand_landmarks: MediaPipe hand landmarks (legacy format)
            
        Returns:
            True if hand is a closed fist
        """
        landmarks = hand_landmarks.landmark
        
        fingertip_ids = [8, 12, 16, 20]
        mcp_ids = [5, 9, 13, 17]
        
        curled_count = 0
        for tip_id, mcp_id in zip(fingertip_ids, mcp_ids):
            tip_y = landmarks[tip_id].y
            mcp_y = landmarks[mcp_id].y
            
            if tip_y > mcp_y:
                curled_count += 1
        
        thumb_tip = landmarks[4]
        index_mcp = landmarks[5]
        thumb_ip = landmarks[3]
        
        thumb_horizontal_dist = abs(thumb_tip.x - index_mcp.x)
        thumb_tucked = thumb_horizontal_dist < 0.12
        thumb_curled = thumb_tip.y > thumb_ip.y
        
        is_fist = curled_count >= 4 and (thumb_tucked or thumb_curled)
        
        if is_fist:
            logger.debug(
                f"Closed fist detected: curled={curled_count}/4, "
                f"thumb_tucked={thumb_tucked}, thumb_curled={thumb_curled}"
            )
        
        return is_fist
    
    def _extract_frame_at_time(
        self, 
        cap: cv2.VideoCapture, 
        time_sec: float
    ) -> Optional[np.ndarray]:
        """
        Extract a single frame at the specified timestamp.
        
        Args:
            cap: OpenCV video capture object
            time_sec: Time in seconds
            
        Returns:
            RGB frame as numpy array, or None if extraction fails
        """
        # Seek to position
        cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000)
        
        ret, frame = cap.read()
        if not ret or frame is None:
            logger.warning(f"Failed to extract frame at {time_sec:.2f}s")
            return None
        
        # Convert BGR (OpenCV default) to RGB (MediaPipe expects)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    def close(self):
        """Explicitly release MediaPipe resources."""
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None
        if self._hands is not None:
            try:
                self._hands.close()
            except Exception:
                pass
            self._hands = None

    def __del__(self):
        """Clean up MediaPipe resources."""
        self.close()


# Module-level singleton — avoids re-creating the MediaPipe HandLandmarker
# and re-searching for the model file on every video processed.
_detector_instance: Optional[GestureDetector] = None


def _get_detector() -> Optional[GestureDetector]:
    """Get or create the singleton GestureDetector instance."""
    global _detector_instance
    if _detector_instance is None:
        try:
            _detector_instance = GestureDetector()
        except ImportError as e:
            logger.warning(f"Gesture detection unavailable: {e}")
            return None
    return _detector_instance


def detect_gesture_trim_point(video_path: str) -> Optional[float]:
    """
    Convenience function to detect gesture trim point.
    
    Uses a module-level singleton GestureDetector to avoid the cost
    of re-initializing MediaPipe and re-loading the hand model on
    every file.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Trim timestamp in seconds, or None if no gesture detected
    """
    try:
        detector = _get_detector()
        if detector is None:
            return None
        return detector.find_trim_point(Path(video_path))
    except Exception as e:
        logger.error(f"Gesture detection failed: {e}", exc_info=True)
        return None
