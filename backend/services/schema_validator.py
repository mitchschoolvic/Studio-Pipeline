from sqlalchemy import inspect, text
from database import engine
from config.ai_config import AI_ENABLED
import logging

logger = logging.getLogger(__name__)

class SchemaValidator:
    @staticmethod
    def check():
        """
        Check if the database schema is up to date.
        Returns:
            dict: {
                "valid": bool,
                "issues": list[str],
                "missing_tables": list[str],
                "missing_columns": list[str]
            }
        """
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        issues = []
        missing_tables = []
        missing_columns = []
        
        # Check 1: 'files' table exists
        if 'files' not in tables:
            missing_tables.append('files')
            issues.append("Missing 'files' table")
        else:
            # Check 2: 'queue_order' column in 'files'
            columns = [col['name'] for col in inspector.get_columns('files')]
            if 'queue_order' not in columns:
                missing_columns.append('files.queue_order')
                issues.append("Missing 'queue_order' column in 'files' table")

        # Check 3: 'file_analytics' table exists (if AI enabled)
        if AI_ENABLED:
            if 'file_analytics' not in tables:
                missing_tables.append('file_analytics')
                issues.append("Missing 'file_analytics' table (AI features enabled)")
            else:
                # Check for critical analytics columns if table exists
                # (We can add more specific column checks here if needed in future)
                pass
                
        valid = len(issues) == 0
        
        if not valid:
            logger.warning(f"Schema validation failed: {issues}")
        else:
            logger.info("✅ Database schema validation passed")
            
        return {
            "valid": valid,
            "issues": issues,
            "missing_tables": missing_tables,
            "missing_columns": missing_columns
        }
