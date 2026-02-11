"""
Analysis Worker - LLM-based content analysis

This worker uses Qwen 2.5 3B to analyze transcripts and extract metadata.
Only included when BUILD_WITH_AI is enabled.

Memory Management:
- Model is unloaded after each job to free GPU memory
- Memory is checked before starting new jobs
- Transcripts are truncated to prevent OOM
- Garbage collection is run aggressively
"""
import asyncio
import json
import logging
import os
import time
import re
import gc
import psutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from models import File, Job, Event, Setting
from models_analytics import FileAnalytics
from workers.base_worker import WorkerBase
from services.websocket import manager as websocket_manager
from services.worker_status_service import worker_status_service

try:
    from mlx_vlm import load, generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
    import mlx.core as mx  # For Metal cache clearing
    MLX_VLM_AVAILABLE = True
    logging.info("✅ mlx-vlm imported successfully - vision analysis enabled")
except ImportError as e:
    MLX_VLM_AVAILABLE = False
    mx = None  # Set to None so we can check later
    logging.error(f"❌ mlx-vlm not available - vision analysis DISABLED: {e}")
    import sys
    logging.error(f"   Python: {sys.executable}")
    logging.error(f"   sys.path: {sys.path[:3]}")

# mlx_lm kept for version logging only - NOT used as fallback (image analysis is required)
try:
    import mlx_lm
    logging.info("✅ mlx-lm available (for reference only - VLM is required)")
except ImportError as e:
    mlx_lm = None
    logging.warning(f"⚠️ mlx-lm not available: {e}")

# Log versions for debugging
try:
    import transformers
    import mlx_vlm
    logging.warning(f"📦 Versions - mlx-vlm: {getattr(mlx_vlm, '__version__', 'unknown')}, "
                    f"transformers: {getattr(transformers, '__version__', 'unknown')}, "
                    f"mlx-lm: {getattr(mlx_lm, '__version__', 'unknown') if mlx_lm else 'not installed'}")
except ImportError:
    logging.warning("⚠️ Could not import one or more AI libraries for version checking")

# PIL is already included in mlx-vlm dependencies
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("⚠️ PIL/Pillow not available - image analysis disabled")

logger = logging.getLogger(__name__)

from services.ai_mutex import gpu_lock, shutting_down

# Dedicated single-thread executor for MLX VLM to control lifecycle and avoid DefaultExecutor reuse edge cases
_VLM_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx_vlm")

# Memory management constants - macOS can swap to SSD so we can be lenient
MAX_MEMORY_PERCENT_FOR_ANALYSIS = 95  # Only skip if memory is critically high
MAX_TRANSCRIPT_LENGTH = 3000  # Truncate transcripts to this length to save memory
MEMORY_WARNING_THRESHOLD = 85  # Log warning above this level

# OOM error patterns to detect
OOM_ERROR_PATTERNS = [
    'kIOGPUCommandBufferCallbackErrorOutOfMemory',
    'out of memory',
    'OutOfMemory',
    'memory allocation failed',
    'Cannot allocate memory',
    'Metal buffer allocation failed',
]


def check_memory_available() -> tuple[bool, float]:
    """
    Check if there's enough memory available to run analysis.
    macOS can swap to SSD efficiently, so we're lenient with memory.
    
    Returns:
        Tuple of (is_available, current_percent)
    """
    memory_percent = psutil.virtual_memory().percent
    if memory_percent > MEMORY_WARNING_THRESHOLD:
        logger.warning(f"⚠️ Memory usage high: {memory_percent:.1f}%")
    return memory_percent < MAX_MEMORY_PERCENT_FOR_ANALYSIS, memory_percent


def is_oom_error(error: Exception) -> bool:
    """
    Check if an exception is an out-of-memory error.
    
    Args:
        error: The exception to check
        
    Returns:
        True if this looks like an OOM error
    """
    error_str = str(error).lower()
    return any(pattern.lower() in error_str for pattern in OOM_ERROR_PATTERNS)


def cleanup_memory():
    """Force garbage collection to free memory."""
    gc.collect()
    # Try to clear any MLX caches if available
    try:
        import mlx.core as mx
        mx.metal.clear_cache()
        logger.info("🧹 Cleared MLX metal cache")
    except Exception:
        pass


class AnalyzeWorker(WorkerBase):
    """
    Worker that analyzes transcripts and images using Qwen3-VL (MLX optimized).

    IMPORTANT: This worker REQUIRES a Vision Language Model (VLM) for image analysis.
    Text-only fallback is NOT supported - image analysis is critical for content
    categorization and description.

    Memory Management:
    - Checks memory before starting each job
    - Unloads model after each job
    - Truncates long transcripts
    - Runs garbage collection aggressively

    Process:
    1. Load transcript from FileAnalytics
    2. Load thumbnail image for visual analysis
    3. Run VLM analysis to extract metadata from both text and image
    4. Parse JSON response and populate CSV fields
    5. Mark analytics as COMPLETED
    6. Trigger CSV export update

    Job Flow:
    ANALYZE job (state=QUEUED) → ANALYZING → COMPLETED
    """

    # Model path will be determined at runtime from config or environment
    MODEL_NAME = None  # Set during initialization
    
    # Analysis prompt template
    ANALYSIS_PROMPT = """<|im_start|>system
You are a JSON-only response assistant. You must respond ONLY with valid JSON, no other text.<|im_end|>
<|im_start|>user
Analyze this video transcript and return ONLY valid JSON (no other text):

Transcript: {transcript}

Filename: {filename}
Duration: {duration}s
Date: {recording_date}

Return this exact JSON structure:
{{
    "video_title": "descriptive title",
    "short_description": "2-3 sentence summary",
    "content_type": "Promotional/Learning Content/Lecture/Tutorial/Presentation/Discussion/Other",
    "faculty": "Sciences/Mathematics/Humanities/Arts/Languages/Technology/General",
    "audience_type": ["Student", "Staff", "Parent"],
    "speaker_type": ["Staff", "Student"],
    "speaker_confidence": {{"Staff": 0.8, "Student": 0.2}},
    "rationale_short": "why you categorized this way",
    "image_description": "description of the visual content",
    "language": "English",
    "speaker_count": 1
}}

Rules:
- Output ONLY JSON, nothing else
- speaker_confidence must sum to 1.0
- Arrays must use brackets []
<|im_end|>
<|im_start|>assistant
"""
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.model = None
        self.processor = None  # mlx-vlm uses processor
        self.config = None
        self.model_path = self._get_model_path()

    def _unload_model(self):
        """Unload the model to free memory."""
        if self.model is not None:
            logger.info("🧹 Unloading VLM model to free memory...")
            self.model = None
            self.processor = None
            self.config = None
            cleanup_memory()
            logger.info("🧹 Model unloaded and memory cleaned")

    async def run_once(self):
        """Run a single iteration - check for ANALYZE job and process if found"""
        try:
            # Check memory availability - but be lenient, macOS handles high memory well
            memory_ok, memory_percent = check_memory_available()
            if not memory_ok:
                logger.warning(f"⚠️ Memory critically high ({memory_percent:.1f}%) - waiting briefly before trying")
                # Try to free memory first
                cleanup_memory()
                await asyncio.sleep(5)  # Short wait, then try anyway
                # Re-check, but proceed regardless (let macOS swap handle it)
                _, new_percent = check_memory_available()
                logger.info(f"💾 Memory after cleanup: {new_percent:.1f}% - proceeding with job")

            # Query for highest priority ANALYZE job
            job = self.db.query(Job).filter(
                Job.kind == 'ANALYZE',
                Job.state == 'QUEUED'
            ).order_by(Job.priority.desc(), Job.created_at).first()

            if not job:
                await asyncio.sleep(1)
                return

            # Check analytics pause and idle settings (only for automatic jobs)
            # Manual jobs (priority >= 1000) always run regardless of these settings
            from constants import SettingKeys

            is_manual_job = job.priority >= 1000

            if not is_manual_job:
                # Get both settings
                pause_setting = self.db.query(Setting).filter(
                    Setting.key == SettingKeys.PAUSE_ANALYTICS
                ).first()

                idle_setting = self.db.query(Setting).filter(
                    Setting.key == SettingKeys.RUN_ANALYTICS_WHEN_IDLE
                ).first()

                is_paused = pause_setting and pause_setting.value == 'true'
                run_when_idle = idle_setting and idle_setting.value == 'true'

                # Combine the checks: if paused but idle-mode enabled, check pipeline status
                if is_paused:
                    if run_when_idle:
                        # Check if pipeline is actually idle - if so, allow job to run
                        pipeline_jobs_running = self.db.query(Job).filter(
                            Job.kind.in_(['COPY', 'PROCESS', 'ORGANIZE']),
                            Job.state == 'RUNNING'
                        ).count()

                        if pipeline_jobs_running > 0:
                            # Pipeline is active - skip this automatic analytics job
                            await asyncio.sleep(1)
                            return
                        # Pipeline is idle - continue to process job
                    else:
                        # Paused without idle-mode - skip this automatic job
                        await asyncio.sleep(1)
                        return

                elif run_when_idle:
                    # Not paused, but idle-mode is enabled - check pipeline
                    pipeline_jobs_running = self.db.query(Job).filter(
                        Job.kind.in_(['COPY', 'PROCESS', 'ORGANIZE']),
                        Job.state == 'RUNNING'
                    ).count()

                    if pipeline_jobs_running > 0:
                        # Pipeline is active - skip this automatic analytics job
                        await asyncio.sleep(1)
                        return

            # Process the job (either not paused, manual job, or pipeline is idle)
            await self.process_job(job)

        except ValueError as e:
            # ValueError indicates a permanent failure (e.g., missing transcript)
            # Fail the job so it doesn't block other jobs
            error_msg = str(e)
            logger.error(f"Permanent error for ANALYZE job {job.id}: {error_msg}")

            try:
                job.state = 'FAILED'
                job.error_message = error_msg

                # Also update FileAnalytics state
                file = job.file
                analytics = self._get_analytics(file)
                if analytics:
                    analytics.state = 'FAILED'
                    analytics.error_message = error_msg

                self.db.commit()

                # Update worker status
                await worker_status_service.update_worker_status(
                    'analyze',
                    state='IDLE',
                    error_message=None
                )
            except Exception as cleanup_error:
                logger.error(f"Error failing job: {cleanup_error}", exc_info=True)
                self.db.rollback()

            # Don't sleep - immediately try next job
            return

        except Exception as e:
            # Unexpected errors - log and sleep before retry
            logger.error(f"Error in analyze worker run_once: {e}", exc_info=True)
            await asyncio.sleep(5)

    async def process_job(self, job: Job) -> None:
        """
        Analyze a transcript using LLM.
        
        Args:
            job: ANALYZE job with associated file
            
        Raises:
            Exception: If analysis fails
        """
        if not MLX_VLM_AVAILABLE:
            raise RuntimeError("MLX VLM not available")
        
        file = job.file
        analytics = self._get_analytics(file)
        
        if not analytics:
            raise ValueError(f"No analytics record found for file {file.id}")
        
        if not analytics.transcript:
            raise ValueError(f"No transcript available for file {file.id}")
        
        try:
            # Update state
            analytics.state = 'ANALYZING'
            analytics.analysis_started_at = datetime.utcnow()
            job.state = 'RUNNING'
            self.db.commit()

            # Update worker status
            await worker_status_service.update_worker_status(
                'analyze',
                state='ACTIVE',
                job=job,
                file=file,
                detail='Analyzing with LLM',
                wait_reason='MLX VLM inference',
                gpu_lock_held=True
            )

            logger.warning(f"📊 Starting analysis for {file.filename}")
            await websocket_manager.send_analytics_state(file.id, file.filename, 'ANALYZING')
            
            # Check for cancellation
            if await self.check_cancellation(job):
                return
            
            # Lazy load model
            if not self.model:
                await self._load_model()
            
            # Run LLM analysis
            raw_response, llm_stats = await self._analyze_transcript(
                analytics.transcript,
                file,
                job
            )

            # Parse JSON response and save structured fields
            # Wrap in try/except to handle malformed model output gracefully
            try:
                analysis = self._parse_json_response(raw_response)
                # Validate that we got a proper dict, not a partial/malformed result
                if not isinstance(analysis, dict):
                    logger.warning(f"⚠️ parse_json_response returned non-dict: {type(analysis)}")
                    analysis = self._default_analysis()
            except Exception as parse_error:
                logger.warning(f"⚠️ JSON parsing failed with error: {parse_error}")
                logger.warning(f"   Raw response was: {raw_response[:500] if raw_response else 'EMPTY'}...")
                analysis = self._default_analysis()
            
            # Save results (with its own error handling)
            try:
                self._save_analysis_results(analytics, analysis, file)
            except Exception as save_error:
                logger.warning(f"⚠️ Save analysis failed: {save_error}, using defaults")
                # Try saving with defaults
                self._save_analysis_results(analytics, self._default_analysis(), file)

            # Save LLM statistics
            analytics.llm_prompt_tokens = llm_stats.get('prompt_tokens')
            analytics.llm_completion_tokens = llm_stats.get('completion_tokens')
            analytics.llm_total_tokens = llm_stats.get('total_tokens')
            analytics.llm_peak_memory_mb = llm_stats.get('peak_memory_mb')

            analytics.state = 'COMPLETED'
            analytics.analysis_completed_at = datetime.utcnow()

            # Calculate duration
            if analytics.analysis_started_at:
                duration = (analytics.analysis_completed_at - analytics.analysis_started_at).total_seconds()
                analytics.analysis_duration_seconds = int(duration)

            job.state = 'DONE'
            job.completed_at = datetime.utcnow()
            self.db.commit()

            logger.warning(f"✅ Analysis complete for {file.filename}")
            logger.warning(f"📝 Parsed and saved structured analysis data")

            # Broadcast completion
            await websocket_manager.send_analytics_state(file.id, file.filename, 'COMPLETED', {
                'title': analytics.title
            })

            # Clear worker status
            await worker_status_service.clear_worker_status('analyze')

        except Exception as e:
            error_str = str(e)
            # Handle malformed model output - recover with defaults instead of failing
            # The error often looks like: '\n"image_description' or similar partial JSON
            is_malformed_output = (
                'image_description' in error_str or 
                '"image_description' in error_str or
                error_str.strip().startswith("'\\n") or
                error_str.strip().startswith("'\"") or
                (len(error_str) < 100 and '{' not in error_str and 'Error' not in error_str)
            )
            
            if is_malformed_output:
                logger.warning(f"⚠️ Caught malformed model output exception: {repr(e)}")
                logger.warning("🔄 Attempting recovery with default analysis values...")
                
                try:
                    # Try to complete with default values instead of failing
                    self._save_analysis_results(analytics, self._default_analysis(), file)
                    
                    analytics.state = 'COMPLETED'
                    analytics.analysis_completed_at = datetime.utcnow()
                    analytics.error_message = "Recovered with defaults - model output was malformed"
                    
                    if analytics.analysis_started_at:
                        duration = (analytics.analysis_completed_at - analytics.analysis_started_at).total_seconds()
                        analytics.analysis_duration_seconds = int(duration)
                    
                    job.state = 'DONE'
                    job.completed_at = datetime.utcnow()
                    self.db.commit()
                    
                    logger.warning(f"✅ Analysis recovered with defaults for {file.filename}")
                    await websocket_manager.send_analytics_state(file.id, file.filename, 'COMPLETED', {
                        'title': analytics.title
                    })
                    await worker_status_service.clear_worker_status('analyze')
                    return  # Success with defaults, don't fail the job
                    
                except Exception as recovery_error:
                    logger.error(f"❌ Recovery failed: {recovery_error}")
                    # Fall through to normal failure handling
            
            # Check if this is an out-of-memory error
            if is_oom_error(e):
                logger.error(f"💾 OUT OF MEMORY during analysis for {file.filename}")
                logger.error(f"   Error: {error_str[:200]}")
                
                # Aggressive cleanup
                self._unload_model()
                cleanup_memory()
                
                # Set state to allow retry - don't mark as permanently failed
                analytics.state = 'TRANSCRIBED'  # Allow re-analysis
                analytics.error_message = "Out of memory - close other apps and try again"
                analytics.retry_count += 1
                
                # Reset the job so it can be retried
                job.state = 'QUEUED'
                job.started_at = None
                self.db.commit()
                
                # Notify GUI with retry option
                await websocket_manager.send_analytics_state(file.id, file.filename, 'OOM_ERROR', {
                    'error': 'Out of memory',
                    'message': 'System ran out of memory during analysis. Close other applications and try again.',
                    'can_retry': True,
                    'retry_count': analytics.retry_count
                })
                
                # Send error notification
                await websocket_manager.send_error(
                    'analysis_oom',
                    f'Out of memory analyzing "{file.filename}". Close other apps and retry.',
                    {'file_id': file.id, 'filename': file.filename, 'can_retry': True}
                )
                
                await worker_status_service.update_worker_status(
                    'analyze',
                    state='IDLE',
                    error_message='OOM - waiting for retry'
                )
                return  # Don't fall through to generic error handling
            
            logger.error(f"❌ Analysis failed for {file.filename}: {e}")
            analytics.state = 'FAILED' if analytics.retry_count >= 1 else 'TRANSCRIBED'
            analytics.error_message = str(e)

            await self.handle_failure_with_reset(job, e)

            # Update analytics with error
            analytics.retry_count += 1
            self.db.commit()

            # Update worker status with error
            await worker_status_service.update_worker_status(
                'analyze',
                state='ERROR',
                error_message=analytics.error_message
            )
        finally:
            # Always unload model after job to free memory
            self._unload_model()
    
    def _get_analytics(self, file: File) -> FileAnalytics:
        """Get FileAnalytics record for file"""
        return self.db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file.id
        ).first()

    def _get_model_path(self) -> str:
        """
        Determine the LLM model path from configuration or environment.

        Checks in this order:
        1. Database setting 'ai_llm_model_path'
        2. Environment variable 'LLM_MODEL_PATH'
        3. config.ai_config.get_model_path('llm')
        4. LM Studio default path (for development)

        Returns:
            Path to LLM model
        """
        import os
        from pathlib import Path

        # Check database setting
        llm_path_setting = self.db.query(Setting).filter(
            Setting.key == 'ai_llm_model_path'
        ).first()

        if llm_path_setting and llm_path_setting.value:
            logger.info(f"📂 Using LLM model path from database: {llm_path_setting.value}")
            return llm_path_setting.value

        # Check environment variable
        env_path = os.environ.get('LLM_MODEL_PATH')
        if env_path:
            logger.info(f"📂 Using LLM model path from environment: {env_path}")
            return env_path

        # Try config's get_model_path (looks in bundled models/)
        try:
            from config.ai_config import get_model_path
            config_path = get_model_path('llm')
            logger.info(f"📂 Using LLM model path from config: {config_path}")
            return config_path
        except Exception as e:
            logger.warning(f"Could not get model path from config: {e}")

        # Fall back to LM Studio default (for development)
        lm_studio_path = Path.home() / ".lmstudio" / "models" / "lmstudio-community"
        if lm_studio_path.exists():
            # Find the first Qwen model
            for model_dir in lm_studio_path.iterdir():
                if model_dir.is_dir() and 'Qwen' in model_dir.name:
                    logger.info(f"📂 Using LM Studio model: {model_dir}")
                    return str(model_dir)

        # Last resort: error
        raise RuntimeError(
            "No LLM model path configured. Please set:\n"
            "  - Database setting 'ai_llm_model_path', or\n"
            "  - Environment variable LLM_MODEL_PATH, or\n"
            "  - Place models in models/llm/ directory"
        )

    async def _load_model(self):
        """Lazy load the VLM or LM model"""
        logger.warning(f"🤖 Loading model from {self.model_path}")

        loop = asyncio.get_event_loop()
        # Serialize model load to avoid concurrent MLX/Metal init with other workers
        if gpu_lock.locked():
            logger.warning("⏳ GPU lock busy during model load - waiting")
        load_wait_start = time.time()
        if shutting_down.is_set():
            raise RuntimeError("Shutting down - skipping model load")
            
        async with gpu_lock:
            waited_ms = int((time.time() - load_wait_start) * 1000)
            if waited_ms > 0:
                logger.warning(f"🔒 Acquired GPU lock for model load after {waited_ms}ms")
            else:
                logger.warning("🔒 Acquired GPU lock for model load immediately")
                logger.warning("🔒 Acquired GPU lock immediately")
            
            # Try loading as VLM first
            try:
                logger.info("🤖 Attempting to load as VLM...")
                # mlx-vlm returns (model, processor)
                self.model, self.processor = await loop.run_in_executor(
                    _VLM_EXECUTOR,
                    load,
                    self.model_path
                )
                self.config = self.model.config
                self.is_vlm = True
                logger.warning("✅ VLM model loaded successfully")
            except Exception as e:
                # VLM is required for image analysis - do NOT fallback to text-only
                logger.error(f"❌ VLM load failed: {e}")
                logger.error("❌ Image analysis requires a working VLM model. Text-only fallback is disabled.")
                logger.error(f"❌ Model path: {self.model_path}")
                logger.error("❌ Please ensure mlx-vlm is properly installed and the model is compatible.")
                raise RuntimeError(f"VLM model load failed - image analysis unavailable: {e}")
    
    async def _analyze_transcript(self, transcript: str, file: File, job: Job) -> dict:
        """
        Run VLM analysis on transcript using mlx-vlm.

        Args:
            transcript: Video transcript text
            file: File being analyzed
            job: Job for cancellation checking

        Returns:
            Raw LLM response text
        """
        # Get system and user prompts from AIConfigService
        try:
            from services.ai_config_service import AIConfigService
            ai_config = AIConfigService(self.db)

            logger.warning("📝 Getting prompts from AIConfigService...")
            system_prompt = ai_config.get_system_prompt()
            user_prompt_template = ai_config.get_user_prompt()
            logger.warning(f"📝 Got system prompt ({len(system_prompt)} chars) and user prompt template ({len(user_prompt_template)} chars)")
            
            # Validate that the prompt template is not corrupted
            # A valid template should contain {transcript} and {filename} placeholders
            # and should NOT contain things like "image_description": which would be model output
            if '{transcript}' not in user_prompt_template or '"image_description"' in user_prompt_template:
                logger.warning("⚠️ User prompt template appears corrupted (contains model output), resetting to default...")
                user_prompt_template = ai_config.DEFAULT_USER_PROMPT
                # Also save the fix to database
                ai_config.save_user_prompt(user_prompt_template)
                logger.warning("✅ Reset user prompt template to default")
                
        except Exception as config_error:
            logger.error(f"❌ Failed to get prompts from AIConfigService: {config_error}")
            raise

        # Truncate transcript if too long to save memory (use constant)
        if len(transcript) > MAX_TRANSCRIPT_LENGTH:
            transcript_sample = transcript[:MAX_TRANSCRIPT_LENGTH] + "\n\n[Transcript truncated for analysis...]"
        else:
            transcript_sample = transcript

        # Format user prompt with placeholders
        try:
            user_prompt = user_prompt_template.format(
                transcript=transcript_sample,
                filename=file.filename,
                duration=file.duration or 0,
                recording_date=file.session.recording_date if file.session else 'Unknown'
            )
            logger.warning(f"📝 Formatted user prompt ({len(user_prompt)} chars)")
        except KeyError as key_error:
            # This happens when the template has invalid placeholders (e.g., corrupted by model output)
            logger.error(f"❌ User prompt template has invalid placeholder: {key_error}")
            logger.warning("🔄 Resetting to default prompt template...")
            from services.ai_config_service import AIConfigService
            user_prompt_template = AIConfigService.DEFAULT_USER_PROMPT
            user_prompt = user_prompt_template.format(
                transcript=transcript_sample,
                filename=file.filename,
                duration=file.duration or 0,
                recording_date=file.session.recording_date if file.session else 'Unknown'
            )
            logger.warning(f"📝 Formatted user prompt with default template ({len(user_prompt)} chars)")
        except Exception as format_error:
            logger.error(f"❌ Failed to format user prompt: {format_error}")
            raise

        # Combine system and user prompts for mlx-vlm
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # Find thumbnail image
        thumbnail_path = self._find_thumbnail(file)

        # Prepare image list for mlx-vlm
        images = []
        if thumbnail_path and thumbnail_path.exists():
            logger.info(f"📷 Found thumbnail: {thumbnail_path}")
            images = [str(thumbnail_path)]
        else:
            logger.warning(f"⚠️  No thumbnail found for {file.filename}")

        logger.warning(f"📝 Using VLM with prompt ({len(full_prompt)} chars) and {len(images)} image(s)")
        logger.warning(f"⚡ About to call _generate_sync")

        # Abort early if app is shutting down
        if shutting_down.is_set():
            raise RuntimeError("Shutting down - skipping VLM generation")

        # Run generation in thread pool but ensure single-flight access to GPU/Metal (shared across workers)
        loop = asyncio.get_event_loop()
        if gpu_lock.locked():
            logger.warning("⏳ GPU lock busy - waiting for current Metal/MLX task to finish")

        wait_start = time.time()
        async with gpu_lock:
            waited_ms = int((time.time() - wait_start) * 1000)
            if waited_ms > 0:
                logger.warning(f"🔒 Acquired GPU lock after {waited_ms}ms")
            else:
                logger.warning("🔒 Acquired GPU lock immediately")
            result = await loop.run_in_executor(
                _VLM_EXECUTOR,
                self._generate_sync,
                full_prompt,
                images
            )
        logger.warning("🔓 Released GPU lock")

        # Unpack result
        response_text, llm_stats = result

        logger.warning(f"⚡ _generate_sync returned: {len(response_text) if response_text else 0} chars")

        # Return both response and stats
        return response_text, llm_stats

    def _find_thumbnail(self, file: File) -> 'Path':
        """
        Find thumbnail image for the file.

        Args:
            file: File record

        Returns:
            Path to thumbnail image, or None if not found
        """
        from pathlib import Path
        from models import Setting

        logger.warning(f"🔍 Looking for thumbnail for {file.filename} (file_id: {file.id})")

        # Method 1: Check the configured thumbnail folder from dev_queue settings
        # Thumbnails are stored as {file_id}.jpg
        thumbnail_folder_setting = self.db.query(Setting).filter(
            Setting.key == 'dev_queue_thumbnail_folder'
        ).first()
        
        if thumbnail_folder_setting and thumbnail_folder_setting.value:
            thumbnail_folder = Path(thumbnail_folder_setting.value)
            logger.warning(f"   Checking thumbnail folder: {thumbnail_folder}")
            if thumbnail_folder.exists():
                # Look for thumbnail named by file_id
                thumbnail_path = thumbnail_folder / f"{file.id}.jpg"
                logger.warning(f"   Looking for: {thumbnail_path}")
                if thumbnail_path.exists():
                    logger.warning(f"   ✅ Found thumbnail: {thumbnail_path}")
                    return thumbnail_path
                
                # Also try .jpeg extension
                thumbnail_path_jpeg = thumbnail_folder / f"{file.id}.jpeg"
                if thumbnail_path_jpeg.exists():
                    logger.warning(f"   ✅ Found thumbnail: {thumbnail_path_jpeg}")
                    return thumbnail_path_jpeg

        # Method 2: Check file's external_export_path (legacy method)
        logger.warning(f"   external_export_path: {file.external_export_path}")
        if file.external_export_path:
            cache_dir = Path(file.external_export_path)
            logger.warning(f"   cache_dir exists: {cache_dir.exists()}")
            if cache_dir.exists():
                # Look for JPG files
                jpg_files = list(cache_dir.glob('*.jpg'))
                logger.warning(f"   Found {len(jpg_files)} .jpg files")
                if jpg_files:
                    logger.warning(f"   ✅ Returning: {jpg_files[0]}")
                    return jpg_files[0]

                # Also check for JPEG extension
                jpeg_files = list(cache_dir.glob('*.jpeg'))
                logger.warning(f"   Found {len(jpeg_files)} .jpeg files")
                if jpeg_files:
                    return jpeg_files[0]

        # Method 3: Check the default StudioPipeline thumbnails folder
        default_thumbnail_folder = Path.home() / "Library/Application Support/StudioPipeline/thumbnails"
        if default_thumbnail_folder.exists():
            thumbnail_path = default_thumbnail_folder / f"{file.id}.jpg"
            logger.warning(f"   Checking default folder: {thumbnail_path}")
            if thumbnail_path.exists():
                logger.warning(f"   ✅ Found thumbnail in default folder: {thumbnail_path}")
                return thumbnail_path

        logger.warning(f"   ❌ No thumbnail found for {file.filename}")
        return None
    
    def _generate_sync(self, prompt: str, images: list = None) -> tuple:
        """
        Synchronous generation using mlx-vlm or mlx-lm (runs in thread pool).

        Args:
            prompt: Analysis prompt
            images: List of image paths for vision models
        
        Returns:
            Tuple of (generated_text, stats_dict)
        """
        import psutil
        import os
        import gc

        try:
            logger.warning(f"🤖 Running VLM generation with prompt length: {len(prompt)} chars")
            
            if images:
                logger.warning(f"📷 Including {len(images)} image(s): {images}")
            else:
                logger.warning("⚠️ No images provided for VLM analysis - proceeding with text-only prompt")

            # Track memory before generation
            process = psutil.Process(os.getpid())
            memory_before_mb = process.memory_info().rss / 1024 / 1024
            memory_percent = psutil.virtual_memory().percent
            logger.warning(f"💾 Memory before generation: {memory_before_mb:.0f}MB ({memory_percent:.1f}% system)")
            
            # If memory is high, try to free some before generation
            if memory_percent > 85:
                logger.warning("⚠️ High memory usage detected, running garbage collection...")
                gc.collect()
                memory_percent_after_gc = psutil.virtual_memory().percent
                logger.warning(f"💾 Memory after GC: {memory_percent_after_gc:.1f}%")

            # Apply chat template for VLM
            num_images = len(images) if images else 0
            logger.warning(f"📝 Applying chat template with {num_images} images...")
            formatted_prompt = apply_chat_template(
                self.processor,
                self.config,
                prompt,
                num_images=num_images
            )

            logger.warning(f"📝 Formatted prompt length: {len(formatted_prompt)} chars")

            # Estimate prompt tokens (rough approximation: ~4 chars per token)
            prompt_tokens = len(formatted_prompt) // 4

            # Generate with VLM
            # Use higher max_tokens to ensure complete JSON output
            # Temperature 0.1 for more deterministic output
            try:
                output = generate(
                    self.model,
                    self.processor,
                    formatted_prompt,
                    images if images else [],
                    max_tokens=1200,
                    temperature=0.1,
                    verbose=False
                )
                # mlx-vlm returns an object with .text attribute usually, or string
                response_text = output.text if hasattr(output, 'text') else str(output)
            except Exception as gen_error:
                error_str = str(gen_error)
                
                # Check if this is an OOM error - re-raise with clear message
                if is_oom_error(gen_error):
                    logger.error(f"💾 OOM during VLM generation: {error_str[:200]}")
                    # Clean up before re-raising
                    gc.collect()
                    if mx is not None:
                        try:
                            mx.metal.clear_cache()
                        except:
                            pass
                    raise RuntimeError(f"kIOGPUCommandBufferCallbackErrorOutOfMemory: {error_str[:100]}")
                
                # Check if this is a malformed output being raised as exception
                if '"' in error_str and ('{' in error_str or 'image' in error_str.lower()):
                    # This looks like partial model output raised as exception
                    logger.warning(f"⚠️ Generation raised partial output as exception: {repr(error_str[:100])}")
                    # Try to use the error string as the response if it looks like JSON
                    if '{' in error_str:
                        response_text = error_str
                    else:
                        # Return empty to trigger defaults
                        response_text = ""
                else:
                    raise

            # Track memory after generation
            memory_after_mb = process.memory_info().rss / 1024 / 1024
            peak_memory_mb = memory_after_mb

            # Estimate completion tokens
            completion_tokens = len(response_text) // 4
            total_tokens = prompt_tokens + completion_tokens

            # Build stats dictionary
            stats = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'peak_memory_mb': round(peak_memory_mb, 2)
            }

            logger.warning(f"🤖 Response length: {len(response_text)}")
            logger.warning(f"🤖 Response: {response_text[:500] if response_text else 'EMPTY'}")
            logger.warning(f"📊 Stats: {stats}")

            # Clean up after generation to free intermediate memory
            gc.collect()
            if MLX_VLM_AVAILABLE and mx is not None:
                try:
                    mx.metal.clear_cache()
                except:
                    pass

            return response_text, stats
        except Exception as e:
            logger.error(f"Generation error: {e}", exc_info=True)
            raise
    
    def _parse_json_response(self, response_text: str) -> dict:
        """
        Parse JSON from LLM response, handling various formats.

        Args:
            response_text: Raw LLM response

        Returns:
            Parsed JSON dictionary
        """
        if not response_text:
            logger.warning("📋 Empty response received")
            return self._default_analysis()
            
        logger.warning(f"📋 Parsing response (length: {len(response_text)})")
        logger.warning(f"📋 Response preview: {response_text[:200]}")

        # Try to extract JSON from markdown code blocks
        if '```json' in response_text:
            start = response_text.find('```json') + 7
            end = response_text.find('```', start)
            if end > start:
                json_str = response_text[start:end].strip()
            else:
                json_str = response_text[start:].strip()
        elif '```' in response_text:
            start = response_text.find('```') + 3
            end = response_text.find('```', start)
            if end > start:
                json_str = response_text[start:end].strip()
            else:
                json_str = response_text[start:].strip()
        else:
            # Try to find JSON object directly
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = response_text[start:end]
            else:
                # No JSON object found
                logger.warning(f"📋 No JSON object found in response")
                json_str = response_text
        
        # Try to parse the JSON
        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return result
            logger.warning(f"📋 JSON parsed but not a dict: {type(result)}")
            return self._default_analysis()
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            logger.warning(f"JSON String preview: {json_str[:300] if json_str else 'EMPTY'}...")
            
            # Attempt to fix common JSON errors
            try:
                logger.info("🔧 Attempting to fix JSON...")
                fixed_json = json_str
                
                # Fix 1: Add missing closing brace if truncated
                open_braces = fixed_json.count('{')
                close_braces = fixed_json.count('}')
                if open_braces > close_braces:
                    # Truncated JSON - try to close it
                    # First, try to find the last complete key-value pair
                    # Remove any trailing incomplete value
                    fixed_json = re.sub(r',\s*"[^"]*":\s*[^,}\]]*$', '', fixed_json)
                    fixed_json = fixed_json.rstrip(',\n\t ')
                    fixed_json += '}' * (open_braces - close_braces)
                    logger.info(f"🔧 Added {open_braces - close_braces} closing braces")
                
                # Fix 2: Missing commas between key-value pairs
                fixed_json = re.sub(r'(["}\]0-9eE\w])\s*\n\s*("[\w]+":)', r'\1,\n\2', fixed_json)
                
                # Fix 3: Trailing comma before closing brace
                fixed_json = re.sub(r',\s*}', '}', fixed_json)
                
                result = json.loads(fixed_json)
                if isinstance(result, dict):
                    logger.info("🔧 JSON fix successful!")
                    return result
            except Exception as fix_error:
                logger.warning(f"Failed to fix JSON: {fix_error}")
            
            # Return default values
            logger.warning("📋 Using default analysis values")
            return self._default_analysis()
    
    def _default_analysis(self) -> dict:
        """Return default analysis values when parsing fails"""
        return {
            "video_title": "Untitled Video",
            "short_description": "Content analysis unavailable",
            "content_type": "Other",
            "faculty": "General",
            "speaker_type": ["Staff"],
            "audience_type": ["Student"],
            "speaker_confidence": {"Staff": 1.0},
            "rationale_short": "Default values - analysis failed",
            "number_of_people_in_image": "1"
        }
    
    def _save_analysis_results(self, analytics: FileAnalytics, analysis: dict, file: File):
        """
        Save analysis results to FileAnalytics record.

        Args:
            analytics: FileAnalytics record to update
            analysis: Parsed analysis JSON
            file: Associated file
        """
        # Store raw JSON (includes image_description, estimated_age_of_people, etc.)
        analytics.analysis_json = json.dumps(analysis, indent=2)

        # Populate individual fields from LLM output
        analytics.title = analysis.get('video_title', analysis.get('title', 'Untitled Video'))
        analytics.description = analysis.get('short_description', analysis.get('description', ''))
        analytics.content_type = analysis.get('content_type', 'Other')
        analytics.faculty = analysis.get('faculty', 'General')

        # Handle JSON array/object fields with tolerant normalization
        audience_type = analysis.get('audience_type', ['Student'])
        raw_speaker_type = analysis.get('speaker_type')
        speaker_confidence = analysis.get('speaker_confidence', {'Staff': 1.0})

        def _normalize_speaker_type(raw, confidence):
            """Return a list of speaker labels using fallbacks.

            Acceptable input forms:
              - list of labels: ["Staff", "Student"]
              - single string label: "Staff"
              - dict of confidences: {"Staff": 0.8, "Student": 0.2}
              - missing/None -> infer from confidence dict
            Fallback precedence:
              1. Non-empty list
              2. String -> [string]
              3. Dict (raw) -> highest key by value
              4. Confidence dict -> highest key by value
              5. Default ["Staff"]
            """
            try:
                # Case 1: list already
                if isinstance(raw, list):
                    return raw if raw else ["Staff"]
                # Case 2: string
                if isinstance(raw, str):
                    return [raw] if raw.strip() else ["Staff"]
                # Case 3: dict treated as confidence map
                if isinstance(raw, dict) and raw:
                    # choose max value key(s); if multiple equal max, include all
                    max_val = max(raw.values())
                    winners = [k for k, v in raw.items() if v == max_val]
                    return winners
                # Case 4: use confidence dict
                if isinstance(confidence, dict) and confidence:
                    max_val = max(confidence.values())
                    winners = [k for k, v in confidence.items() if v == max_val]
                    return winners
            except Exception as e:  # defensive; shouldn't happen
                logger.warning(f"Speaker type normalization error: {e}")
            # Default
            return ["Staff"]

        speaker_type = _normalize_speaker_type(raw_speaker_type, speaker_confidence)
        # Log when fallback triggered (raw was missing or empty list/dict)
        if raw_speaker_type is None:
            logger.info("Speaker type missing; inferred from speaker_confidence fallback")
        elif isinstance(raw_speaker_type, list) and not raw_speaker_type:
            logger.info("Speaker type empty list; replaced with default 'Staff'")
        elif isinstance(raw_speaker_type, dict):
            logger.info("Speaker type provided as dict; normalized to highest-confidence labels")

        # Store as JSON strings
        analytics.speaker_type = json.dumps(speaker_type)
        analytics.audience_type = json.dumps(audience_type)
        analytics.speaker_confidence = json.dumps(speaker_confidence)
        analytics.rationale_short = analysis.get('rationale_short', '')

        # NEW: Populate simplified string fields for schema compliance
        # Convert JSON arrays to comma-separated strings
        analytics.speaker = ', '.join(speaker_type) if speaker_type else ''
        analytics.audience = ', '.join(audience_type) if audience_type else ''

        # Map number_of_people_in_image to speaker_count
        # Handle both string and int formats from LLM
        people_count = analysis.get('number_of_people_in_image', 1)
        try:
            analytics.speaker_count = int(people_count)
        except (ValueError, TypeError):
            analytics.speaker_count = 1

        # Populate duration fields from file
        if file.duration:
            analytics.duration_seconds = int(file.duration)
            analytics.duration = self._format_duration(file.duration)

        # Populate timestamp fields from session
        if file.session and file.session.recording_date:
            analytics.timestamp_sort = file.session.recording_date + "T00:00:00"
            analytics.timestamp = self._format_timestamp(file.session.recording_date)

        # Populate URLs (will be set by export service with SharePoint URLs)
        analytics.filename = file.filename

        # Studio location from session name or folder
        analytics.studio_location = self._extract_studio_location(file)

        self.db.commit()
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS or HH:MM:SS"""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    
    def _format_timestamp(self, date_str: str) -> str:
        """Format date as 'Nov 5, 10:30 AM'"""
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%b %d, %I:%M %p')
        except:
            return date_str
    
    def _extract_studio_location(self, file: File) -> str:
        """Extract studio location from session name or folder"""
        if file.session_folder:
            if 'City' in file.session_folder:
                return 'City'
            elif 'Keysborough' in file.session_folder:
                return 'Keysborough'
        
        if file.session and file.session.name:
            if 'City' in file.session.name:
                return 'City'
            elif 'Keysborough' in file.session.name:
                return 'Keysborough'
        
        return 'Unknown'
    
    async def _update_csv_export(self):
        """Trigger CSV export update"""
        # Import here to avoid circular dependency
        from services.analytics_excel_service import AnalyticsExcelService

        excel_service = AnalyticsExcelService(self.db)
        await excel_service.export_to_excel()
