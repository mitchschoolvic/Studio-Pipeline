#!/usr/bin/env python3
"""Configure FTP settings for local server"""
from database import SessionLocal
from models import Setting

db = SessionLocal()

settings = [
    ('ftp_host', '127.0.0.1'),
    ('ftp_port', '2121'),
    ('ftp_username', 'anonymous'),
    ('ftp_password_encrypted', ''),
    ('source_path', '/')
]

for key, value in settings:
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = value
    else:
        db.add(Setting(key=key, value=value))
    print(f"✓ {key} = {value}")

db.commit()
db.close()
print("\n✅ FTP settings configured for 127.0.0.1:2121")
