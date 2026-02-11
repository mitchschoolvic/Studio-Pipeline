import subprocess
import json
import asyncio
from pathlib import Path
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


class SwiftToolRunner:
    def __init__(self, swift_tools_dir: Path):
        self.tools_dir = Path(swift_tools_dir)
        self._verify_tools()
    
    def _verify_tools(self):
        """Ensure all Swift tools exist and are executable"""
        required = ['extract', 'boost', 'convert', 'remux', 'split', 'gesturetrim']
        for tool in required:
            tool_path = self.tools_dir / tool
            if not tool_path.exists():
                raise FileNotFoundError(f"Swift tool not found: {tool_path}")
            if not tool_path.is_file():
                raise PermissionError(f"Swift tool is not a file: {tool_path}")
            
            # Make executable if not already
            if not tool_path.stat().st_mode & 0o111:
                try:
                    tool_path.chmod(tool_path.stat().st_mode | 0o111)
                    logger.info(f"Made {tool} executable")
                except Exception as e:
                    raise PermissionError(f"Cannot make {tool} executable: {e}")
        
        logger.info(f"All Swift tools verified in {self.tools_dir}")
    
    async def run_tool(
        self,
        tool_name: str,
        args: list,
        progress_callback: Optional[Callable] = None
    ) -> subprocess.CompletedProcess:
        """Run a Swift tool and capture JSON progress output
        
        Args:
            tool_name: Name of the tool (extract, boost, denoise, convert, remux, split)
            args: List of arguments to pass to the tool
            progress_callback: Optional async callback for progress updates
            
        Returns:
            CompletedProcess with stdout and stderr
            
        Raises:
            subprocess.CalledProcessError: If the tool fails
        """
        tool_path = self.tools_dir / tool_name
        cmd = [str(tool_path)] + [str(arg) for arg in args]
        
        logger.info(f"Running Swift tool: {' '.join(cmd)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.tools_dir)
            )
            
            # Read stdout line by line for progress updates
            stdout_chunks = []
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                
                decoded_line = line.decode().strip()
                stdout_chunks.append(decoded_line)
                
                # Try to parse as JSON for progress reporting
                try:
                    progress_data = json.loads(decoded_line)
                    if progress_callback and 'progress' in progress_data:
                        await progress_callback(progress_data)
                        logger.debug(f"{tool_name} progress: {progress_data}")
                except json.JSONDecodeError:
                    # Not JSON, just regular output
                    logger.debug(f"{tool_name}: {decoded_line}")
            
            # Wait for process to complete
            await process.wait()
            
            # Get stderr
            stderr = await process.stderr.read()
            stderr_text = stderr.decode()
            
            if process.returncode != 0:
                error_msg = stderr_text or f"{tool_name} failed with code {process.returncode}"
                logger.error(f"Swift tool failed: {error_msg}")
                raise subprocess.CalledProcessError(
                    process.returncode,
                    cmd,
                    output='\n'.join(stdout_chunks),
                    stderr=stderr_text
                )
            
            logger.info(f"Swift tool {tool_name} completed successfully")
            return subprocess.CompletedProcess(
                cmd,
                process.returncode,
                '\n'.join(stdout_chunks),
                stderr_text
            )
        
        except subprocess.CalledProcessError:
            raise
        except Exception as e:
            logger.error(f"Error running Swift tool {tool_name}: {e}")
            raise
