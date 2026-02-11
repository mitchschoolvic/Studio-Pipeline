"""
Domain Aggregates

Aggregates are clusters of domain objects that can be treated as a single unit.
The aggregate root is the only member of the aggregate that outside objects
are allowed to hold references to.

Examples:
- SessionAggregate: Groups Session with its Files
- ProcessingPipeline: Groups Files with their Jobs
"""
