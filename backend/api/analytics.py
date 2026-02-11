"""
Analytics API Endpoints

REST API for managing AI analytics.
Only included when BUILD_WITH_AI is enabled.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session, joinedload, load_only
from typing import List, Optional
from pydantic import BaseModel, field_validator
from datetime import datetime as dt
import logging

from database import get_db
from models import Session as SessionModel, File as FileModel
from models_analytics import FileAnalytics
from services.analytics_service import AnalyticsService
from services.analytics_excel_service import AnalyticsExcelService
from services.analytics_scheduler import get_scheduler
from config.ai_config import AI_ENABLED, get_model_path, ModelValidationError
from utils.error_handlers import handle_api_errors
from utils.caching import make_signature, maybe_304, cache_headers
from schemas import AnalyticsSummaryItem, AnalyticsDetail, TranscriptResponse
from constants import HTTPStatus

logger = logging.getLogger(__name__)
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter()


# Response Models
class AnalyticsResponse(BaseModel):
    """Single analytics record response"""
    id: str
    file_id: str
    session_id: Optional[str] = None
    state: str
    file_name: Optional[str] = None  # Alias for filename
    status: Optional[str] = None  # Alias for state
    filename: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    content_type: Optional[str] = None
    faculty: Optional[str] = None
    
    # NEW: Simplified string fields for schema compliance
    speaker: Optional[str] = None        # Comma-separated: "Staff, Student"
    audience: Optional[str] = None       # Comma-separated: "Student, Parent"
    
    # LEGACY: Detailed fields for internal use (keep for backward compatibility)
    speaker_type: Optional[str] = None   # JSON array of speaker types
    audience_type: Optional[str] = None  # JSON array of audience types
    speaker_confidence: Optional[str] = None  # JSON object of confidence scores
    rationale_short: Optional[str] = None  # AI reasoning
    language: Optional[str] = None  # Deprecated, use detected_language
    speaker_count: Optional[int] = None
    transcript: Optional[str] = None
    detected_language: Optional[str] = None
    analysis_json: Optional[str] = None
    error_message: Optional[str] = None

    # LLM statistics
    llm_prompt_tokens: Optional[int] = None
    llm_completion_tokens: Optional[int] = None
    llm_total_tokens: Optional[int] = None
    llm_peak_memory_mb: Optional[float] = None
    analysis_duration_seconds: Optional[int] = None

    # Analysis timestamps
    analysis_started_at: Optional[str] = None
    analysis_completed_at: Optional[str] = None

    created_at: str

    @field_validator('created_at', 'analysis_started_at', 'analysis_completed_at', mode='before')
    @classmethod
    def convert_datetime(cls, v):
        if isinstance(v, dt):
            return v.isoformat()
        return v

    def __init__(self, **data):
        # Map state to status and filename to file_name for frontend compatibility
        if 'state' in data and 'status' not in data:
            data['status'] = data['state']
        if 'filename' in data and 'file_name' not in data:
            data['file_name'] = data['filename']
        super().__init__(**data)

    class Config:
        from_attributes = True
        populate_by_name = True


class AnalyticsStatsResponse(BaseModel):
    """Analytics statistics response"""
    pending: int = 0
    transcribing: int = 0
    transcribed: int = 0
    analyzing: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    eligible_without_analytics: int = 0
    total_eligible: int = 0


class SchedulerStatusResponse(BaseModel):
    """Scheduler status response"""
    running: bool
    enabled: bool
    in_scheduled_hours: bool
    current_hour: int
    stats: AnalyticsStatsResponse


class CSVExportResponse(BaseModel):
    """CSV export response"""
    success: bool
    path: str
    records_exported: int
    message: str


class QueueAnalyticsRequest(BaseModel):
    """Request to queue analytics for specific files"""
    file_ids: Optional[List[str]] = None  # If None, queue all eligible


class AIInfoResponse(BaseModel):
    """AI model information response"""
    enabled: bool
    whisper_model: Optional[str] = None
    whisper_path: Optional[str] = None
    whisper_available: bool = False
    llm_model: Optional[str] = None
    llm_path: Optional[str] = None
    llm_available: bool = False


# Endpoints

@router.get("/info", response_model=AIInfoResponse)
@handle_api_errors("Get AI info")
def get_ai_info():
    """
    Get information about AI models and their availability.

    Returns model names, paths, and availability status.
    """
    if not AI_ENABLED:
        return AIInfoResponse(enabled=False)

    info = AIInfoResponse(enabled=True)

    # Check Whisper model
    try:
        whisper_path = get_model_path('whisper')
        info.whisper_path = whisper_path
        info.whisper_available = Path(whisper_path).exists()
        info.whisper_model = "mlx-community/whisper-small-mlx"
    except ModelValidationError as e:
        logger.warning(f"Whisper model validation failed: {e}")
        info.whisper_available = False

    # Check LLM model
    try:
        llm_path = get_model_path('llm')
        info.llm_path = llm_path
        info.llm_available = Path(llm_path).exists()
        info.llm_model = "Qwen3-VL-4B-Instruct-MLX-8bit"
    except ModelValidationError as e:
        logger.warning(f"LLM model validation failed: {e}")
        info.llm_available = False

    return info

@router.get("/", response_model=List[AnalyticsResponse])
@handle_api_errors("Get analytics")
def get_analytics(
    state: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Get list of analytics records with optional filtering.
    
    Query parameters:
    - state: Filter by state (PENDING, TRANSCRIBING, COMPLETED, etc.)
    - limit: Maximum number of records to return
    - offset: Number of records to skip
    """
    query = db.query(FileAnalytics).options(joinedload(FileAnalytics.file))
    
    if state:
        query = query.filter(FileAnalytics.state == state.upper())
    
    analytics = query.order_by(
        FileAnalytics.created_at.desc()
    ).limit(limit).offset(offset).all()
    
    # Build response including session_id from related File
    results: List[AnalyticsResponse] = []
    for a in analytics:
        try:
            results.append(AnalyticsResponse(
                id=a.id,
                file_id=a.file_id,
                session_id=getattr(getattr(a, 'file', None), 'session_id', None),
                state=a.state,
                filename=a.filename,
                title=a.title,
                description=a.description,
                content_type=a.content_type,
                faculty=a.faculty,
                speaker=a.speaker,
                audience=a.audience,
                speaker_type=a.speaker_type,
                audience_type=a.audience_type,
                speaker_confidence=a.speaker_confidence,
                rationale_short=a.rationale_short,
                language=a.detected_language,  # map detected_language to legacy 'language'
                speaker_count=a.speaker_count,
                transcript=a.transcript,
                detected_language=a.detected_language,
                analysis_json=a.analysis_json,
                error_message=a.error_message,
                llm_prompt_tokens=a.llm_prompt_tokens,
                llm_completion_tokens=a.llm_completion_tokens,
                llm_total_tokens=a.llm_total_tokens,
                llm_peak_memory_mb=a.llm_peak_memory_mb,
                analysis_duration_seconds=a.analysis_duration_seconds,
                analysis_started_at=a.analysis_started_at,
                analysis_completed_at=a.analysis_completed_at,
                created_at=a.created_at,
            ))
        except Exception as e:
            logger.warning(f"Failed to serialize analytics {a.id}: {e}")
    
    return results


@router.get("/stats", response_model=AnalyticsStatsResponse)
@handle_api_errors("Get analytics stats")
def get_analytics_stats(db: Session = Depends(get_db)):
    """
    Get analytics processing statistics.

    Returns counts by state and eligible files without analytics.
    """
    analytics_service = AnalyticsService(db)
    stats = analytics_service.get_analytics_stats()
    return AnalyticsStatsResponse(**stats)


@router.get("/transcript/{file_id}")
@handle_api_errors("Get transcript")
def get_transcript(file_id: str, db: Session = Depends(get_db)):
    """Return transcript text only for a file's analytics (lazy fetch)."""
    analytics = db.query(FileAnalytics).filter(FileAnalytics.file_id == file_id).first()
    if not analytics:
        raise HTTPException(status_code=404, detail="Analytics not found")
    return {"file_id": file_id, "transcript": analytics.transcript or ""}


@router.get("/summary", response_model=List[AnalyticsSummaryItem])
@handle_api_errors("Get analytics summary")
def get_analytics_summary(
    request: Request,
    db: Session = Depends(get_db),
    state: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "created_at:desc",
    # New filters for drill-down
    faculty: Optional[str] = None,
    content_type: Optional[str] = None,
    speaker_count: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    audience: Optional[str] = None,
    speaker_type: Optional[str] = None
):
    """
    Get lightweight list of analytics records (excludes transcript and heavy fields).

    This endpoint is optimized for list views and includes HTTP caching.

    Query parameters:
    - state: Filter by state (PENDING, TRANSCRIBING, COMPLETED, etc.)
    - q: Search query for title/filename
    - limit: Maximum number of records to return (default 50)
    - offset: Number of records to skip (default 0)
    - sort: Sort field and direction (e.g., created_at:desc)
    """
    # Build query with only lightweight fields
    qy = (
        db.query(FileAnalytics)
        .options(
            load_only(
                FileAnalytics.id,
                FileAnalytics.file_id,
                FileAnalytics.title,
                FileAnalytics.filename,
                FileAnalytics.state,
                FileAnalytics.created_at,
                FileAnalytics.analysis_duration_seconds,
                FileAnalytics.llm_total_tokens,
                FileAnalytics.faculty,
                FileAnalytics.content_type,
                FileAnalytics.speaker,
                FileAnalytics.audience,
                FileAnalytics.thumbnail_url,
                FileAnalytics.duration
            ),
            joinedload(FileAnalytics.file)
        )
    )

    # Apply filters
    # Apply filters
    if state:
        qy = qy.filter(FileAnalytics.state == state.upper())
    if q:
        qy = qy.filter(
            (FileAnalytics.title.ilike(f"%{q}%")) |
            (FileAnalytics.filename.ilike(f"%{q}%"))
        )
    
    # Debug logging for filters
    logger.info(f"Analytics Summary Filters: faculty={faculty}, content={content_type}, "
                f"speakers={speaker_count}, start={start_date}, end={end_date}, "
                f"audience={audience}, type={speaker_type}")

    # Drill-down filters
    if faculty:
        qy = qy.filter(FileAnalytics.faculty == faculty)
    
    if content_type:
        qy = qy.filter(FileAnalytics.content_type == content_type)
        
    if speaker_count is not None:
        qy = qy.filter(FileAnalytics.speaker_count == speaker_count)
        
    if audience:
        # Partial match for audience (comma separated list)
        qy = qy.filter(FileAnalytics.audience.ilike(f"%{audience}%"))
        
    if speaker_type:
        # Partial match for speaker type (comma separated list)
        qy = qy.filter(FileAnalytics.speaker.ilike(f"%{speaker_type}%"))
        
    if start_date:
        try:
            # Parse YYYY-MM-DD
            s_date = dt.strptime(start_date, '%Y-%m-%d')
            qy = qy.join(FileAnalytics.file).join(FileModel.session).filter(SessionModel.recording_date >= s_date)
        except ValueError:
            pass
            
    if end_date:
        try:
            # Parse YYYY-MM-DD and set to end of day
            e_date = dt.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            # Join only if not already joined (SQLAlchemy handles this usually, but good to be safe)
            if not start_date:
                qy = qy.join(FileAnalytics.file).join(FileModel.session)
            qy = qy.filter(SessionModel.recording_date <= e_date)
        except ValueError:
            pass

    # Get total for ETag calculation
    total = qy.count()

    # Apply sorting
    if sort == "created_at:desc":
        qy = qy.order_by(FileAnalytics.created_at.desc())
    elif sort == "created_at:asc":
        qy = qy.order_by(FileAnalytics.created_at.asc())

    # Apply pagination
    rows = qy.limit(limit).offset(offset).all()

    # Build response
    payload = []
    for r in rows:
        item = AnalyticsSummaryItem(
            id=r.id,
            file_id=r.file_id,
            session_id=getattr(getattr(r, 'file', None), 'session_id', None),
            title=r.title,
            filename=r.filename,
            file_name=r.filename,  # Alias for frontend
            owner=None,  # Add if you have owner field
            state=r.state,
            status=r.state,  # Alias for frontend
            created_at=r.created_at,
            analysis_duration_seconds=r.analysis_duration_seconds,
            llm_total_tokens=r.llm_total_tokens,
            faculty=r.faculty,
            content_type=r.content_type,
            speaker=r.speaker,
            audience=r.audience,
            thumbnail_url=r.thumbnail_url,
            duration=r.duration,
            recording_date=getattr(getattr(getattr(r, 'file', None), 'session', None), 'recording_date', None)
        )
        payload.append(item)

    # Generate ETag from query params and newest timestamp
    newest = rows[0].created_at.isoformat() if rows else "none"
    etag = make_signature("analytics-summary-v2", state, q, limit, offset, total, newest)

    # Check for 304 Not Modified
    if (resp := maybe_304(request, etag)):
        return resp

    # Return with cache headers
    return JSONResponse(
        content=[item.model_dump(mode='json') for item in payload],
        headers=cache_headers(etag)
    )


@router.get("/detail/{analytics_id}", response_model=AnalyticsDetail)
@handle_api_errors("Get analytics detail")
def get_analytics_detail(analytics_id: str, db: Session = Depends(get_db)):
    """
    Get full analytics record including heavy fields (transcript, analysis_json).

    Use this endpoint when the user expands a card for details.
    """
    analytics = db.query(FileAnalytics).options(
        joinedload(FileAnalytics.file)
    ).filter(FileAnalytics.id == analytics_id).first()

    if not analytics:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Analytics not found: {analytics_id}"
        )

    return AnalyticsDetail(
        id=analytics.id,
        file_id=analytics.file_id,
        session_id=getattr(getattr(analytics, 'file', None), 'session_id', None),
        title=analytics.title,
        filename=analytics.filename,
        file_name=analytics.filename,  # Alias for frontend
        owner=None,  # Add if you have owner field
        state=analytics.state,
        status=analytics.state,  # Alias for frontend
        created_at=analytics.created_at,
        transcript=analytics.transcript,
        analysis_json=analytics.analysis_json,
        description=analytics.description,
        thumbnail_path=analytics.file.thumbnail_path if analytics.file else None,
        content_type=analytics.content_type,
        faculty=analytics.faculty,
        speaker=analytics.speaker,
        audience=analytics.audience,
        speaker_type=analytics.speaker_type,
        audience_type=analytics.audience_type,
        speaker_confidence=analytics.speaker_confidence,
        rationale_short=analytics.rationale_short,
        detected_language=analytics.detected_language,
        speaker_count=analytics.speaker_count,
        error_message=analytics.error_message,
        llm_prompt_tokens=analytics.llm_prompt_tokens,
        llm_completion_tokens=analytics.llm_completion_tokens,
        llm_total_tokens=analytics.llm_total_tokens,
        llm_peak_memory_mb=analytics.llm_peak_memory_mb,
        analysis_duration_seconds=analytics.analysis_duration_seconds
    )


@router.get("/drilldown", response_model=List[AnalyticsSummaryItem])
@handle_api_errors("Get analytics drilldown")
def get_analytics_drilldown(
    time_range: str = Query(..., description="Time range filter used in chart"),
    filter_type: str = Query(..., description="Type of filter (audience, faculty, etc)"),
    filter_value: str = Query(..., description="Value of the clicked chart segment"),
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get detailed list of files matching a specific chart segment.
    Used for the drill-down modal when clicking on charts.
    """
    try:
        logger.info(f"🔍 Drilldown Request: range={time_range}, type={filter_type}, value={filter_value}")
        
        analytics_service = AnalyticsService(db)
        
        # Base query joining Analytics -> File -> Session
        query = db.query(FileAnalytics).join(FileAnalytics.file).join(FileModel.session)
        
        # 1. Apply Time Range (Must match chart logic)
        query = analytics_service.apply_time_filter(query, time_range)
        
        # 2. Apply Dimension Filter
        query = analytics_service.apply_drilldown_filter(query, filter_type, filter_value)
        
        # Execute
        analytics = query.order_by(SessionModel.recording_date.desc()).limit(limit).all()
        
        logger.info(f"✅ Drilldown found {len(analytics)} records")
        
        # Convert to summary items
        results = []
        for a in analytics:
            try:
                # Safe access to session_id
                session_id = a.file.session_id if a.file else None
                
                results.append(AnalyticsSummaryItem(
                    id=a.id,
                    file_id=a.file_id,
                    session_id=session_id,
                    title=a.title,
                    filename=a.filename,
                    file_name=a.filename,
                    state=a.state,
                    status=a.state,
                    created_at=a.created_at,
                    faculty=a.faculty,
                    content_type=a.content_type,
                    speaker=a.speaker,
                    audience=a.audience,
                    thumbnail_url=a.thumbnail_url,
                    duration=a.duration,
                    recording_date=a.file.session.recording_date if a.file and a.file.session else None
                ))
            except Exception as e:
                logger.error(f"⚠️ Failed to serialize analytics item {a.id}: {e}")
                continue
            
        return results
        
    except Exception as e:
        logger.error(f"❌ Drilldown failed: {e}", exc_info=True)
        raise e


# Prompt Management Endpoints (must come before /{file_id} to avoid route conflicts)

class PromptResponse(BaseModel):
    """Prompt response"""
    system_prompt: str
    user_prompt: str


class UpdatePromptRequest(BaseModel):
    """Request to update prompts"""
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None


@router.get("/prompts", response_model=PromptResponse)
@handle_api_errors("Get prompts")
def get_prompts(request: Request, db: Session = Depends(get_db)):
    """
    Get current system and user prompts for LLM analysis.

    Returns:
        System and user prompts
    """
    from services.ai_config_service import AIConfigService

    logger.info("📥 GET /api/analytics/prompts - Fetching prompts")
    ai_config = AIConfigService(db)

    system_prompt = ai_config.get_system_prompt()
    user_prompt = ai_config.get_user_prompt()

    # Generate ETag from prompt lengths and content hash
    etag = make_signature("prompts", len(system_prompt), len(user_prompt), system_prompt[:100], user_prompt[:100])

    # Check for 304 Not Modified
    if (resp := maybe_304(request, etag)):
        return resp

    logger.info(f"📤 Returning prompts: system={len(system_prompt)} chars, user={len(user_prompt)} chars")

    body = {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt
    }
    return JSONResponse(content=body, headers=cache_headers(etag))


@router.put("/prompts")
@handle_api_errors("Update prompts")
def update_prompts(request: UpdatePromptRequest, db: Session = Depends(get_db)):
    """
    Update system and/or user prompts for LLM analysis.

    Args:
        request: Updated prompts (either or both)

    Returns:
        Success message with updated prompts
    """
    from services.ai_config_service import AIConfigService

    logger.info("📥 PUT /api/analytics/prompts - Updating prompts")
    logger.info(f"   system_prompt: {len(request.system_prompt) if request.system_prompt else 0} chars")
    logger.info(f"   user_prompt: {len(request.user_prompt) if request.user_prompt else 0} chars")

    ai_config = AIConfigService(db)

    if request.system_prompt is not None:
        logger.info("   Saving system prompt...")
        ai_config.save_system_prompt(request.system_prompt)

    if request.user_prompt is not None:
        logger.info("   Saving user prompt...")
        ai_config.save_user_prompt(request.user_prompt)

    # Get the saved prompts to return
    saved_system = ai_config.get_system_prompt()
    saved_user = ai_config.get_user_prompt()
    
    logger.info(f"📤 Update complete. Returning: system={len(saved_system)} chars, user={len(saved_user)} chars")

    return {
        "success": True,
        "message": "Prompts updated successfully",
        "system_prompt": saved_system,
        "user_prompt": saved_user
    }


@router.get("/whisper-settings")
@handle_api_errors("Get Whisper settings")
def get_whisper_settings(request: Request, db: Session = Depends(get_db)):
    """
    Get current Whisper transcription settings.

    Returns:
        Dictionary of Whisper settings including prompt_words
    """
    from services.ai_config_service import AIConfigService

    logger.info("📥 GET /api/analytics/whisper-settings - Fetching Whisper settings")
    ai_config = AIConfigService(db)

    settings = ai_config.get_whisper_settings()

    # Generate ETag from settings content
    import json
    settings_str = json.dumps(settings, sort_keys=True)
    etag = make_signature("whisper-settings", settings_str)

    # Check for 304 Not Modified
    if (resp := maybe_304(request, etag)):
        return resp

    logger.info(f"📤 Returning Whisper settings: {settings}")

    body = {
        "success": True,
        "settings": settings
    }
    return JSONResponse(content=body, headers=cache_headers(etag))


@router.put("/whisper-settings")
@handle_api_errors("Update Whisper settings")
def update_whisper_settings(request: dict, db: Session = Depends(get_db)):
    """
    Update Whisper transcription settings.

    Args:
        request: Dictionary of Whisper settings

    Returns:
        Success message with updated settings
    """
    from services.ai_config_service import AIConfigService

    logger.info("📥 PUT /api/analytics/whisper-settings - Updating Whisper settings")
    logger.info(f"   Settings: {request}")

    ai_config = AIConfigService(db)
    
    # Extract settings from request
    settings = request.get('settings', request)
    
    # Save settings
    ai_config.save_whisper_settings(settings)

    # Get the saved settings to return
    saved_settings = ai_config.get_whisper_settings()
    
    logger.info(f"📤 Update complete. Returning: {saved_settings}")

    return {
        "success": True,
        "message": "Whisper settings updated successfully",
        "settings": saved_settings
    }


@router.post("/toggle-pause")
@handle_api_errors("Toggle Analytics Pause")
def toggle_analytics_pause(db: Session = Depends(get_db)):
    """
    Toggle analytics processing on/off.
    """
    from models import Job, Setting
    from constants import SettingKeys

    # Get current pause setting
    pause_setting = db.query(Setting).filter(
        Setting.key == SettingKeys.PAUSE_ANALYTICS
    ).first()

    if not pause_setting:
        # Create setting if it doesn't exist
        pause_setting = Setting(key=SettingKeys.PAUSE_ANALYTICS, value='true')
        db.add(pause_setting)

    # Toggle the setting
    current_paused = pause_setting.value == 'true'
    new_paused = not current_paused
    pause_setting.value = 'true' if new_paused else 'false'

    cancelled_job_id = None

    # If pausing, cancel any running ANALYZE job
    if new_paused:
        running_job = db.query(Job).filter(
            Job.kind == 'ANALYZE',
            Job.state == 'RUNNING'
        ).first()

        if running_job:
            running_job.cancellation_requested = True
            cancelled_job_id = running_job.id
            logger.info(f"Cancellation requested for ANALYZE job {running_job.id} due to pause")

    db.commit()

    state_text = "paused" if new_paused else "resumed"
    logger.info(f"Analytics processing {state_text}")

    return {
        "success": True,
        "paused": new_paused,
        "message": f"Analytics processing {state_text}",
        "cancelled_job_id": cancelled_job_id
    }


@router.get("/pause-status")
@handle_api_errors("Get Analytics Pause Status")
def get_analytics_pause_status(db: Session = Depends(get_db)):
    """
    Get current analytics pause status.
    """
    from models import Job, Setting
    from constants import SettingKeys

    # Get pause setting
    pause_setting = db.query(Setting).filter(
        Setting.key == SettingKeys.PAUSE_ANALYTICS
    ).first()

    paused = pause_setting.value == 'true' if pause_setting else True

    # Get job counts
    queued_count = db.query(Job).filter(
        Job.kind == 'ANALYZE',
        Job.state == 'QUEUED'
    ).count()

    running_job = db.query(Job).filter(
        Job.kind == 'ANALYZE',
        Job.state == 'RUNNING'
    ).first()

    return {
        "paused": paused,
        "queued_count": queued_count,
        "running_job_id": running_job.id if running_job else None
    }


@router.get("/settings/run-when-idle")
@handle_api_errors("Get run when idle setting")
def get_run_when_idle(db: Session = Depends(get_db)):
    """Get the run_analytics_when_idle setting"""
    from models import Setting
    from constants import SettingKeys

    setting = db.query(Setting).filter(
        Setting.key == SettingKeys.RUN_ANALYTICS_WHEN_IDLE
    ).first()

    return {
        "enabled": setting.value == 'true' if setting else True
    }


@router.post("/settings/run-when-idle")
@handle_api_errors("Set run when idle setting")
def set_run_when_idle(request: dict, db: Session = Depends(get_db)):
    """Toggle the run_analytics_when_idle setting"""
    from models import Setting
    from constants import SettingKeys

    enabled = request.get('enabled', True)

    setting = db.query(Setting).filter(
        Setting.key == SettingKeys.RUN_ANALYTICS_WHEN_IDLE
    ).first()

    if not setting:
        setting = Setting(key=SettingKeys.RUN_ANALYTICS_WHEN_IDLE, value='true' if enabled else 'false')
        db.add(setting)
    else:
        setting.value = 'true' if enabled else 'false'

    db.commit()

    logger.info(f"Run analytics when idle: {'enabled' if enabled else 'disabled'}")

    return {
        "success": True,
        "enabled": enabled,
        "message": f"Analytics will {'only run when pipeline is idle' if enabled else 'run regardless of pipeline activity'}"
    }


@router.get("/charts", response_model=dict)
@handle_api_errors("Get analytics charts")
def get_analytics_charts(
    time_range: str = "all",
    db: Session = Depends(get_db)
):
    """
    Get aggregated data for analytics charts.
    
    Args:
        time_range: Time range filter (all, 12m, 6m, 30d, 7d, 2024, etc.)
    """
    from sqlalchemy import func, case, desc
    from datetime import datetime, timedelta
    from models import Session as SessionModel, FileAnalytics, File, Setting, Job
    
    # Create service instance for shared logic
    service = AnalyticsService(db)
    
    # Base query
    base_query = db.query(FileAnalytics).join(FileAnalytics.file).join(File.session)
    
    # Apply Time Filter via Service
    base_query = service.apply_time_filter(base_query, time_range)
    
    now = datetime.utcnow()
        
    # Helper for simple aggregations
    def get_agg(field, func_agg=func.count(FileAnalytics.id)):
        results = (
            base_query
            .with_entities(field, func_agg)
            .group_by(field)
            .order_by(func_agg.desc())
            .limit(10)
            .all()
        )
        return [
            ChartDataPoint(name=str(r[0] or "Unknown"), value=r[1]) 
            for r in results if (r[1] or 0) > 0
        ]

    # 1. Recording Volume Over Time
    # Dynamic grouping: Day for short ranges, Week for long ranges
    if time_range in ["7d", "30d"]:
        # Group by Day (YYYY-MM-DD)
        date_format = '%Y-%m-%d'
        group_col = SessionModel.recording_date
        
        # Calculate start date for filling gaps
        if time_range == "7d":
            fill_start = now - timedelta(days=7)
        else:
            fill_start = now - timedelta(days=30)
        
        # Generate all days in range
        all_periods = []
        curr = fill_start
        while curr <= now:
            all_periods.append(curr.strftime("%Y-%m-%d"))
            curr += timedelta(days=1)
            
    else:
        # Group by Week (YYYY-Www)
        date_format = '%Y-W%W'
        group_col = func.strftime(date_format, SessionModel.recording_date)
        
        # Calculate start date for filling gaps (simplified logic matches service)
        if time_range == "12m":
            fill_start = now - timedelta(days=365)
        elif time_range == "6m":
            fill_start = now - timedelta(days=180)
        elif time_range.isdigit() and len(time_range) == 4:
            fill_start = datetime(int(time_range), 1, 1)
        else:
            # "all" or unknown
            fill_start = now - timedelta(days=365)
            
        # Generate all weeks in range
        all_periods = []
        curr = fill_start - timedelta(days=fill_start.weekday())
        while curr <= now:
            all_periods.append(curr.strftime("%Y-W%W"))
            curr += timedelta(weeks=1)

    # Query DB
    vol_data = (
        base_query
        .with_entities(
            group_col.label('period'),
            func.sum(func.coalesce(FileAnalytics.duration_seconds, File.duration, 0))
        )
        .group_by('period')
        .order_by('period')
        .all()
    )
    
    # Convert DB results to dict for easy lookup
    data_map = {r[0]: r[1] for r in vol_data if r[0]}
    
    # Merge with all periods
    recording_volume = []
    for period in all_periods:
        val = data_map.get(period, 0)
        recording_volume.append(
            ChartDataPoint(name=period, value=round((val or 0) / 3600, 1))
        )

    # 2. Total Content Hours per Faculty
    hours_data = get_agg(FileAnalytics.faculty, func.sum(FileAnalytics.duration_seconds))
    content_hours_faculty = [
        ChartDataPoint(name=d.name, value=round(d.value / 3600, 1))
        for d in hours_data
    ]

    # 3. Speaker Count Distribution
    speaker_count_dist = get_agg(FileAnalytics.speaker_count)
    # Filter out "Unknown" (null values)
    speaker_count_dist = [d for d in speaker_count_dist if d.name != "Unknown"]
    try:
        speaker_count_dist.sort(key=lambda x: int(x.name) if str(x.name).isdigit() else 0)
    except:
        pass

    # 4. Target Audience Analysis
    # Fetch all audience strings to manually aggregate
    audience_rows = base_query.with_entities(FileAnalytics.audience).filter(FileAnalytics.audience.isnot(None)).all()
    
    audience_counts = {"Parent": 0, "Student": 0, "Staff": 0, "Prospective": 0}
    for row in audience_rows:
        if not row[0]: continue
        targets = [t.strip() for t in row[0].split(',')]
        for target in targets:
            target_lower = target.lower()
            if "parent" in target_lower: audience_counts["Parent"] += 1
            if "student" in target_lower: audience_counts["Student"] += 1
            if "staff" in target_lower: audience_counts["Staff"] += 1
            if "prospective" in target_lower: audience_counts["Prospective"] += 1
                
    audience_dist = [ChartDataPoint(name=k, value=v) for k, v in audience_counts.items()]

    # 5. Speaker Demographics
    allowed_speakers = ["Staff", "Student", "Staff, Student", "Staff,Student"]
    speaker_results = (
        base_query
        .with_entities(FileAnalytics.speaker, func.count(FileAnalytics.id))
        .filter(FileAnalytics.speaker.in_(allowed_speakers))
        .group_by(FileAnalytics.speaker)
        .order_by(func.count(FileAnalytics.id).desc())
        .all()
    )
    speaker_dist = [ChartDataPoint(name=r[0], value=r[1]) for r in speaker_results]

    # 6. Campus Content Hours
    campus_data = (
        base_query
        .with_entities(
            SessionModel.campus,
            func.sum(func.coalesce(FileAnalytics.duration_seconds, File.duration, 0))
        )
        .group_by(SessionModel.campus)
        .order_by(func.sum(func.coalesce(FileAnalytics.duration_seconds, File.duration, 0)).desc())
        .all()
    )
    
    campus_dist = [
        ChartDataPoint(name=str(r[0] or "Unknown"), value=round((r[1] or 0) / 3600, 1))
        for r in campus_data if (r[1] or 0) > 0
    ]

    # 7. Language Distribution
    language_results = (
        base_query
        .with_entities(FileAnalytics.detected_language, func.count(FileAnalytics.id))
        .filter(FileAnalytics.detected_language.isnot(None))
        .group_by(FileAnalytics.detected_language)
        .order_by(func.count(FileAnalytics.id).desc())
        .all()
    )
    language_dist = [ChartDataPoint(name=r[0], value=r[1]) for r in language_results]

    # 7. Content Type (Hours)
    type_data = get_agg(FileAnalytics.content_type, func.sum(FileAnalytics.duration_seconds))
    content_type_dist = [ChartDataPoint(name=d.name, value=round(d.value / 3600, 1)) for d in type_data]

    # 8. Faculty Count Distribution (ordered by count desc)
    faculty_results = (
        base_query
        .with_entities(FileAnalytics.faculty, func.count(FileAnalytics.id))
        .filter(FileAnalytics.faculty.isnot(None))
        .group_by(FileAnalytics.faculty)
        .order_by(func.count(FileAnalytics.id).desc())
        .all()
    )
    faculty_count_dist = [ChartDataPoint(name=r[0], value=r[1]) for r in faculty_results]

    # 9. Content Type Count Distribution (ordered by count desc)
    content_type_results = (
        base_query
        .with_entities(FileAnalytics.content_type, func.count(FileAnalytics.id))
        .filter(FileAnalytics.content_type.isnot(None))
        .group_by(FileAnalytics.content_type)
        .order_by(func.count(FileAnalytics.id).desc())
        .all()
    )
    content_type_count_dist = [ChartDataPoint(name=r[0], value=r[1]) for r in content_type_results]

    total_duration_seconds = base_query.with_entities(func.sum(FileAnalytics.duration_seconds)).scalar() or 0
    total_videos = base_query.count()

    # 10. Video Duration Distribution
    duration_results = (
        base_query
        .with_entities(func.coalesce(FileAnalytics.duration_seconds, File.duration, 0))
        .all()
    )
    
    # Define buckets
    duration_buckets = {
        "0-30s": 0,
        "30s-1m": 0,
        "1-5m": 0,
        "5-10m": 0,
        "10-20m": 0,
        "20-30m": 0
    }
    
    for row in duration_results:
        seconds = row[0] or 0
        minutes = seconds / 60
        
        if seconds < 30:
            duration_buckets["0-30s"] += 1
        elif seconds < 60:
            duration_buckets["30s-1m"] += 1
        elif minutes < 5:
            duration_buckets["1-5m"] += 1
        elif minutes < 10:
            duration_buckets["5-10m"] += 1
        elif minutes < 20:
            duration_buckets["10-20m"] += 1
        elif minutes < 30:
            duration_buckets["20-30m"] += 1
        # Ignore > 30m as requested
            
    video_duration_dist = [ChartDataPoint(name=k, value=v) for k, v in duration_buckets.items()]

    return {
        "recording_volume": recording_volume,
        "content_hours_faculty": content_hours_faculty,
        "speaker_count_dist": speaker_count_dist,
        "audience_dist": audience_dist,
        "speaker_dist": speaker_dist,
        "campus_dist": campus_dist,
        "language_dist": language_dist,
        "content_type_dist": content_type_dist,
        "faculty_count_dist": faculty_count_dist,
        "content_type_count_dist": content_type_count_dist,
        "video_duration_dist": video_duration_dist,
        "total_duration_seconds": total_duration_seconds,
        "total_videos": total_videos
    }


class ChartDataPoint(BaseModel):
    name: str
    value: float


@router.get("/{file_id}", response_model=AnalyticsResponse)
@handle_api_errors("Get analytics by file")
def get_analytics_by_file(file_id: str, db: Session = Depends(get_db)):
    """
    Get analytics for a specific file.
    
    Args:
        file_id: File ID to get analytics for
    """
    analytics = db.query(FileAnalytics).filter(
        FileAnalytics.file_id == file_id
    ).first()
    
    if not analytics:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Analytics not found for file {file_id}"
        )
    
    return analytics


@router.post("/queue")
@handle_api_errors("Queue analytics")
def queue_analytics(
    request: QueueAnalyticsRequest = QueueAnalyticsRequest(),
    db: Session = Depends(get_db)
):
    """
    Queue analytics jobs for files.
    """
    analytics_service = AnalyticsService(db)
    
    if request.file_ids:
        # Queue specific files
        from models import File
        queued_count = 0
        
        for file_id in request.file_ids:
            file = db.query(File).filter(File.id == file_id).first()
            if not file:
                logger.warning(f"File {file_id} not found")
                continue
            
            if analytics_service.queue_analytics_for_file(file):
                queued_count += 1
        
        return {
            "success": True,
            "queued": queued_count,
            "message": f"Queued {queued_count} analytics jobs"
        }
    else:
        # Queue all eligible files
        queued_count = analytics_service.queue_pending_analytics()
        
        return {
            "success": True,
            "queued": queued_count,
            "message": f"Queued {queued_count} analytics jobs"
        }


@router.post("/{file_id}/retry")
@handle_api_errors("Retry analytics")
def retry_analytics(file_id: str, db: Session = Depends(get_db)):
    """
    Retry analytics for a file that failed.
    """
    analytics_service = AnalyticsService(db)
    job = analytics_service.retry_failed_analytics(file_id)

    if not job:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot retry analytics for this file"
        )

    return {
        "success": True,
        "job_id": job.id,
        "message": f"Queued {job.kind} job for retry"
    }


@router.post("/{file_id}/force-start")
@handle_api_errors("Force start analytics")
def force_start_analytics(file_id: str, db: Session = Depends(get_db)):
    """
    Force start analytics processing immediately.
    """
    from models import File, Job
    from datetime import datetime

    # Get file analytics record
    analytics = db.query(FileAnalytics).filter(
        FileAnalytics.file_id == file_id
    ).first()

    if not analytics:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"No analytics record found for file {file_id}"
        )

    # Verify state allows force start
    if analytics.state not in ['PENDING', 'FAILED']:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Cannot force start analytics in state: {analytics.state}"
        )

    # Reset analytics state if FAILED
    if analytics.state == 'FAILED':
        analytics.state = 'PENDING'
        analytics.error_message = None
        analytics.manual_retry_required = False
        db.commit()

    # Check for existing TRANSCRIBE job
    existing_job = db.query(Job).filter(
        Job.file_id == file_id,
        Job.kind == 'TRANSCRIBE',
        Job.state.in_(['QUEUED', 'RUNNING'])
    ).first()

    if existing_job:
        # Update priority to maximum for immediate processing
        existing_job.priority = 1000
        existing_job.created_at = datetime.utcnow()  # Bump to front of queue
        db.commit()
        job_id = existing_job.id
        logger.info(f"Updated existing TRANSCRIBE job {job_id} to priority 1000 for file {file_id}")
    else:
        # Create new TRANSCRIBE job with maximum priority
        from utils.uuid_helper import generate_uuid
        job = Job(
            id=generate_uuid(),
            file_id=file_id,
            kind='TRANSCRIBE',
            state='QUEUED',
            priority=1000,  # Maximum priority for immediate processing
            created_at=datetime.utcnow()
        )
        db.add(job)
        db.commit()
        job_id = job.id
        logger.info(f"Created TRANSCRIBE job {job_id} with priority 1000 for file {file_id}")

    return {
        "success": True,
        "job_id": job_id,
        "file_id": file_id,
        "message": "Analytics forced to start with maximum priority"
    }


@router.post("/export", response_model=CSVExportResponse)
@handle_api_errors("Export analytics CSV")
async def export_analytics_csv(
    include_pending: bool = False,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Export analytics to CSV file.
    """
    csv_service = AnalyticsExcelService(db)
    
    # Get count of records to export
    from sqlalchemy import func
    query = db.query(func.count(FileAnalytics.id))
    if not include_pending:
        query = query.filter(FileAnalytics.state == 'COMPLETED')
    record_count = query.scalar() or 0
    
    if record_count == 0:
        return CSVExportResponse(
            success=False,
            path="",
            records_exported=0,
            message="No analytics records to export"
        )
    
    # Export CSV
    export_path = await csv_service.export_to_csv(include_pending)
    
    return CSVExportResponse(
        success=True,
        path=str(export_path),
        records_exported=record_count,
        message=f"Exported {record_count} records to CSV"
    )


@router.get("/export/stats")
@handle_api_errors("Get export stats")
def get_export_stats(db: Session = Depends(get_db)):
    """
    Get statistics about CSV exports.
    """
    csv_service = AnalyticsExcelService(db)
    return csv_service.get_export_stats()


@router.get("/export/download")
@handle_api_errors("Download analytics Excel file")
async def download_analytics_excel(db: Session = Depends(get_db)):
    """
    Download the analytics Excel file.
    """
    # Create the Excel export
    excel_service = AnalyticsExcelService(db)
    excel_path = await excel_service.export_to_excel(include_pending=False)

    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="Excel file not found")

    # Return the file for download
    return FileResponse(
        path=str(excel_path),
        filename="analytics.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
@handle_api_errors("Get scheduler status")
def get_scheduler_status():
    """
    Get analytics scheduler status.
    """
    scheduler = get_scheduler()
    status = scheduler.get_status()
    
    # Convert stats dict to AnalyticsStatsResponse
    stats = AnalyticsStatsResponse(**status.get('stats', {}))
    
    return SchedulerStatusResponse(
        running=status['running'],
        enabled=status['enabled'],
        in_scheduled_hours=status['in_scheduled_hours'],
        current_hour=status['current_hour'],
        stats=stats
    )


@router.post("/scheduler/pause")
@handle_api_errors("Pause scheduler")
def pause_scheduler():
    """
    Pause analytics processing.
    """
    scheduler = get_scheduler()
    scheduler.pause_analytics()
    
    return {
        "success": True,
        "message": "Analytics processing paused"
    }


@router.post("/scheduler/resume")
@handle_api_errors("Resume scheduler")
def resume_scheduler():
    """
    Resume analytics processing.
    """
    scheduler = get_scheduler()
    scheduler.resume_analytics()

    return {
        "success": True,
        "message": "Analytics processing resumed"
    }


@router.post("/{file_id}/analyze")
@handle_api_errors("Trigger analysis")
def trigger_analysis(file_id: str, db: Session = Depends(get_db)):
    """
    Manually trigger LLM analysis for a file that has been transcribed.
    """
    from models import File, Job
    from datetime import datetime

    # Get file analytics record
    analytics = db.query(FileAnalytics).filter(
        FileAnalytics.file_id == file_id
    ).first()

    if not analytics:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"No analytics record found for file {file_id}"
        )

    # Verify file has been transcribed
    if not analytics.transcript:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"File has not been transcribed yet. State: {analytics.state}"
        )

    # Check for existing ANALYZE job
    existing_job = db.query(Job).filter(
        Job.file_id == file_id,
        Job.kind == 'ANALYZE',
        Job.state.in_(['QUEUED', 'RUNNING'])
    ).first()

    if existing_job:
        # Update priority to maximum for immediate processing
        existing_job.priority = 1000
        existing_job.created_at = datetime.utcnow()
        db.commit()
        job_id = existing_job.id
        logger.info(f"Updated existing ANALYZE job {job_id} to priority 1000 for file {file_id}")
    else:
        # Create new ANALYZE job with maximum priority
        from utils.uuid_helper import generate_uuid
        job = Job(
            id=generate_uuid(),
            file_id=file_id,
            kind='ANALYZE',
            state='QUEUED',
            priority=1000,
            created_at=datetime.utcnow()
        )
        db.add(job)

        # Update analytics state if needed
        if analytics.state in ['TRANSCRIBED', 'FAILED']:
            analytics.state = 'TRANSCRIBED'
            analytics.error_message = None

        db.commit()
        job_id = job.id
        logger.info(f"Created ANALYZE job {job_id} with priority 1000 for file {file_id}")

    return {
        "success": True,
        "job_id": job_id,
        "file_id": file_id,
        "message": "Analysis queued with maximum priority"
    }


@router.post("/{file_id}/re-transcribe")
@handle_api_errors("Re-transcribe")
def retranscribe_file(file_id: str, db: Session = Depends(get_db)):
    """
    Reset transcription and re-transcribe a file.
    """
    from models import File, Job
    from datetime import datetime
    
    # Get file analytics record
    analytics = db.query(FileAnalytics).filter(
        FileAnalytics.file_id == file_id
    ).first()
    
    # If analytics record doesn't exist, check if file exists and create it
    if not analytics:
        file = db.query(File).filter(File.id == file_id).first()
        if not file:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=f"File {file_id} not found"
            )
            
        # Create new analytics record
        logger.info(f"Creating missing analytics record for file {file_id}")
        
        # Format duration string
        duration_str = None
        if file.duration:
            hours = int(file.duration // 3600)
            minutes = int((file.duration % 3600) // 60)
            seconds = int(file.duration % 60)
            if hours > 0:
                duration_str = f"{hours}h {minutes}m"
            else:
                duration_str = f"{minutes}m {seconds}s"

        analytics = FileAnalytics(
            file_id=file.id,
            filename=file.filename,
            state='PENDING',
            duration_seconds=int(file.duration) if file.duration else None,
            duration=duration_str
        )
        db.add(analytics)
        db.commit()
        db.refresh(analytics)
    
    # Clear transcript and analysis data
    analytics.transcript = None
    analytics.analysis_json = None
    analytics.title = None
    analytics.description = None
    analytics.content_type = None
    analytics.faculty = None
    analytics.audience = None
    analytics.speaker = None
    analytics.audience_type = None
    analytics.speaker_type = None
    analytics.speaker_confidence = None
    analytics.rationale_short = None
    analytics.language = None
    analytics.detected_language = None
    analytics.speaker_count = None
    analytics.transcription_started_at = None
    analytics.transcription_completed_at = None
    analytics.transcription_duration_seconds = None
    analytics.analysis_started_at = None
    analytics.analysis_completed_at = None
    analytics.analysis_duration_seconds = None
    analytics.transcription_settings_json = None
    analytics.llm_stats_json = None
    analytics.llm_prompt_tokens = None
    analytics.llm_completion_tokens = None
    analytics.llm_total_tokens = None
    analytics.llm_peak_memory_mb = None
    
    # Reset state to PENDING
    analytics.state = 'PENDING'
    analytics.error_message = None
    analytics.retry_count = 0
    
    # Delete any existing TRANSCRIBE or ANALYZE jobs
    db.query(Job).filter(
        Job.file_id == file_id,
        Job.kind.in_(['TRANSCRIBE', 'ANALYZE'])
    ).delete()
    
    # Create new TRANSCRIBE job with maximum priority
    from utils.uuid_helper import generate_uuid
    job = Job(
        id=generate_uuid(),
        file_id=file_id,
        kind='TRANSCRIBE',
        state='QUEUED',
        priority=1000,
        created_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()
    
    job_id = job.id
    logger.info(f"Reset and created TRANSCRIBE job {job_id} with priority 1000 for file {file_id}")
    
    return {
        "success": True,
        "job_id": job_id,
        "file_id": file_id,
        "message": "Transcription reset. Re-transcription queued."
    }


@router.post("/{file_id}/open-folder")
@handle_api_errors("Open analytics folder")
def open_analytics_folder(file_id: str, db: Session = Depends(get_db)):
    """
    Open the AI analytics external export folder in Finder (macOS only).
    """
    import platform
    import subprocess
    from models import File

    if platform.system() != 'Darwin':
        raise HTTPException(
            status_code=HTTPStatus.NOT_IMPLEMENTED,
            detail="This feature is only supported on macOS"
        )

    file = db.query(FileModel).filter(FileModel.id == file_id).first()
    if not file:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"File '{file_id}' not found"
        )

    if not file.external_export_path:
        # Fallback to output folder if no external export path
        # Use session logic to open parent folder
        return open_session_folder_logic(file.session_id, db)
        
    external_path = Path(file.external_export_path)
    if not external_path.exists() or not external_path.is_dir():
         # Fallback to session logic
        return open_session_folder_logic(file.session_id, db)

    try:
        subprocess.run(['open', str(external_path)], check=True)
        return {
            "success": True,
            "message": "Folder opened in Finder",
            "path": str(external_path)
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to open folder: {str(e)}"
        )

def open_session_folder_logic(session_id: str, db: Session):
    """Helper to open session folder (reused logic)"""
    import subprocess
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Attempt to find a completed file to get path
    file = db.query(FileModel).filter(
        FileModel.session_id == session_id,
        FileModel.path_final.isnot(None)
    ).first()
    
    if not file:
        raise HTTPException(status_code=404, detail="No valid path found for session")
        
    path = Path(file.path_final).parent
    # If in subfolder, go up
    if file.relative_path and '/' in file.relative_path:
        path = path.parent
        
    if not path.exists():
         raise HTTPException(status_code=404, detail="Folder path does not exist")
         
    try:
        subprocess.run(['open', str(path)], check=True)
        return {"success": True, "message": "Opened folder", "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BulkOperationRequest(BaseModel):
    """Request for bulk operations on files"""
    file_ids: List[str]


@router.post("/bulk-re-transcribe")
@handle_api_errors("Bulk re-transcribe")
def bulk_retranscribe_files(request: BulkOperationRequest, db: Session = Depends(get_db)):
    """
    Re-transcribe multiple files at once.
    """
    from models import File, Job
    from datetime import datetime

    if not request.file_ids:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="No file IDs provided"
        )

    queued_count = 0
    skipped_count = 0

    for file_id in request.file_ids:
        analytics = db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file_id
        ).first()

        # If analytics record doesn't exist, check if file exists and create it
        if not analytics:
            file = db.query(File).filter(File.id == file_id).first()
            if not file:
                skipped_count += 1
                continue
                
            # Create new analytics record
            duration_str = None
            if file.duration:
                hours = int(file.duration // 3600)
                minutes = int((file.duration % 3600) // 60)
                seconds = int(file.duration % 60)
                if hours > 0:
                    duration_str = f"{hours}h {minutes}m"
                else:
                    duration_str = f"{minutes}m {seconds}s"

            analytics = FileAnalytics(
                file_id=file.id,
                filename=file.filename,
                state='PENDING',
                duration_seconds=int(file.duration) if file.duration else None,
                duration=duration_str
            )
            db.add(analytics)
            db.commit()
            db.refresh(analytics)

        # Clear transcript and analysis data
        analytics.transcript = None
        analytics.analysis_json = None
        analytics.title = None
        analytics.description = None
        analytics.content_type = None
        analytics.faculty = None
        analytics.audience = None
        analytics.speaker = None
        analytics.audience_type = None
        analytics.speaker_type = None
        analytics.speaker_confidence = None
        analytics.rationale_short = None
        analytics.language = None
        analytics.detected_language = None
        analytics.speaker_count = None
        analytics.transcription_started_at = None
        analytics.transcription_completed_at = None
        analytics.transcription_duration_seconds = None
        analytics.analysis_started_at = None
        analytics.analysis_completed_at = None
        analytics.analysis_duration_seconds = None
        analytics.transcription_settings_json = None
        analytics.llm_stats_json = None
        analytics.llm_prompt_tokens = None
        analytics.llm_completion_tokens = None
        analytics.llm_total_tokens = None
        analytics.llm_peak_memory_mb = None
        
        # Reset state to PENDING
        analytics.state = 'PENDING'
        analytics.error_message = None
        analytics.retry_count = 0

        db.query(Job).filter(
            Job.file_id == file_id,
            Job.kind.in_(['TRANSCRIBE', 'ANALYZE'])
        ).delete()

        from utils.uuid_helper import generate_uuid
        job = Job(
            id=generate_uuid(),
            file_id=file_id,
            kind='TRANSCRIBE',
            state='QUEUED',
            priority=900,
            created_at=datetime.utcnow()
        )
        db.add(job)
        queued_count += 1

    db.commit()

    return {
        "success": True,
        "queued": queued_count,
        "skipped": skipped_count,
        "message": f"Queued {queued_count} file(s) for re-transcription"
    }


@router.post("/settings/cache/update")
@handle_api_errors("Update local analytics cache")
def update_local_analytics_cache(db: Session = Depends(get_db)):
    """
    Trigger update of local analytics cache.
    Scans for files that need to be cached and copies them.
    """
    from services.analytics_service import AnalyticsService
    
    service = AnalyticsService(db)
    result = service.update_local_cache()
    
    if 'error' in result:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=result['error']
        )
        
    return {
        "success": True,
        "stats": result,
        "message": f"Cache update complete: {result['processed']} processed, {result['skipped']} skipped, {result['failed']} failed"
    }


@router.post("/bulk-re-analyze")
@handle_api_errors("Bulk re-analyze")
def bulk_reanalyze_files(request: BulkOperationRequest, db: Session = Depends(get_db)):
    """
    Re-analyze multiple files at once.
    """
    from models import File, Job
    from datetime import datetime

    if not request.file_ids:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="No file IDs provided"
        )

    queued_count = 0
    skipped_count = 0

    for file_id in request.file_ids:
        analytics = db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file_id
        ).first()

        if not analytics or not analytics.transcript:
            skipped_count += 1
            continue

        existing_job = db.query(Job).filter(
            Job.file_id == file_id,
            Job.kind == 'ANALYZE',
            Job.state.in_(['QUEUED', 'RUNNING'])
        ).first()

        if existing_job:
            existing_job.priority = 900
            existing_job.created_at = datetime.utcnow()
        else:
            from utils.uuid_helper import generate_uuid
            job = Job(
                id=generate_uuid(),
                file_id=file_id,
                kind='ANALYZE',
                state='QUEUED',
                priority=900,
                created_at=datetime.utcnow()
            )
            db.add(job)

            if analytics.state in ['TRANSCRIBED', 'FAILED']:
                analytics.state = 'TRANSCRIBED'
                analytics.error_message = None

        queued_count += 1

    db.commit()

    return {
        "success": True,
        "queued": queued_count,
        "skipped": skipped_count,
        "message": f"Queued {queued_count} file(s) for re-analysis"
    }


class BulkUpdateFieldRequest(BaseModel):
    """Request for bulk field updates on analytics records"""
    file_ids: List[str]
    value: str


@router.post("/bulk-update-faculty")
@handle_api_errors("Bulk update faculty")
def bulk_update_faculty(request: BulkUpdateFieldRequest, db: Session = Depends(get_db)):
    """
    Update faculty for multiple analytics records at once.
    """
    VALID_FACULTIES = [
        'N/A', 'Humanities', 'English', 'Commerce', 'PE', 
        'Languages', 'Visual Arts', 'Sciences', 'Music'
    ]
    
    if request.value not in VALID_FACULTIES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Invalid faculty value. Must be one of: {', '.join(VALID_FACULTIES)}"
        )

    if not request.file_ids:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="No file IDs provided"
        )

    updated_count = 0
    skipped_count = 0

    for file_id in request.file_ids:
        analytics = db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file_id
        ).first()

        if not analytics:
            skipped_count += 1
            continue

        analytics.faculty = request.value
        updated_count += 1

    db.commit()

    return {
        "success": True,
        "updated": updated_count,
        "skipped": skipped_count,
        "message": f"Updated faculty to '{request.value}' for {updated_count} file(s)"
    }


@router.post("/bulk-update-content-type")
@handle_api_errors("Bulk update content type")
def bulk_update_content_type(request: BulkUpdateFieldRequest, db: Session = Depends(get_db)):
    """
    Update content type for multiple analytics records at once.
    """
    VALID_CONTENT_TYPES = [
        'Guidance & Information', 'Promotional', 'Learning Content',
        'Student Work', 'Out-take/Noise', 'Announcements'
    ]
    
    if request.value not in VALID_CONTENT_TYPES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Invalid content type value. Must be one of: {', '.join(VALID_CONTENT_TYPES)}"
        )

    if not request.file_ids:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="No file IDs provided"
        )

    updated_count = 0
    skipped_count = 0

    for file_id in request.file_ids:
        analytics = db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file_id
        ).first()

        if not analytics:
            skipped_count += 1
            continue

        analytics.content_type = request.value
        updated_count += 1

    db.commit()

    return {
        "success": True,
        "updated": updated_count,
        "skipped": skipped_count,
        "message": f"Updated content type to '{request.value}' for {updated_count} file(s)"
    }