from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from typing import List
from database import get_db
from models import Setting as SettingModel, Event
from schemas import Setting, SettingBase, SettingsTestRequest, SettingsTestResponse
from constants import HTTPStatus, FTPConfig
import aioftp
import asyncio
from pathlib import Path
import os
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
import shutil
from datetime import datetime
from sqlalchemy import create_engine, text, inspect as io_inspect
from sqlalchemy.orm import sessionmaker
from database import get_db, DB_PATH
from models import Session, File as FileModel

router = APIRouter()


@router.get("/settings", response_model=List[Setting])
def get_settings(db: DBSession = Depends(get_db)):
    """Get all settings"""
    return db.query(SettingModel).all()


@router.get("/settings/{key}", response_model=Setting)
def get_setting(key: str, db: DBSession = Depends(get_db)):
    """Get a specific setting"""
    setting = db.query(SettingModel).filter(SettingModel.key == key).first()
    if not setting:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"Setting '{key}' not found")
    return setting


@router.put("/settings/{key}", response_model=Setting)
def update_setting(key: str, setting_update: SettingBase, db: DBSession = Depends(get_db)):
    """Update a specific setting value"""
    if setting_update.key != key:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Key mismatch in path and body")
    
    setting = db.query(SettingModel).filter(SettingModel.key == key).first()
    if not setting:
        # Create the setting if it doesn't exist
        setting = SettingModel(key=key, value=setting_update.value)
        db.add(setting)
    else:
        setting.value = setting_update.value
    
    db.commit()
    db.refresh(setting)
    
    # If pause_processing changed, create an event to notify WebSocket clients
    if key == 'pause_processing':
        event = Event(
            event_type='pause_state_changed',
            payload_json=json.dumps({
                'paused': str(setting.value).lower() == 'true'
            })
        )
        db.add(event)
        db.commit()
    
    return setting


@router.post("/settings/test-connection", response_model=SettingsTestResponse)
async def test_ftp_connection(test_request: SettingsTestRequest):
    """Test FTP connection with provided settings"""
    try:
        # Parse port
        try:
            port = int(test_request.ftp_port)
        except ValueError:
            return SettingsTestResponse(
                success=False,
                message="Invalid port number",
                details=f"Port must be a number, got: {test_request.ftp_port}"
            )
        
        # Determine username/password
        is_anonymous = test_request.ftp_anonymous.lower() == 'true'
        username = 'anonymous' if is_anonymous else test_request.ftp_username
        password = '' if is_anonymous else test_request.ftp_password_encrypted
        
        if not is_anonymous and not username:
            return SettingsTestResponse(
                success=False,
                message="Username required for non-anonymous login",
                details="Please provide a username or enable anonymous login"
            )
        
        # Test connection
        try:
            client = aioftp.Client()
            await asyncio.wait_for(
                client.connect(test_request.ftp_host, port),
                timeout=FTPConfig.CONNECTION_TIMEOUT_SECONDS
            )
            await asyncio.wait_for(
                client.login(username, password),
                timeout=FTPConfig.LOGIN_TIMEOUT_SECONDS
            )

            # Test path access
            try:
                await asyncio.wait_for(
                    client.list(test_request.source_path),
                    timeout=FTPConfig.LIST_TIMEOUT_SECONDS
                )
                path_accessible = True
                path_message = f"Source path '{test_request.source_path}' is accessible"
            except Exception as e:
                path_accessible = False
                path_message = f"Source path '{test_request.source_path}' not accessible: {str(e)}"
            
            await client.quit()
            
            if path_accessible:
                return SettingsTestResponse(
                    success=True,
                    message="FTP connection successful",
                    details=path_message
                )
            else:
                return SettingsTestResponse(
                    success=False,
                    message="Connected but source path not found",
                    details=path_message
                )
        
        except asyncio.TimeoutError:
            return SettingsTestResponse(
                success=False,
                message="Connection timeout",
                details=f"Could not connect to {test_request.ftp_host}:{port} within {FTPConfig.CONNECTION_TIMEOUT_SECONDS} seconds"
            )
        except aioftp.errors.StatusCodeError as e:
            return SettingsTestResponse(
                success=False,
                message="Authentication failed",
                details=str(e)
            )
        except Exception as e:
            return SettingsTestResponse(
                success=False,
                message="Connection failed",
                details=str(e)
            )
    
    except Exception as e:
        return SettingsTestResponse(
            success=False,
            message="Unexpected error",
            details=str(e)
        )


@router.post("/settings/validate", response_model=dict)
async def validate_settings(db: DBSession = Depends(get_db)):
    """Validate current settings - check FTP connection and local paths"""
    results = {
        "ftp_connection": {"valid": False, "message": ""},
        "temp_path": {"valid": False, "message": ""},
        "output_path": {"valid": False, "message": ""},
        "external_audio_path": {"valid": True, "message": "Not configured (optional)"},
        "overall_valid": False
    }
    
    # Get settings from database
    settings = {s.key: s.value for s in db.query(SettingModel).all()}
    
    # Validate FTP connection
    try:
        ftp_host = settings.get('ftp_host', '')
        ftp_port = int(settings.get('ftp_port', '21'))
        ftp_username = settings.get('ftp_username', 'anonymous')
        ftp_password = settings.get('ftp_password', '')
        ftp_source_path = settings.get('ftp_source_path', '/')
        
        if not ftp_host:
            results["ftp_connection"]["message"] = "FTP host not configured"
        else:
            try:
                client = aioftp.Client()
                await asyncio.wait_for(
                    client.connect(ftp_host, ftp_port),
                    timeout=FTPConfig.CONNECTION_TIMEOUT_SECONDS
                )
                await asyncio.wait_for(
                    client.login(ftp_username, ftp_password),
                    timeout=FTPConfig.LOGIN_TIMEOUT_SECONDS
                )

                # Test path access
                try:
                    await asyncio.wait_for(
                        client.list(ftp_source_path),
                        timeout=FTPConfig.LIST_TIMEOUT_SECONDS
                    )
                    results["ftp_connection"]["valid"] = True
                    results["ftp_connection"]["message"] = f"Connected to {ftp_host}:{ftp_port}"
                except Exception as e:
                    results["ftp_connection"]["message"] = f"Source path '{ftp_source_path}' not accessible: {str(e)}"
                
                await client.quit()
                
            except asyncio.TimeoutError:
                results["ftp_connection"]["message"] = f"Connection timeout: {ftp_host}:{ftp_port}"
            except Exception as e:
                results["ftp_connection"]["message"] = f"Connection failed: {str(e)}"
    
    except Exception as e:
        results["ftp_connection"]["message"] = f"Invalid FTP settings: {str(e)}"
    
    # Validate temp_path
    temp_path_str = settings.get('temp_path', '/tmp/pipeline')
    try:
        temp_path = Path(temp_path_str).expanduser()
        
        # Try to create directory if it doesn't exist
        temp_path.mkdir(parents=True, exist_ok=True)
        
        # Test write access
        test_file = temp_path / '.write_test'
        try:
            test_file.write_text('test')
            test_file.unlink()
            results["temp_path"]["valid"] = True
            results["temp_path"]["message"] = f"Writable: {temp_path}"
        except Exception as e:
            results["temp_path"]["message"] = f"Not writable: {temp_path} - {str(e)}"
    
    except Exception as e:
        results["temp_path"]["message"] = f"Invalid path: {temp_path_str} - {str(e)}"
    
    # Validate output_path
    output_path_str = settings.get('output_path', str(Path.home() / 'Videos' / 'StudioPipeline'))
    try:
        output_path = Path(output_path_str).expanduser()
        
        # Try to create directory if it doesn't exist
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Test write access
        test_file = output_path / '.write_test'
        try:
            test_file.write_text('test')
            test_file.unlink()
            results["output_path"]["valid"] = True
            results["output_path"]["message"] = f"Writable: {output_path}"
        except Exception as e:
            results["output_path"]["message"] = f"Not writable: {output_path} - {str(e)}"
    
    except Exception as e:
        results["output_path"]["message"] = f"Invalid path: {output_path_str} - {str(e)}"

    # Validate external_audio_export_path (optional)
    external_audio_enabled = settings.get('external_audio_export_enabled', 'false')
    external_audio_path_str = settings.get('external_audio_export_path', '')

    if external_audio_enabled.lower() == 'true' and external_audio_path_str and external_audio_path_str.strip():
        try:
            external_audio_path = Path(external_audio_path_str).expanduser()

            # Try to create directory if it doesn't exist
            external_audio_path.mkdir(parents=True, exist_ok=True)

            # Test write access
            test_file = external_audio_path / '.write_test'
            try:
                test_file.write_text('test')
                test_file.unlink()
                results["external_audio_path"]["valid"] = True
                results["external_audio_path"]["message"] = f"Writable: {external_audio_path}"
            except Exception as e:
                results["external_audio_path"]["valid"] = False
                results["external_audio_path"]["message"] = f"Not writable: {external_audio_path} - {str(e)}"

        except Exception as e:
            results["external_audio_path"]["valid"] = False
            results["external_audio_path"]["message"] = f"Invalid path: {external_audio_path_str} - {str(e)}"
    elif external_audio_enabled.lower() == 'true':
        results["external_audio_path"]["valid"] = False
        results["external_audio_path"]["message"] = "External audio export is enabled but no path configured"

    # Overall validation (external_audio_path is optional, so only fail if it's enabled and invalid)
    results["overall_valid"] = all([
        results["ftp_connection"]["valid"],
        results["temp_path"]["valid"],
        results["output_path"]["valid"],
        # External audio path must be valid if enabled, but can be disabled
        results["external_audio_path"]["valid"] if external_audio_enabled.lower() == 'true' else True
    ])

    return results


@router.get("/settings/database/export")
def export_database(db: DBSession = Depends(get_db)):
    """Export the current database file"""
    if not DB_PATH.exists():
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Database file not found")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pipeline_backup_{timestamp}.db"
    
    return FileResponse(
        path=DB_PATH,
        filename=filename,
        media_type="application/x-sqlite3"
    )


@router.post("/settings/database/restore")
async def restore_database(file: UploadFile = File(...), db: DBSession = Depends(get_db)):
    """Restore the database from a backup file"""
    if not file.filename.endswith('.db'):
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid file type. Must be a .db file")
    
    # Create a backup of the current database before overwriting
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / f"pipeline_pre_restore_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    
    try:
        # Save uploaded file to a temporary location first
        temp_path = DB_PATH.parent / "temp_restore.db"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Close existing connections (handled by pool recycling, but we can't force close easily here)
        # In SQLite, replacing the file while open might cause issues on Windows, but usually fine on Unix
        # if we are careful. Ideally, we should stop the app, but for this tool, we'll swap the file.
        
        # Move temp file to actual DB path
        shutil.move(temp_path, DB_PATH)
        
        return {"message": "Database restored successfully", "backup_created": str(backup_path.name)}
        
    except Exception as e:
        # If anything goes wrong, try to restore from the backup we just made
        if backup_path.exists():
            shutil.copy2(backup_path, DB_PATH)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"Restore failed: {str(e)}")


@router.get("/settings/database/stats")
def get_database_stats(db: DBSession = Depends(get_db)):
    """Get statistics about the current database"""
    try:
        session_count = db.query(Session).count()
        # Count files that have a thumbnail path
        thumbnail_count = db.query(FileModel).filter(FileModel.thumbnail_path.isnot(None)).count()
        
        return {
            "sessions": session_count,
            "thumbnails": thumbnail_count
        }
    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"Failed to get stats: {str(e)}")


@router.post("/settings/database/inspect")
async def inspect_database(file: UploadFile = File(...)):
    """Inspect a database file and return statistics without restoring it"""
    if not file.filename.endswith('.db'):
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Invalid file type. Must be a .db file")

    # Save uploaded file to a temporary location
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = DB_PATH.parent / f"temp_inspect_{timestamp}.db"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create a temporary engine to read this DB
        inspect_engine = create_engine(f'sqlite:///{temp_path}')
        InspectSession = sessionmaker(bind=inspect_engine)
        inspect_db = InspectSession()

        try:
            # We use raw SQL or bind the models to this engine?
            # Binding models to multiple engines is tricky with declarative base.
            # Safest is to use raw SQL for inspection to avoid ORM confusion,
            # or just simple counts which are easy in SQL.

            # Check if tables exist first
            inspector = io_inspect(inspect_engine)
            tables = inspector.get_table_names()

            if 'sessions' not in tables or 'files' not in tables:
                 return {
                    "valid": False,
                    "message": "Invalid database format: missing required tables",
                    "sessions": 0,
                    "thumbnails": 0
                }

            # Count sessions
            session_count = inspect_db.execute(text("SELECT COUNT(*) FROM sessions")).scalar()

            # Count thumbnails (files with thumbnail_path)
            thumbnail_count = inspect_db.execute(text("SELECT COUNT(*) FROM files WHERE thumbnail_path IS NOT NULL")).scalar()

            return {
                "valid": True,
                "sessions": session_count,
                "thumbnails": thumbnail_count
            }

        finally:
            inspect_db.close()
            inspect_engine.dispose()

    except Exception as e:
        return {
            "valid": False,
            "message": f"Failed to inspect database: {str(e)}",
            "sessions": 0,
            "thumbnails": 0
        }
    finally:
        # Clean up temp file
        if temp_path.exists():
            try:
                os.remove(temp_path)
            except Exception:
                pass


@router.post("/settings/database/clear")
def clear_database(db: DBSession = Depends(get_db)):
    """Clear all data from the database (sessions, files, jobs, events) but keep settings"""
    try:
        # Create automatic backup before clearing
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = DB_PATH.parent / f"pipeline_pre_clear_{timestamp}.db"
        shutil.copy2(DB_PATH, backup_path)

        # Get counts before deletion
        from models import Job, Event
        session_count = db.query(Session).count()
        file_count = db.query(FileModel).count()
        job_count = db.query(Job).count()
        event_count = db.query(Event).count()

        # Check if AI analytics table exists
        analytics_count = 0
        try:
            from config.ai_config import AI_ENABLED
            if AI_ENABLED:
                from models_analytics import FileAnalytics
                analytics_count = db.query(FileAnalytics).count()
        except Exception:
            pass

        # Delete all data (cascade will handle relationships)
        # Order matters: delete children before parents
        db.query(Job).delete()
        db.query(Event).delete()
        db.query(FileModel).delete()
        db.query(Session).delete()

        # Delete analytics if it exists
        if analytics_count > 0:
            try:
                from models_analytics import FileAnalytics
                db.query(FileAnalytics).delete()
            except Exception:
                pass

        db.commit()

        return {
            "message": "Database cleared successfully",
            "backup_created": str(backup_path.name),
            "deleted": {
                "sessions": session_count,
                "files": file_count,
                "jobs": job_count,
                "events": event_count,
                "analytics": analytics_count
            }
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear database: {str(e)}"
        )


@router.post("/settings/reset")
def reset_settings(db: DBSession = Depends(get_db)):
    """Reset all settings to their default values"""
    from constants import SettingKeys

    try:
        # Define default settings (same as init_db.py)
        defaults = {
            'ftp_host': 'atem.studio.local',
            'ftp_port': '21',
            'ftp_anonymous': 'true',
            'ftp_username': 'anonymous',
            'ftp_password_encrypted': '',
            'source_path': '/ATEM/recordings',
            SettingKeys.FTP_EXCLUDE_FOLDERS: '',
            'temp_path': '/tmp/pipeline',
            'output_path': '~/Videos/StudioPipeline',
            'max_concurrent_copy': '1',
            'max_concurrent_process': '1',
            'ftp_check_interval': '5',
            'pause_processing': 'false',
            'iso_min_size_mb': '50',
            'bitrate_threshold_kbps': '500',
            SettingKeys.ONEDRIVE_DETECTION_ENABLED: 'true',
            SettingKeys.ONEDRIVE_ROOT: str((Path.home() / 'Library/CloudStorage').resolve()),
            SettingKeys.AUTO_DELETE_ENABLED: 'false',
            SettingKeys.AUTO_DELETE_AGE_MONTHS: '12',
            SettingKeys.EXTERNAL_AUDIO_EXPORT_ENABLED: 'false',
            SettingKeys.EXTERNAL_AUDIO_EXPORT_PATH: '',
            SettingKeys.PAUSE_ANALYTICS: 'false',
            SettingKeys.RUN_ANALYTICS_WHEN_IDLE: 'true',
        }

        reset_count = 0
        reset_keys = []

        # Update all settings to defaults
        for key, default_value in defaults.items():
            setting = db.query(SettingModel).filter(SettingModel.key == key).first()
            if setting:
                setting.value = default_value
                reset_count += 1
                reset_keys.append(key)
            else:
                # Create if doesn't exist
                db.add(SettingModel(key=key, value=default_value))
                reset_count += 1
                reset_keys.append(key)

        db.commit()

        return {
            "message": "Settings reset to defaults successfully",
            "reset_count": reset_count,
            "reset_keys": reset_keys
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset settings: {str(e)}"
        )


@router.get("/network/interfaces")
def get_network_interfaces():
    """Get available network interfaces and their IP addresses"""
    import socket
    import subprocess

    interfaces = []
    
    # Always include "all interfaces" option
    interfaces.append({
        "name": "All Interfaces",
        "address": "0.0.0.0",
        "description": "Listen on all available network interfaces (recommended)"
    })
    
    # Always include localhost
    interfaces.append({
        "name": "Localhost Only",
        "address": "127.0.0.1",
        "description": "Only accessible from this machine"
    })
    
    # Get real interfaces using ifconfig (macOS) or ip (Linux)
    try:
        try:
            # macOS / BSD
            result = subprocess.run(
                ['ifconfig'], capture_output=True, text=True, timeout=5
            )
            output = result.stdout
            current_iface = None
            for line in output.splitlines():
                if not line.startswith('\t') and not line.startswith(' ') and ':' in line:
                    current_iface = line.split(':')[0]
                elif 'inet ' in line and current_iface:
                    parts = line.strip().split()
                    ip_idx = parts.index('inet') + 1
                    if ip_idx < len(parts):
                        ip = parts[ip_idx]
                        if ip != '127.0.0.1' and not ip.startswith('169.254.'):
                            description = f"Interface: {current_iface}"
                            if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                                description = f"LAN ({current_iface})"
                            interfaces.append({
                                "name": f"{current_iface} - {ip}",
                                "address": ip,
                                "description": description
                            })
        except FileNotFoundError:
            # Linux fallback: ip addr
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show'], capture_output=True, text=True, timeout=5
            )
            output = result.stdout
            current_iface = None
            for line in output.splitlines():
                line = line.strip()
                if line and line[0].isdigit() and ':' in line:
                    current_iface = line.split(':')[1].strip()
                elif line.startswith('inet ') and current_iface:
                    ip = line.split()[1].split('/')[0]
                    if ip != '127.0.0.1':
                        interfaces.append({
                            "name": f"{current_iface} - {ip}",
                            "address": ip,
                            "description": f"LAN ({current_iface})"
                        })
    except Exception:
        # Final fallback: use socket
        try:
            hostname = socket.gethostname()
            host_ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
            seen = set()
            for addr_info in host_ips:
                ip = addr_info[4][0]
                if ip not in seen and ip != '127.0.0.1':
                    seen.add(ip)
                    interfaces.append({
                        "name": ip,
                        "address": ip,
                        "description": "LAN"
                    })
        except Exception:
            pass
    
    return {"interfaces": interfaces}


@router.get("/network/status")
def get_network_status(db: DBSession = Depends(get_db)):
    """Get current network binding status"""
    import socket
    import subprocess
    
    # Get current setting from DB
    setting = db.query(SettingModel).filter(SettingModel.key == "server_host").first()
    current_host = setting.value if setting else "0.0.0.0"
    
    # Get local hostname and IPs
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "unknown"
    
    # Get all IPs this machine has
    all_ips = []
    try:
        try:
            result = subprocess.run(
                ['ifconfig'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if 'inet ' in line:
                    parts = line.strip().split()
                    ip_idx = parts.index('inet') + 1
                    if ip_idx < len(parts):
                        ip = parts[ip_idx]
                        if not ip.startswith('169.254.'):
                            all_ips.append(ip)
        except FileNotFoundError:
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('inet '):
                    ip = line.split()[1].split('/')[0]
                    all_ips.append(ip)
    except Exception:
        try:
            host_ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
            all_ips = list(set(info[4][0] for info in host_ips))
        except Exception:
            all_ips = [local_ip]
    
    return {
        "current_host": current_host,
        "hostname": hostname,
        "local_ip": local_ip,
        "all_ips": all_ips,
        "port": 8888,
        "requires_restart": True
    }
