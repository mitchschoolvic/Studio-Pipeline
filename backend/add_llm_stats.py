#!/usr/bin/env python3
"""
Add LLM statistics columns to FileAnalytics table.
"""
import sys
from sqlalchemy import text
from database import engine

def add_llm_stats_columns():
    """Add LLM statistics columns to file_analytics table"""

    columns_to_add = [
        ("llm_prompt_tokens", "INTEGER"),
        ("llm_completion_tokens", "INTEGER"),
        ("llm_total_tokens", "INTEGER"),
        ("llm_peak_memory_mb", "REAL"),
    ]

    with engine.connect() as conn:
        for column_name, column_type in columns_to_add:
            try:
                # Check if column exists
                result = conn.execute(text(f"PRAGMA table_info(file_analytics)"))
                columns = [row[1] for row in result]

                if column_name not in columns:
                    print(f"Adding column: {column_name} ({column_type})")
                    conn.execute(text(f"ALTER TABLE file_analytics ADD COLUMN {column_name} {column_type}"))
                    conn.commit()
                    print(f"✅ Added {column_name}")
                else:
                    print(f"ℹ️  Column {column_name} already exists")
            except Exception as e:
                print(f"❌ Error adding {column_name}: {e}")
                conn.rollback()

    print("\n✅ LLM statistics columns migration complete!")

if __name__ == "__main__":
    add_llm_stats_columns()
