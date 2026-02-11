"""
AI Mutexes and Locks

Provides global synchronization primitives to coordinate access to GPU/Metal
resources across AI workers (Whisper transcription and VLM analysis).

Rationale: Apple's Metal command buffers and MLX backends are not safely
re-entrant for our mixed workloads. We serialize GPU-bound sections to avoid
driver assertions like:
  AGXG13XFamilyCommandBuffer: A command encoder is already encoding...

Usage:
  from services.ai_mutex import gpu_lock
  async with gpu_lock:
      # GPU-bound operation
      ...
"""

import asyncio

# Single-flight GPU/Metal access across the process
gpu_lock = asyncio.Semaphore(1)

# Global shutdown signal so workers can stop scheduling GPU work during app teardown
shutting_down = asyncio.Event()

def set_shutting_down():
  """Mark the application as shutting down to prevent new GPU jobs."""
  try:
    shutting_down.set()
  except Exception:
    # Event already set or loop closed - best effort
    pass
