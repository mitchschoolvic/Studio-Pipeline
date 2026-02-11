"""
Waveform API Endpoints

Serves pre-generated waveform JSON files for frontend canvas visualization.
Supports on-demand generation when kiosk clients request waveforms that haven't
been generated yet (self-healing for any missed pipeline triggers).
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path

from models import File
from database import get_db, SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter()

# Persistent waveform storage directory
WAVEFORM_DIR = Path.home() / "Library/Application Support/StudioPipeline/waveforms"

# Track in-flight generation tasks to avoid duplicates
_generating_tasks: set = set()


@router.get("/waveforms/{file_id}")
async def get_waveform(file_id: str, db: Session = Depends(get_db)):
    """
    Get waveform peaks JSON for a file.
    
    Returns:
        JSON file with peaks array for Wavesurfer.js
        
    Response Codes:
        200: Waveform ready
        202: Waveform still generating
        404: File not found or waveform unavailable
    """
    file = db.query(File).filter(File.id == file_id).first()
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    if file.waveform_state == 'READY' and file.waveform_path:
        waveform_path = Path(file.waveform_path)
        if waveform_path.exists():
            return FileResponse(
                str(waveform_path),
                media_type='application/json',
                headers={
                    "Cache-Control": "public, max-age=31536000",  # 1 year (waveforms are immutable)
                }
            )
        else:
            # Path exists in DB but file is missing — reset to PENDING for backfill
            logger.warning(f"Waveform file missing for {file_id}, resetting to PENDING")
            file.waveform_state = 'PENDING'
            file.waveform_path = None
            db.commit()
            raise HTTPException(status_code=202, detail="Waveform generation pending")
    
    elif file.waveform_state == 'GENERATING':
        raise HTTPException(status_code=202, detail="Waveform is being generated")
    
    elif file.waveform_state in ('PENDING', 'FAILED'):
        # On-demand generation: trigger waveform creation when a kiosk client requests it
        # This self-heals if the pipeline trigger was missed
        if file_id not in _generating_tasks:
            audio_path = _find_audio_source(file)
            if audio_path:
                _generating_tasks.add(file_id)
                asyncio.create_task(_on_demand_generate(file_id, audio_path))
                logger.info(f"On-demand waveform generation triggered for {file.filename}")
            else:
                raise HTTPException(status_code=404, detail="No audio source available for waveform generation")
        raise HTTPException(status_code=202, detail="Waveform generation in progress")
    
    else:
        raise HTTPException(status_code=404, detail="Unknown waveform state")


def _find_audio_source(file: File) -> str | None:
    """Find the best available audio/video source for waveform generation."""
    for candidate in [file.path_final, file.path_processed]:
        if candidate and Path(candidate).exists():
            return candidate
    return None


async def _on_demand_generate(file_id: str, audio_path: str):
    """Generate waveform on-demand when requested by a kiosk client."""
    from services.waveform_generator import WaveformGenerator

    try:
        WAVEFORM_DIR.mkdir(parents=True, exist_ok=True)
        generator = WaveformGenerator(str(WAVEFORM_DIR))

        # Use separate DB session for thread-safe generation
        waveform_db = SessionLocal()
        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                generator.generate_waveform,
                file_id,
                audio_path,
                waveform_db
            )
        finally:
            waveform_db.close()

        if success:
            logger.info(f"On-demand waveform ready for {file_id}")
            try:
                from services.websocket import manager
                await manager.send_waveform_update(file_id, 'READY')
            except Exception:
                pass
        else:
            logger.warning(f"On-demand waveform generation failed for {file_id}")
    except Exception as e:
        logger.error(f"On-demand waveform generation error for {file_id}: {e}")
    finally:
        _generating_tasks.discard(file_id)


@router.get("/waveforms/{file_id}/status")
async def get_waveform_status(file_id: str, db: Session = Depends(get_db)):
    """
    Get waveform generation status for a file.
    
    Returns:
        JSON with state and optional error message
    """
    file = db.query(File).filter(File.id == file_id).first()
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    return {
        "file_id": file_id,
        "waveform_state": file.waveform_state,
        "waveform_error": file.waveform_error,
        "waveform_generated_at": file.waveform_generated_at.isoformat() if file.waveform_generated_at else None
    }


@router.post("/waveforms/backfill")
async def backfill_waveforms(db: Session = Depends(get_db)):
    """
    Trigger waveform generation for all completed program files missing waveforms.
    
    Finds files that are:
    - Marked as program output (is_program_output=True)
    - Completed processing (status='completed')
    - Missing waveform (waveform_state IN ('PENDING', 'FAILED'))
    - Have a valid audio/video file on disk
    
    Returns count of files queued for generation.
    """
    from services.waveform_generator import WaveformGenerator
    
    # Find all files needing waveforms
    pending_files = db.query(File).filter(
        File.is_program_output == True,
        File.state == 'COMPLETED',
        File.waveform_state.in_(['PENDING', 'FAILED']),
    ).all()
    
    if not pending_files:
        return {"queued": 0, "message": "All waveforms are up to date"}
    
    # Ensure waveform directory exists
    WAVEFORM_DIR.mkdir(parents=True, exist_ok=True)
    generator = WaveformGenerator(str(WAVEFORM_DIR))
    
    queued = 0
    skipped = 0
    
    for file in pending_files:
        # Find the best available audio source
        audio_path = None
        for candidate in [file.path_final, file.path_processed]:
            if candidate and Path(candidate).exists():
                audio_path = candidate
                break
        
        if not audio_path:
            logger.debug(f"Skipping waveform backfill for {file.filename}: no audio file on disk")
            skipped += 1
            continue
        
        # Generate synchronously in small batches (waveform gen is fast ~1-2s each)
        success = generator.generate_waveform(file.id, audio_path, db)
        if success:
            queued += 1
            logger.info(f"Backfilled waveform for {file.filename}")
        else:
            skipped += 1
    
    return {
        "queued": queued,
        "skipped": skipped,
        "total": len(pending_files),
        "message": f"Generated {queued} waveforms, skipped {skipped}"
    }
