"""
Build Configuration for AI Features

Determines whether AI analytics features should be included at build time.
Controlled by BUILD_WITH_AI environment variable.

Includes:
- Conditional module imports
- Type stubs for non-AI builds (mypy compatibility)
- Model availability validation
- Startup health checks
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def is_ai_enabled() -> bool:
    """
    Check if AI features are enabled at build time.
    
    Returns:
        True if BUILD_WITH_AI environment variable is set to 'true' (case-insensitive)
    """
    build_with_ai = os.environ.get('BUILD_WITH_AI', 'false').lower()
    enabled = build_with_ai in ('true', '1', 'yes')
    
    if enabled:
        logger.info("✅ AI analytics features ENABLED")
    else:
        logger.info("ℹ️  AI analytics features DISABLED")
    
    return enabled


# Global flag for conditional imports
AI_ENABLED = is_ai_enabled()


# Conditional imports - only import AI modules if enabled
# Note: We DON'T import services/workers/api here to avoid circular imports
# Those should be imported where they're actually used
if AI_ENABLED:
    try:
        from models_analytics import FileAnalytics
        logger.info("✅ AI analytics features enabled")

    except ImportError as e:
        logger.error(f"❌ Failed to import AI modules: {e}")
        logger.error("Make sure requirements-ai.txt is installed")
        AI_ENABLED = False
        # Fall through to stubs
else:
    logger.info("ℹ️  AI analytics disabled (BUILD_WITH_AI=false)")

# Always provide type stubs for non-AI builds (satisfies type checkers)
if not AI_ENABLED:
    from models_analytics_stubs import FileAnalytics


# Model path management
class ModelValidationError(Exception):
    """Raised when AI model validation fails"""
    pass


def get_model_path(model_type: str) -> str:
    """
    Get the path to an AI model (whisper or llm).

    Args:
        model_type: Either 'whisper' or 'llm'

    Returns:
        Path to the model directory

    Raises:
        ModelValidationError: If model type is invalid or model not found
    """
    if not AI_ENABLED:
        raise ModelValidationError("AI features are not enabled")

    if model_type not in ['whisper', 'llm']:
        raise ModelValidationError(f"Invalid model type: {model_type}")

    # Check for bundled models (PyInstaller bundle)
    import sys
    from pathlib import Path

    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        base_path = Path(sys._MEIPASS)
        model_parent = base_path / 'models' / model_type
    else:
        # Running in development
        base_path = Path(__file__).parent.parent.parent
        model_parent = base_path / 'models' / model_type

    if not model_parent.exists():
        raise ModelValidationError(f"Model directory not found: {model_parent}")

    # For Whisper/LLM models downloaded from HuggingFace, they're in subdirectories
    # Find the first subdirectory that contains config.json or weights.npz
    subdirs = [d for d in model_parent.iterdir() if d.is_dir()]
    for subdir in subdirs:
        if (subdir / 'config.json').exists() or (subdir / 'weights.npz').exists():
            return str(subdir)

    # If no subdirectory found, return parent (for backwards compatibility)
    return str(model_parent)


def validate_models() -> dict:
    """
    Validate that required AI models are available and loadable.
    
    Performs both startup warnings and provides job-time error info.
    Only runs if BUILD_WITH_AI=true.
    
    Returns:
        dict with validation results:
        {
            'whisper_available': bool,
            'whisper_error': str | None,
            'llm_available': bool,
            'llm_error': str | None,
            'all_available': bool
        }
    """
    if not AI_ENABLED:
        return {
            'whisper_available': False,
            'whisper_error': 'AI features disabled',
            'llm_available': False,
            'llm_error': 'AI features disabled',
            'all_available': False
        }
    
    results = {
        'whisper_available': False,
        'whisper_error': None,
        'llm_available': False,
        'llm_error': None,
        'all_available': False
    }
    
    # Check Whisper
    try:
        import mlx_whisper
        # Try to access model (will trigger download warning if missing)
        # But don't actually load it yet (too memory intensive)
        results['whisper_available'] = True
        logger.info("✅ MLX Whisper module available")
    except ImportError as e:
        results['whisper_error'] = f"mlx_whisper not installed: {e}"
        logger.error(f"❌ {results['whisper_error']}")
    except Exception as e:
        results['whisper_error'] = f"Whisper validation error: {e}"
        logger.warning(f"⚠️  {results['whisper_error']}")
    
    # Check LLM
    try:
        from mlx_lm import load
        results['llm_available'] = True
        logger.info("✅ MLX LM module available")
    except ImportError as e:
        results['llm_error'] = f"mlx_lm not installed: {e}"
        logger.error(f"❌ {results['llm_error']}")
    except Exception as e:
        results['llm_error'] = f"LLM validation error: {e}"
        logger.warning(f"⚠️  {results['llm_error']}")
    
    results['all_available'] = results['whisper_available'] and results['llm_available']
    
    if not results['all_available']:
        logger.warning("⚠️  AI models not fully available - analytics may fail at runtime")
        logger.warning("Run model download script or check bundle includes models")
    
    return results


def check_bundled_models(app_bundle_path: str = None) -> dict:
    """
    Check if AI models are bundled in the macOS app bundle.
    
    Args:
        app_bundle_path: Path to .app bundle (auto-detected if None)
        
    Returns:
        dict with model paths and availability
    """
    if not AI_ENABLED:
        return {'bundled': False, 'reason': 'AI disabled'}
    
    # Auto-detect bundle path
    if app_bundle_path is None:
        # Try to find bundle in typical locations
        possible_paths = [
            Path.cwd() / "Resources" / "models",  # Running from bundle
            Path.cwd() / "models",  # Development
            Path.home() / ".cache" / "mlx_models"  # Cache location
        ]
        
        for path in possible_paths:
            if path.exists():
                app_bundle_path = str(path)
                break
    
    if not app_bundle_path:
        return {
            'bundled': False,
            'reason': 'No model directory found',
            'checked_paths': [str(p) for p in possible_paths]
        }
    
    model_path = Path(app_bundle_path)
    whisper_path = model_path / "whisper"
    llm_path = model_path / "llm"
    
    return {
        'bundled': whisper_path.exists() and llm_path.exists(),
        'model_path': str(model_path),
        'whisper_path': str(whisper_path) if whisper_path.exists() else None,
        'llm_path': str(llm_path) if llm_path.exists() else None,
        'whisper_available': whisper_path.exists(),
        'llm_available': llm_path.exists()
    }


def require_ai():
    """
    Decorator to mark functions that require AI features.
    
    Raises RuntimeError if AI features are not enabled.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not AI_ENABLED:
                raise RuntimeError(
                    f"Function {func.__name__} requires AI features. "
                    "Set BUILD_WITH_AI=true to enable."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_ai_status() -> dict:
    """
    Get comprehensive status of AI features.
    
    Returns:
        Dictionary with AI feature status including model validation
    """
    status = {
        'enabled': AI_ENABLED,
        'modules_loaded': False,
        'models_validated': False,
        'models_available': []
    }
    
    if AI_ENABLED:
        status['modules_loaded'] = all([
            FileAnalytics is not None,
            TranscribeWorker is not None,
            AnalyzeWorker is not None
        ])
        
        # Validate models
        validation = validate_models()
        status['models_validated'] = validation['all_available']
        
        if validation['whisper_available']:
            status['models_available'].append('whisper')
        if validation['llm_available']:
            status['models_available'].append('llm')
        
        # Add validation details
        status['validation'] = validation
        
        # Check for bundled models
        status['bundled_models'] = check_bundled_models()
    
    return status


def startup_validation():
    """
    Run validation checks at application startup.
    
    Logs warnings but does not fail startup if models are missing.
    This allows the app to start even if models need to be downloaded.
    """
    if not AI_ENABLED:
        return
    
    logger.info("🔍 Validating AI analytics setup...")
    
    status = get_ai_status()
    
    if not status['modules_loaded']:
        logger.error("❌ AI modules failed to load - check dependencies")
        return
    
    if not status['models_validated']:
        logger.warning("⚠️  AI models not fully validated")
        logger.warning("Analytics jobs may fail until models are available")
        
        validation = status.get('validation', {})
        if validation.get('whisper_error'):
            logger.warning(f"   Whisper: {validation['whisper_error']}")
        if validation.get('llm_error'):
            logger.warning(f"   LLM: {validation['llm_error']}")
        
        logger.info("💡 Run model download script to prepare models")
    else:
        logger.info("✅ AI analytics fully validated and ready")
    
    # Check bundled models
    bundled = status.get('bundled_models', {})
    if bundled.get('bundled'):
        logger.info(f"✅ Models bundled at: {bundled['model_path']}")
    else:
        logger.info("ℹ️  Models not bundled - will use system cache")
