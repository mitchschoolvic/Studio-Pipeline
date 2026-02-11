"""
Data Transfer Objects (DTOs) Layer

This package contains DTOs that decouple the API layer from the database models.
DTOs prevent leaking database structure to external APIs and allow independent evolution.

Structure:
- request/: DTOs for incoming API requests
- response/: DTOs for outgoing API responses
- internal/: DTOs for service-to-service communication
"""
