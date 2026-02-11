"""
Thumbnail Generator Service

Generates video thumbnails using native macOS tools (qlmanage/QuickLook).
Fast, hardware-accelerated, non-blocking thumbnail generation.
"""

import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from models import File

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """
    Generates video thumbnails using native macOS QuickLook.
    
    Uses qlmanage for fast, hardware-accelerated thumbnail generation.
    Handles empty files with placeholder images.
    """
    
    def __init__(self, thumbnail_dir: str, size: int = 320):
        """
        Initialize thumbnail generator.
        
        Args:
            thumbnail_dir: Directory to store generated thumbnails
            size: Thumbnail width in pixels (default 320)
        """
        self.thumbnail_dir = Path(thumbnail_dir)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        self.size = size
        self.placeholder_path = self.thumbnail_dir / "placeholder_empty.jpg"
        
        # Create placeholder on initialization
        if not self.placeholder_path.exists():
            self._create_placeholder_image()
    
    def generate_thumbnail(self, file_id: str, video_path: str, db: Session) -> bool:
        """
        Generate thumbnail for a video file using QuickLook.
        
        Args:
            file_id: File UUID
            video_path: Path to video file
            db: Database session
            
        Returns:
            True if successful, False otherwise
        """
        file = db.query(File).filter(File.id == file_id).first()
        if not file:
            logger.error(f"File {file_id} not found in database")
            return False
        
        # Handle empty files - use placeholder
        if file.is_empty:
            logger.info(f"File {file.filename} is empty, using placeholder")
            file.thumbnail_path = str(self.placeholder_path)
            file.thumbnail_state = 'READY'
            file.thumbnail_generated_at = datetime.utcnow()
            db.commit()
            return True
        
        # Check if video exists
        video_path = Path(video_path)
        if not video_path.exists():
            logger.warning(f"Video file not found: {video_path}")
            file.thumbnail_state = 'FAILED'
            file.thumbnail_error = "Video file not found"
            db.commit()
            return False
        
        # Set generating state
        file.thumbnail_state = 'GENERATING'
        db.commit()
        
        try:
            # Generate thumbnail using qlmanage (QuickLook)
            thumbnail_filename = f"{file_id}.jpg"
            thumbnail_path = self.thumbnail_dir / thumbnail_filename
            
            # qlmanage generates a PNG file with .png appended to original name
            # We'll convert it to JPG after generation
            logger.info(f"Generating thumbnail for {file.filename} using qlmanage")
            
            result = subprocess.run([
                'qlmanage',
                '-t',  # Generate thumbnail
                '-s', str(self.size),  # Size: width in pixels
                '-o', str(self.thumbnail_dir),  # Output directory
                str(video_path)
            ], capture_output=True, timeout=15, text=True)
            
            if result.returncode != 0:
                error_msg = result.stderr or "Unknown error"
                raise Exception(f"qlmanage failed: {error_msg}")
            
            # qlmanage creates file with .png extension appended
            # Find the generated file
            generated_file = self.thumbnail_dir / f"{video_path.name}.png"
            
            if not generated_file.exists():
                # Sometimes qlmanage uses different naming
                # Look for any .png file created in the last few seconds
                import time
                now = time.time()
                for png_file in self.thumbnail_dir.glob("*.png"):
                    if now - png_file.stat().st_mtime < 20:  # Created in last 20 seconds
                        generated_file = png_file
                        break
            
            if generated_file.exists():
                # Convert PNG to JPG to save space
                try:
                    result = subprocess.run([
                        'sips',
                        '-s', 'format', 'jpeg',
                        '-s', 'formatOptions', '85',  # 85% quality
                        str(generated_file),
                        '--out', str(thumbnail_path)
                    ], capture_output=True, timeout=10)
                    
                    if result.returncode == 0:
                        generated_file.unlink()  # Remove PNG
                    else:
                        # If conversion fails, just rename PNG to JPG
                        generated_file.rename(thumbnail_path)
                except Exception as convert_error:
                    logger.warning(f"Could not convert PNG to JPG: {convert_error}")
                    # Fallback: just use the PNG
                    generated_file.rename(thumbnail_path.with_suffix('.png'))
                    thumbnail_path = thumbnail_path.with_suffix('.png')
            else:
                raise Exception("qlmanage did not generate thumbnail file")
            
            # Verify thumbnail was created
            if not thumbnail_path.exists():
                raise Exception("Thumbnail file not found after generation")
            
            # Update database
            file.thumbnail_path = str(thumbnail_path)
            file.thumbnail_state = 'READY'
            file.thumbnail_generated_at = datetime.utcnow()
            file.thumbnail_error = None
            db.commit()
            
            logger.info(f"✅ Thumbnail generated for {file.filename}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"Thumbnail generation timed out for {file.filename}")
            file.thumbnail_state = 'FAILED'
            file.thumbnail_error = "Generation timed out"
            db.commit()
            return False
            
        except Exception as e:
            logger.error(f"Thumbnail generation failed for {file.filename}: {e}")
            file.thumbnail_state = 'FAILED'
            file.thumbnail_error = str(e)
            db.commit()
            return False
    
    def _create_placeholder_image(self):
        """
        Create a grey placeholder image for empty files.
        Uses PIL if available, falls back to system tools.
        """
        logger.info("Creating placeholder image for empty files")
        
        try:
            # Try using PIL first (better quality)
            from PIL import Image, ImageDraw, ImageFont
            
            # Create grey rectangle with 16:9 aspect ratio
            width = self.size
            height = int(width * 9 / 16)
            img = Image.new('RGB', (width, height), color='#CCCCCC')
            draw = ImageDraw.Draw(img)
            
            # Add "Empty File" text
            try:
                # Try to use system font
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
            except:
                # Fallback to default font
                font = ImageFont.load_default()
            
            text = "Empty File"
            
            # Get text bounding box for centering
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Center text
            position = ((width - text_width) // 2, (height - text_height) // 2)
            draw.text(position, text, fill='#666666', font=font)
            
            # Add icon
            # Draw a simple file icon shape
            icon_size = 40
            icon_x = width // 2 - icon_size // 2
            icon_y = height // 3
            
            # Draw document icon
            draw.rectangle(
                [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
                outline='#999999',
                width=2
            )
            
            # Save as JPEG
            img.save(self.placeholder_path, 'JPEG', quality=85)
            logger.info(f"✅ Placeholder created with PIL: {self.placeholder_path}")
            
        except ImportError:
            # PIL not available, use system tools
            logger.info("PIL not available, using basic placeholder")
            
            try:
                # Create a simple grey image using ImageMagick if available
                result = subprocess.run([
                    'convert',
                    '-size', f'{self.size}x{int(self.size * 9 / 16)}',
                    'xc:#CCCCCC',
                    '-pointsize', '20',
                    '-fill', '#666666',
                    '-gravity', 'center',
                    '-annotate', '+0+0', 'Empty File',
                    str(self.placeholder_path)
                ], capture_output=True, timeout=5)
                
                if result.returncode == 0:
                    logger.info(f"✅ Placeholder created with ImageMagick: {self.placeholder_path}")
                else:
                    # Last resort: create a blank grey image with sips
                    self._create_basic_placeholder()
                    
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # ImageMagick not available, create basic placeholder
                self._create_basic_placeholder()
    
    def _create_basic_placeholder(self):
        """Create a very basic placeholder image using sips."""
        try:
            # Create a temporary text file and generate thumbnail from it
            temp_txt = self.thumbnail_dir / "temp_empty.txt"
            temp_txt.write_text("Empty File")
            
            subprocess.run([
                'sips',
                '--createThumbnail', str(self.size),
                '--out', str(self.placeholder_path),
                str(temp_txt)
            ], capture_output=True, timeout=5)
            
            temp_txt.unlink()
            
            if self.placeholder_path.exists():
                logger.info(f"✅ Basic placeholder created: {self.placeholder_path}")
            else:
                logger.warning("Could not create placeholder image")
                
        except Exception as e:
            logger.error(f"Failed to create basic placeholder: {e}")
