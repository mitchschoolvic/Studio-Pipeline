"""
Response DTOs

DTOs for outgoing API responses. These decouple the API from database models
and provide a clear contract for what data the API returns.

Benefits:
- Hide internal database structure
- Control exactly what data is exposed
- Add computed/derived fields without modifying models
- Version API responses independently
"""
