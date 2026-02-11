"""
Export analytics to Excel spreadsheet

This script exports all completed analytics records to an Excel file
using the schema-compliant format with all 17 required fields.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from database import SessionLocal
import models  # Import models first to load File class
from models_analytics import FileAnalytics

def export_to_excel():
    """Export analytics to Excel file"""
    
    db = SessionLocal()
    
    try:
        # Get all analytics records (not just completed)
        all_records = db.query(FileAnalytics).order_by(FileAnalytics.created_at.desc()).all()
        
        print("=" * 70)
        print("ANALYTICS EXCEL EXPORT")
        print("=" * 70)
        print(f"Total records found: {len(all_records)}")
        
        # Count by state
        by_state = {}
        for record in all_records:
            by_state[record.state] = by_state.get(record.state, 0) + 1
        
        print("\nRecords by state:")
        for state, count in sorted(by_state.items()):
            print(f"  {state}: {count}")
        
        if not all_records:
            print("\n⚠️  No records to export")
            return None
        
        # Convert to Excel format
        print("\n📊 Converting to Excel format...")
        excel_data = []
        for record in all_records:
            try:
                # Pass thumbnail path if available
                thumb_path = record.file.thumbnail_path if record.file else None
                row = record.to_excel_row(thumbnail_path=thumb_path)
                excel_data.append(row)
            except Exception as e:
                print(f"  ⚠️  Error converting record {record.id}: {e}")
        
        print(f"✅ Converted {len(excel_data)} records")
        
        # Try to export using pandas (if available)
        try:
            import pandas as pd
            
            # Create DataFrame
            df = pd.DataFrame(excel_data)
            
            # Reorder columns: schema fields with Transcript last
            schema_columns = [
                'Audience', 'Description', 'Duration', 'DurationSeconds',
                'Faculty', 'Filename', 'Language', 'Speaker', 'SpeakerCount',
                'StudioLocation', 'ThumbnailUrl', 'ThumbnailPath', 'Timestamp', 'TimestampSort',
                'Title', 'Type', 'VideoUrl', 'Transcript'  # Transcript moved to last
            ]
            
            # Ensure all schema columns exist
            for col in schema_columns:
                if col not in df.columns:
                    df[col] = ''
            
            # Reorder - only schema columns, no debug columns
            df = df[schema_columns]
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = Path(__file__).parent.parent / f'analytics_export_{timestamp}.xlsx'
            
            # Export to Excel
            print(f"\n💾 Exporting to: {output_file}")
            df.to_excel(output_file, index=False, engine='openpyxl')
            
            print("=" * 70)
            print("✅ EXPORT COMPLETE")
            print("=" * 70)
            print(f"File: {output_file}")
            print(f"Records: {len(excel_data)}")
            print(f"Columns: {len(schema_columns)} (all schema fields)")
            print("\nYou can now open this file in Excel to inspect the data.")
            
            return output_file
            
        except ImportError:
            print("\n⚠️  pandas and openpyxl not installed")
            print("Installing required packages...")
            
            import subprocess
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', 'pandas', 'openpyxl'
            ], check=True)
            
            print("\n✅ Packages installed. Please run the script again.")
            return None
    
    except Exception as e:
        print(f"\n❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        db.close()


def preview_data():
    """Preview the data that will be exported"""
    
    db = SessionLocal()
    
    try:
        # Get a sample record
        sample = db.query(FileAnalytics).filter(
            FileAnalytics.state == 'COMPLETED'
        ).first()
        
        if not sample:
            sample = db.query(FileAnalytics).first()
        
        if sample:
            print("\n" + "=" * 70)
            print("SAMPLE RECORD PREVIEW")
            print("=" * 70)
            
            # Pass thumbnail path if available
            thumb_path = sample.file.thumbnail_path if sample.file else None
            excel_row = sample.to_excel_row(thumbnail_path=thumb_path)
            
            print(f"\nFilename: {excel_row['Filename']}")
            print(f"State: {sample.state}")
            print("\nAll 17 schema fields (Transcript is last):")
            print("-" * 70)
            
            # Show columns in export order
            export_order = [
                'Audience', 'Description', 'Duration', 'DurationSeconds',
                'Faculty', 'Filename', 'Language', 'Speaker', 'SpeakerCount',
                'StudioLocation', 'ThumbnailUrl', 'ThumbnailPath', 'Timestamp', 'TimestampSort',
                'Title', 'Type', 'VideoUrl', 'Transcript'
            ]
            
            for key in export_order:
                value = excel_row[key]
                value_type = type(value).__name__
                
                # Truncate long values
                if isinstance(value, str) and len(value) > 50:
                    value_display = value[:50] + '...'
                else:
                    value_display = value
                
                print(f"{key:20s} ({value_type:5s}): {value_display}")
    
    finally:
        db.close()


if __name__ == '__main__':
    print("🚀 Starting analytics export...\n")
    
    # Preview data
    preview_data()
    
    # Export to Excel
    output_file = export_to_excel()
    
    if output_file:
        print(f"\n✨ Open the file: {output_file}")
