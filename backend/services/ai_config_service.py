"""
AI Configuration Service

Manages AI prompts and settings that can be edited via GUI.
Stores configuration in database settings table.
"""
import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models import Setting

logger = logging.getLogger(__name__)


class AIConfigService:
    """
    Service for managing AI configuration.
    
    Handles:
    - LLM analysis prompts (editable in GUI)
    - Whisper transcription settings
    - Model versions
    """
    
    # Default configurations
    DEFAULT_SYSTEM_PROMPT = """You are a JSON-only response assistant. You must respond ONLY with valid JSON, no other text."""

    DEFAULT_USER_PROMPT = """Analyze this video transcript and thumbnail image, then return ONLY valid JSON (no other text):

Transcript: {transcript}

Filename: {filename}
Duration: {duration}s
Date: {recording_date}

Return this exact JSON structure:
{{
    "image_description": "description of what you see in the thumbnail",
    "number_of_people_in_image": "1",
    "estimated_age_of_people": "30s",
    "video_title": "descriptive title",
    "short_description": "2-3 sentence summary",
    "content_type": "Promotional/Learning Content/Lecture/Tutorial/Presentation/Discussion/Other",
    "faculty": "Sciences/Mathematics/Humanities/Arts/Languages/Technology/General",
    "audience_type": ["Student", "Staff", "Parent"],
    "speaker_type": ["Staff", "Student"],
    "speaker_confidence": {{"Staff": 0.8, "Student": 0.2}},
    "rationale_short": "why you categorized this way"
}}

Rules:
- Output ONLY JSON, nothing else
- speaker_confidence must sum to 1.0
- Arrays must use brackets []
- number_of_people_in_image should be a string representing the count"""

    # Legacy combined prompt for backwards compatibility
    DEFAULT_ANALYSIS_PROMPT = """You are an educational content analyzer. Analyze this video transcript and extract the following information in JSON format:

Video Transcript:
{transcript}

Video Filename: {filename}
Video Duration: {duration} seconds
Recording Date: {recording_date}

Extract and return ONLY valid JSON with these fields:
{{
    "title": "Brief descriptive title for the video (e.g., 'Year 12 Chemistry: Organic Reactions')",
    "description": "2-3 sentence description of the content",
    "content_type": "Category: 'Learning Content', 'Lecture', 'Tutorial', 'Presentation', 'Discussion', or 'Other'",
    "faculty": "Subject area: 'Sciences', 'Mathematics', 'Humanities', 'Arts', 'Languages', 'Technology', or 'General'",
    "speaker": "Who is speaking: 'Staff', 'Student', 'Student, Staff', or 'Multiple'",
    "audience": "Target audience: 'Student', 'Staff', 'Parent', or comma-separated combinations",
    "language": "Primary language (e.g., 'English', 'Spanish', 'Mandarin')",
    "speaker_count": Integer number of distinct speakers (1, 2, 3, etc.)
}}

Important:
- Be concise and accurate
- Return ONLY the JSON object, no other text
- If information cannot be determined, use reasonable defaults
- Title should be specific and educational"""
    
    DEFAULT_WHISPER_SETTINGS = {
        "translate_to_english": False,
        "language": None,  # Auto-detect
        "word_timestamps": False,
        "custom_dictionary": [],  # List of custom words/phrases (legacy)
        "prompt_words": "",  # Comma-separated prompt words for initial_prompt (e.g., "Haileybury, VCE, ATAR")
        "temperature": 0.0,  # Deterministic
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_system_prompt(self, version: str = "default") -> str:
        """
        Get LLM system prompt (chat template system message).

        Args:
            version: Prompt version identifier (default: "default")

        Returns:
            System prompt string
        """
        key = f"ai_system_prompt_{version}"
        setting = self.db.query(Setting).filter(Setting.key == key).first()

        if setting and setting.value:
            logger.info(f"✅ Retrieved system prompt (version: {version}), length: {len(setting.value)}, preview: {setting.value[:50]}")
            return setting.value

        # Return default if not found
        logger.warning(f"⚠️ No system prompt found for version '{version}', returning default (length: {len(self.DEFAULT_SYSTEM_PROMPT)})")
        return self.DEFAULT_SYSTEM_PROMPT

    def save_system_prompt(self, prompt: str, version: str = "default") -> None:
        """
        Save LLM system prompt.

        Args:
            prompt: System prompt string
            version: Prompt version identifier
        """
        key = f"ai_system_prompt_{version}"
        logger.info(f"💾 Saving system prompt (version: {version}), length: {len(prompt)}, preview: {prompt[:50]}")
        setting = self.db.query(Setting).filter(Setting.key == key).first()

        if setting:
            logger.info(f"   Updating existing setting (old length: {len(setting.value)})")
            setting.value = prompt
        else:
            logger.info(f"   Creating new setting")
            setting = Setting(key=key, value=prompt)
            self.db.add(setting)

        self.db.commit()
        logger.info(f"✅ Saved system prompt version: {version}")
        
        # Verify it was saved
        verify = self.db.query(Setting).filter(Setting.key == key).first()
        if verify:
            logger.info(f"   ✓ Verification: prompt saved successfully (length: {len(verify.value)})")
        else:
            logger.error(f"   ✗ Verification FAILED: prompt not found after save!")

    def get_user_prompt(self, version: str = "default") -> str:
        """
        Get LLM user prompt (chat template user message).

        Args:
            version: Prompt version identifier (default: "default")

        Returns:
            User prompt template string
        """
        key = f"ai_user_prompt_{version}"
        setting = self.db.query(Setting).filter(Setting.key == key).first()

        if setting and setting.value:
            logger.info(f"✅ Retrieved user prompt (version: {version}), length: {len(setting.value)}")
            return setting.value

        # Return default if not found
        logger.warning(f"⚠️ No user prompt found for version '{version}', returning default (length: {len(self.DEFAULT_USER_PROMPT)})")
        return self.DEFAULT_USER_PROMPT

    def save_user_prompt(self, prompt: str, version: str = "default") -> None:
        """
        Save LLM user prompt template.

        Args:
            prompt: User prompt template string
            version: Prompt version identifier
        """
        key = f"ai_user_prompt_{version}"
        logger.info(f"💾 Saving user prompt (version: {version}), length: {len(prompt)}")
        setting = self.db.query(Setting).filter(Setting.key == key).first()

        if setting:
            logger.info(f"   Updating existing setting (old length: {len(setting.value)})")
            setting.value = prompt
        else:
            logger.info(f"   Creating new setting")
            setting = Setting(key=key, value=prompt)
            self.db.add(setting)

        self.db.commit()
        logger.info(f"✅ Saved user prompt version: {version}")
        
        # Verify it was saved
        verify = self.db.query(Setting).filter(Setting.key == key).first()
        if verify:
            logger.info(f"   ✓ Verification: prompt saved successfully (length: {len(verify.value)})")
        else:
            logger.error(f"   ✗ Verification FAILED: prompt not found after save!")

    def get_analysis_prompt(self, version: str = "default") -> str:
        """
        Get LLM analysis prompt template (legacy combined format).

        Args:
            version: Prompt version identifier (default: "default")

        Returns:
            Prompt template string
        """
        key = f"ai_analysis_prompt_{version}"
        setting = self.db.query(Setting).filter(Setting.key == key).first()

        if setting and setting.value:
            return setting.value

        # Return default if not found
        return self.DEFAULT_ANALYSIS_PROMPT
    
    def save_analysis_prompt(self, prompt: str, version: str = "default") -> None:
        """
        Save LLM analysis prompt template.
        
        Args:
            prompt: Prompt template string
            version: Prompt version identifier
        """
        key = f"ai_analysis_prompt_{version}"
        setting = self.db.query(Setting).filter(Setting.key == key).first()
        
        if setting:
            setting.value = prompt
        else:
            setting = Setting(
                key=key,
                value=prompt,
                description=f"LLM analysis prompt template (version: {version})"
            )
            self.db.add(setting)
        
        self.db.commit()
        logger.info(f"✅ Saved analysis prompt version: {version}")
    
    def get_whisper_settings(self) -> Dict[str, Any]:
        """
        Get Whisper transcription settings.

        Returns:
            Dictionary of Whisper settings
        """
        setting = self.db.query(Setting).filter(
            Setting.key == 'ai_whisper_settings'
        ).first()

        settings = self.DEFAULT_WHISPER_SETTINGS.copy()

        if setting and setting.value:
            try:
                settings = json.loads(setting.value)
            except json.JSONDecodeError:
                logger.warning("Failed to parse Whisper settings, using defaults")

        # Check for separate translate_to_english checkbox setting
        translate_setting = self.db.query(Setting).filter(
            Setting.key == 'whisper_translate_to_english'
        ).first()

        if translate_setting:
            settings['translate_to_english'] = translate_setting.value.lower() in ('true', '1', 'yes')

        return settings
    
    def save_whisper_settings(self, settings: Dict[str, Any]) -> None:
        """
        Save Whisper transcription settings.
        
        Args:
            settings: Dictionary of Whisper settings
        """
        setting = self.db.query(Setting).filter(
            Setting.key == 'ai_whisper_settings'
        ).first()
        
        settings_json = json.dumps(settings, indent=2)
        
        if setting:
            setting.value = settings_json
        else:
            setting = Setting(
                key='ai_whisper_settings',
                value=settings_json
            )
            self.db.add(setting)
        
        self.db.commit()
        logger.info("✅ Saved Whisper settings")
    
    def get_model_versions(self) -> Dict[str, str]:
        """
        Get configured AI model versions.
        
        Returns:
            Dictionary mapping model type to version string
        """
        versions = {}
        
        # Whisper version
        whisper_setting = self.db.query(Setting).filter(
            Setting.key == 'ai_whisper_model_version'
        ).first()
        versions['whisper'] = whisper_setting.value if whisper_setting else 'mlx-community/whisper-small-mlx'
        
        # LLM version
        llm_setting = self.db.query(Setting).filter(
            Setting.key == 'ai_llm_model_version'
        ).first()
        versions['llm'] = llm_setting.value if llm_setting else 'mlx-community/Qwen2.5-3B-Instruct-4bit'
        
        return versions
    
    def initialize_defaults(self) -> None:
        """
        Initialize default AI configuration settings if they don't exist.

        Called during app startup.
        """
        defaults = [
            ('ai_system_prompt_default', self.DEFAULT_SYSTEM_PROMPT),
            ('ai_user_prompt_default', self.DEFAULT_USER_PROMPT),
            ('ai_analysis_prompt_default', self.DEFAULT_ANALYSIS_PROMPT),
            ('ai_whisper_settings', json.dumps(self.DEFAULT_WHISPER_SETTINGS)),
            ('ai_whisper_model_version', 'mlx-community/whisper-small-mlx'),
            ('ai_llm_model_version', 'mlx-community/Qwen2.5-3B-Instruct-4bit'),
            ('analytics_enabled', 'true'),
            ('analytics_schedule_enabled', 'true'),
            ('analytics_start_hour', '20'),
            ('analytics_end_hour', '6'),
            ('analytics_output_path', ''),
        ]

        for key, value in defaults:
            existing = self.db.query(Setting).filter(Setting.key == key).first()
            if not existing:
                setting = Setting(key=key, value=value)
                self.db.add(setting)

        self.db.commit()
        logger.info("✅ AI configuration defaults initialized")
    
    def get_all_settings(self) -> Dict[str, Any]:
        """
        Get all AI-related settings for GUI display.

        Returns:
            Dictionary of all AI settings
        """
        return {
            'system_prompt': self.get_system_prompt(),
            'user_prompt': self.get_user_prompt(),
            'analysis_prompt': self.get_analysis_prompt(),  # Legacy
            'whisper_settings': self.get_whisper_settings(),
            'model_versions': self.get_model_versions(),
            'enabled': self._get_setting_bool('analytics_enabled', True),
            'schedule': {
                'enabled': self._get_setting_bool('analytics_schedule_enabled', True),
                'start_hour': int(self._get_setting('analytics_start_hour', '20')),
                'end_hour': int(self._get_setting('analytics_end_hour', '6')),
            },
            'output_path': self._get_setting('analytics_output_path', ''),
        }
    
    def _get_setting(self, key: str, default: str = '') -> str:
        """Helper to get setting value"""
        setting = self.db.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else default
    
    def _get_setting_bool(self, key: str, default: bool = False) -> bool:
        """Helper to get boolean setting value"""
        value = self._get_setting(key, str(default).lower())
        return value.lower() in ('true', '1', 'yes')
