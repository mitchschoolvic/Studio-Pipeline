"""
Domain Value Objects

Value objects are immutable types that represent descriptive aspects of the domain.
They have no conceptual identity and are compared by their values, not by ID.

Examples:
- FileState: Represents the state of a file (immutable enum-like value)
- FilePath: Validated file path with operations
- FileSize: Size with formatting and validation
- FTPCredentials: Immutable credential set
"""
