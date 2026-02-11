"""
Path validation service - ensures working directories are accessible
"""
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class PathValidator:
    """Validates and monitors file system paths for accessibility"""
    
    @staticmethod
    def validate_path(path_str: str, path_type: str = "directory") -> Tuple[bool, Optional[str]]:
        """
        Validate a path exists and is accessible
        
        Args:
            path_str: Path string to validate
            path_type: Type of path - "directory" or "file"
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if not path_str or not path_str.strip():
                return False, f"{path_type.capitalize()} path is empty"
            
            path = Path(path_str).expanduser().resolve()
            
            if path_type == "directory":
                # Check if directory exists
                if not path.exists():
                    return False, f"Directory does not exist: {path}"
                
                if not path.is_dir():
                    return False, f"Path is not a directory: {path}"
                
                # Check if directory is writable
                test_file = path / '.write_test'
                try:
                    test_file.write_text('test')
                    test_file.unlink()
                except Exception as e:
                    return False, f"Directory is not writable: {path} - {str(e)}"
            
            elif path_type == "file":
                # Check if file exists
                if not path.exists():
                    return False, f"File does not exist: {path}"
                
                if not path.is_file():
                    return False, f"Path is not a file: {path}"
                
                # Check if file is readable
                try:
                    path.read_bytes()
                except Exception as e:
                    return False, f"File is not readable: {path} - {str(e)}"
            
            return True, None
            
        except Exception as e:
            return False, f"Path validation error: {str(e)}"
    
    @staticmethod
    def ensure_directory(path_str: str) -> Tuple[bool, Optional[str], Optional[Path]]:
        """
        Ensure a directory exists and is writable, creating if necessary
        
        Args:
            path_str: Directory path string
            
        Returns:
            Tuple of (success, error_message, resolved_path)
        """
        try:
            if not path_str or not path_str.strip():
                return False, "Directory path is empty", None
            
            path = Path(path_str).expanduser().resolve()
            
            # Create directory if it doesn't exist
            path.mkdir(parents=True, exist_ok=True)
            
            # Test write access
            test_file = path / '.write_test'
            try:
                test_file.write_text('test')
                test_file.unlink()
            except Exception as e:
                return False, f"Directory is not writable: {path} - {str(e)}", path
            
            return True, None, path
            
        except Exception as e:
            return False, f"Failed to create/access directory: {str(e)}", None
    
    @staticmethod
    def verify_file_exists(path_str: str, min_size_bytes: int = 0) -> Tuple[bool, Optional[str]]:
        """
        Verify a file exists and optionally check minimum size
        
        Args:
            path_str: File path string
            min_size_bytes: Minimum expected file size in bytes (0 = no check)
            
        Returns:
            Tuple of (exists, error_message)
        """
        try:
            if not path_str or not path_str.strip():
                return False, "File path is empty"
            
            path = Path(path_str).expanduser().resolve()
            
            if not path.exists():
                return False, f"File does not exist: {path}"
            
            if not path.is_file():
                return False, f"Path is not a file: {path}"
            
            # Check file size if minimum specified
            if min_size_bytes > 0:
                actual_size = path.stat().st_size
                if actual_size < min_size_bytes:
                    return False, f"File is smaller than expected: {actual_size} < {min_size_bytes} bytes"
            
            return True, None
            
        except Exception as e:
            return False, f"File verification error: {str(e)}"
    
    @staticmethod
    def validate_workspace_paths(temp_path: str, output_path: str) -> Tuple[bool, list]:
        """
        Validate both temp and output paths are accessible
        
        Args:
            temp_path: Temporary processing directory
            output_path: Final output directory
            
        Returns:
            Tuple of (all_valid, list_of_errors)
        """
        errors = []
        
        # Validate temp path
        temp_valid, temp_error, _ = PathValidator.ensure_directory(temp_path)
        if not temp_valid:
            errors.append(f"Temp path invalid: {temp_error}")
            logger.error(f"Temp path validation failed: {temp_error}")
        
        # Validate output path
        output_valid, output_error, _ = PathValidator.ensure_directory(output_path)
        if not output_valid:
            errors.append(f"Output path invalid: {output_error}")
            logger.error(f"Output path validation failed: {output_error}")
        
        all_valid = temp_valid and output_valid
        
        if all_valid:
            logger.info(f"Workspace paths validated: temp={temp_path}, output={output_path}")
        
        return all_valid, errors


# Global singleton instance
path_validator = PathValidator()
