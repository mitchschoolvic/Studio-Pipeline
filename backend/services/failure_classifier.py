"""
Failure Classifier Service

Analyzes exceptions and classifies them into recovery-actionable categories.
This enables the recovery orchestrator to make intelligent retry decisions.
"""
import logging
from constants import FailureCategory

logger = logging.getLogger(__name__)


class FailureClassifier:
    """
    Classifies exceptions into recovery-actionable categories.
    
    The classifier examines the exception message and type to determine
    the appropriate FailureCategory, which drives recovery behavior.
    """
    
    # Keywords that indicate specific failure types
    FTP_CONNECTION_KEYWORDS = [
        'connection refused', 'connection reset', 'connection closed',
        'connection lost', 'connection error', 'cannot connect',
        'host unreachable', 'network unreachable', 'no route to host',
        'broken pipe', 'reset by peer', 'not connected'
    ]
    
    FTP_TIMEOUT_KEYWORDS = [
        'timeout', 'timed out', 'operation timed out', 'connection timed out'
    ]
    
    FTP_AUTH_KEYWORDS = [
        'authentication', 'login failed', 'access denied', '530',
        'invalid credentials', 'permission denied to login'
    ]
    
    FTP_MISSING_KEYWORDS = [
        'no longer exists', 'file not found', 'not found on ftp',
        '550 file', '550 no such', 'no such file', 'missing from ftp'
    ]
    
    FTP_TRANSFER_KEYWORDS = [
        'transfer interrupted', 'download failed', 'transfer failed',
        'disk disconnected', 'volume', 'mount', 'unmounted',
        'i/o error', 'io error', 'read error', 'write error'
    ]
    
    PROCESSING_RESOURCE_KEYWORDS = [
        'memory', 'oom', 'out of memory', 'cannot allocate',
        'resource exhausted', 'too many open files', 'process killed'
    ]
    
    PROCESSING_CORRUPT_KEYWORDS = [
        'corrupt', 'invalid', 'malformed', 'unsupported format',
        'cannot decode', 'invalid data', 'broken file'
    ]
    
    STORAGE_SPACE_KEYWORDS = [
        'no space', 'disk full', 'quota exceeded', 'not enough space',
        'insufficient space', 'storage full'
    ]
    
    STORAGE_PERMISSION_KEYWORDS = [
        'permission denied', 'access denied', 'not permitted',
        'operation not permitted', 'read-only', 'readonly'
    ]
    
    STORAGE_PATH_KEYWORDS = [
        'no such file or directory', 'path not found', 'directory not found',
        'output path', 'destination not', 'not accessible', 'not exist'
    ]
    
    @classmethod
    def classify(cls, exception: Exception, job_kind: str) -> tuple[FailureCategory, str]:
        """
        Analyze exception and return (category, cleaned_message)
        
        Args:
            exception: The exception that caused the failure
            job_kind: The job type ('COPY', 'PROCESS', 'ORGANIZE')
            
        Returns:
            Tuple of (FailureCategory, human-readable message)
        """
        error_msg = str(exception).lower()
        original_msg = str(exception)
        
        # Log for debugging
        logger.debug(f"Classifying failure for {job_kind}: {original_msg[:200]}")
        
        if job_kind == 'COPY':
            return cls._classify_copy_failure(error_msg, original_msg)
        elif job_kind == 'PROCESS':
            return cls._classify_process_failure(error_msg, original_msg)
        elif job_kind == 'ORGANIZE':
            return cls._classify_organize_failure(error_msg, original_msg)
        elif job_kind in ['TRANSCRIBE', 'ANALYZE']:
            return cls._classify_process_failure(error_msg, original_msg)
        else:
            return (FailureCategory.UNKNOWN, original_msg)
    
    @classmethod
    def _classify_copy_failure(cls, error_msg: str, original_msg: str) -> tuple[FailureCategory, str]:
        """Classify failures during COPY (FTP download) jobs"""
        
        # Check for timeout first (most specific)
        if any(kw in error_msg for kw in cls.FTP_TIMEOUT_KEYWORDS):
            return (FailureCategory.FTP_TIMEOUT, "Connection timed out while downloading")
        
        # Check for authentication issues
        if any(kw in error_msg for kw in cls.FTP_AUTH_KEYWORDS):
            return (FailureCategory.FTP_AUTH, "FTP authentication failed")
        
        # Check for file not found on FTP
        if any(kw in error_msg for kw in cls.FTP_MISSING_KEYWORDS):
            return (FailureCategory.FTP_FILE_MISSING, "File no longer exists on FTP server")
        
        # Check for connection issues
        if any(kw in error_msg for kw in cls.FTP_CONNECTION_KEYWORDS):
            return (FailureCategory.FTP_CONNECTION, "Lost connection to FTP server")
        
        # Check for transfer/disk issues
        if any(kw in error_msg for kw in cls.FTP_TRANSFER_KEYWORDS):
            return (FailureCategory.FTP_TRANSFER, "Transfer interrupted - storage may have disconnected")
        
        # Check for disk space
        if any(kw in error_msg for kw in cls.STORAGE_SPACE_KEYWORDS):
            return (FailureCategory.STORAGE_SPACE, "Insufficient disk space for download")
        
        # Default for copy failures - assume connection issue
        return (FailureCategory.FTP_TRANSFER, f"Download failed: {original_msg[:100]}")
    
    @classmethod
    def _classify_process_failure(cls, error_msg: str, original_msg: str) -> tuple[FailureCategory, str]:
        """Classify failures during PROCESS jobs"""
        
        # Check for resource exhaustion
        if any(kw in error_msg for kw in cls.PROCESSING_RESOURCE_KEYWORDS):
            return (FailureCategory.PROCESSING_RESOURCE, "Insufficient system resources for processing")
        
        # Check for corrupt/invalid input
        if any(kw in error_msg for kw in cls.PROCESSING_CORRUPT_KEYWORDS):
            return (FailureCategory.PROCESSING_CORRUPT, "Source file appears to be corrupted or invalid")
        
        # Check for disk space
        if any(kw in error_msg for kw in cls.STORAGE_SPACE_KEYWORDS):
            return (FailureCategory.STORAGE_SPACE, "Insufficient disk space for processing")
        
        # Check for storage path issues
        if any(kw in error_msg for kw in cls.STORAGE_PATH_KEYWORDS):
            return (FailureCategory.STORAGE_PATH, "Required file or directory not accessible")
        
        # Default for process failures
        return (FailureCategory.PROCESSING_ERROR, f"Processing failed: {original_msg[:100]}")
    
    @classmethod
    def _classify_organize_failure(cls, error_msg: str, original_msg: str) -> tuple[FailureCategory, str]:
        """Classify failures during ORGANIZE jobs"""
        
        # Check for permission issues first
        if any(kw in error_msg for kw in cls.STORAGE_PERMISSION_KEYWORDS):
            return (FailureCategory.STORAGE_PERMISSION, "Permission denied writing to output location")
        
        # Check for disk space
        if any(kw in error_msg for kw in cls.STORAGE_SPACE_KEYWORDS):
            return (FailureCategory.STORAGE_SPACE, "Insufficient disk space in output location")
        
        # Check for path issues
        if any(kw in error_msg for kw in cls.STORAGE_PATH_KEYWORDS):
            return (FailureCategory.STORAGE_PATH, "Output path not accessible - drive may be disconnected")
        
        # Default for organize failures
        return (FailureCategory.STORAGE_PATH, f"Failed to move file to output: {original_msg[:100]}")
    
    @classmethod
    def get_backoff_minutes(cls, category: FailureCategory, attempt: int) -> int:
        """
        Calculate backoff delay in minutes based on category and attempt number.
        
        Args:
            category: The failure category
            attempt: The recovery attempt number (1, 2, 3, ...)
            
        Returns:
            Number of minutes to wait before retry
        """
        # Base backoff: 2^attempt minutes (2, 4, 8, 16...)
        base_backoff = min(2 ** attempt, 60)  # Cap at 60 minutes
        
        # Adjust based on category
        if FailureCategory.requires_ftp(category):
            # FTP failures: shorter backoff since we wait for connection anyway
            return max(1, base_backoff // 2)
        
        if category == FailureCategory.PROCESSING_RESOURCE:
            # Resource exhaustion: longer backoff
            return min(base_backoff * 2, 120)
        
        if FailureCategory.requires_path_validation(category):
            # Storage issues: moderate backoff
            return base_backoff
        
        return base_backoff
