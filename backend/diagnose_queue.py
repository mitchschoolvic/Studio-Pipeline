#!/usr/bin/env python3
"""Diagnose the state of files and jobs in the database"""

from database import SessionLocal
from models import File, Job, Session as SessionModel
from sqlalchemy import func

db = SessionLocal()

# Check file states
print('=== FILE STATES ===')
file_states = db.query(File.state, func.count(File.id)).group_by(File.state).all()
for state, count in file_states:
    print(f'  {state}: {count}')

# Check job states
print('\n=== JOB STATES ===')
job_states = db.query(Job.kind, Job.state, func.count(Job.id)).group_by(Job.kind, Job.state).all()
for kind, state, count in job_states:
    print(f'  {kind} - {state}: {count}')

# Find pending/discovered files 
print('\n=== DISCOVERED/COPYING FILES ===')
orphaned = db.query(File).filter(
    File.state.in_(['DISCOVERED', 'COPYING']),
).all()

for f in orphaned[:30]:
    all_jobs = db.query(Job).filter(Job.file_id == f.id).all()
    job_summary = ', '.join([f'{j.kind}:{j.state}' for j in all_jobs])
    print(f'  {f.filename[:50]:50} state={f.state:12} jobs=[{job_summary}]')

# Check sessions with partial completion
print('\n=== SESSIONS WITH PARTIAL COMPLETION ===')
sessions = db.query(SessionModel).all()
for sess in sessions[:10]:
    files = sess.files
    states = {}
    for f in files:
        states[f.state] = states.get(f.state, 0) + 1
    state_str = ', '.join([f'{k}:{v}' for k,v in states.items()])
    if len(states) > 1 or 'DISCOVERED' in states or 'COPYING' in states:
        print(f'  {sess.name[:40]:40} files={len(files)} states=[{state_str}]')

# Check for files with FAILED jobs that might need recovery
print('\n=== FAILED FILES ===')
failed_files = db.query(File).filter(File.state == 'FAILED').all()
for f in failed_files[:10]:
    print(f'  {f.filename[:50]:50} category={f.failure_category} job_kind={f.failure_job_kind}')

db.close()
