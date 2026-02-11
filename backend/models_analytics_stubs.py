"""
Type stubs for AI analytics modules when AI is disabled.

These stubs allow type checkers to work correctly when BUILD_WITH_AI=false
while providing no-op implementations at runtime.
"""
from typing import Optional, Any, Dict, List
from datetime import datetime


class FileAnalytics:
    """Stub for FileAnalytics model"""
    id: str
    file_id: str
    state: str
    
    def __init__(self, **kwargs): ...
    def to_excel_row(self) -> Dict[str, Any]: ...


class TranscribeWorker:
    """Stub for TranscribeWorker"""
    def __init__(self, db): ...
    async def process_job(self, job) -> None: ...


class AnalyzeWorker:
    """Stub for AnalyzeWorker"""
    def __init__(self, db): ...
    async def process_job(self, job) -> None: ...


class AnalyticsService:
    """Stub for AnalyticsService"""
    def __init__(self, db): ...
    def queue_analytics_for_file(self, file) -> Optional[Any]: ...


class AnalyticsExcelService:
    """Stub for AnalyticsExcelService"""
    def __init__(self, db): ...
    async def export_to_excel(self) -> Optional[str]: ...


class AnalyticsScheduler:
    """Stub for AnalyticsScheduler"""
    def start(self) -> None: ...
    def stop(self) -> None: ...


# Module-level stubs
scheduler = AnalyticsScheduler()


def start_scheduler() -> None:
    """No-op stub for start_scheduler"""
    pass


def stop_scheduler() -> None:
    """No-op stub for stop_scheduler"""
    pass


# API router stub
class _RouterStub:
    """Stub for FastAPI router"""
    router = None


analytics_router = _RouterStub()


__all__ = [
    'FileAnalytics',
    'TranscribeWorker',
    'AnalyzeWorker',
    'AnalyticsService',
    'AnalyticsExcelService',
    'scheduler',
    'start_scheduler',
    'stop_scheduler',
    'analytics_router',
]
