"""
Specification Pattern Implementation

Provides a way to encapsulate complex query logic in reusable, composable specifications.
This follows the Specification Pattern from Domain-Driven Design.

Benefits:
- Encapsulate complex query logic
- Compose specifications using AND, OR, NOT
- Reusable across different repositories
- Testable in isolation
- More expressive than passing many parameters
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from sqlalchemy.orm import Query


T = TypeVar('T')


class Specification(ABC, Generic[T]):
    """
    Abstract base class for specifications.

    A specification encapsulates a single business rule or query criterion.
    """

    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """
        Check if a candidate object satisfies this specification.

        Args:
            candidate: Object to check

        Returns:
            True if candidate satisfies specification
        """
        pass

    @abstractmethod
    def to_sql_filter(self):
        """
        Convert specification to SQLAlchemy filter expression.

        Returns:
            SQLAlchemy filter expression
        """
        pass

    def __and__(self, other: "Specification[T]") -> "AndSpecification[T]":
        """Combine specifications with AND."""
        return AndSpecification(self, other)

    def __or__(self, other: "Specification[T]") -> "OrSpecification[T]":
        """Combine specifications with OR."""
        return OrSpecification(self, other)

    def __invert__(self) -> "NotSpecification[T]":
        """Negate specification with NOT."""
        return NotSpecification(self)


class AndSpecification(Specification[T]):
    """Specification that combines two specifications with AND."""

    def __init__(self, left: Specification[T], right: Specification[T]):
        """
        Initialize AND specification.

        Args:
            left: Left specification
            right: Right specification
        """
        self.left = left
        self.right = right

    def is_satisfied_by(self, candidate: T) -> bool:
        """Check if candidate satisfies both specifications."""
        return self.left.is_satisfied_by(candidate) and self.right.is_satisfied_by(candidate)

    def to_sql_filter(self):
        """Convert to SQL AND filter."""
        from sqlalchemy import and_
        return and_(self.left.to_sql_filter(), self.right.to_sql_filter())


class OrSpecification(Specification[T]):
    """Specification that combines two specifications with OR."""

    def __init__(self, left: Specification[T], right: Specification[T]):
        """
        Initialize OR specification.

        Args:
            left: Left specification
            right: Right specification
        """
        self.left = left
        self.right = right

    def is_satisfied_by(self, candidate: T) -> bool:
        """Check if candidate satisfies either specification."""
        return self.left.is_satisfied_by(candidate) or self.right.is_satisfied_by(candidate)

    def to_sql_filter(self):
        """Convert to SQL OR filter."""
        from sqlalchemy import or_
        return or_(self.left.to_sql_filter(), self.right.to_sql_filter())


class NotSpecification(Specification[T]):
    """Specification that negates another specification."""

    def __init__(self, spec: Specification[T]):
        """
        Initialize NOT specification.

        Args:
            spec: Specification to negate
        """
        self.spec = spec

    def is_satisfied_by(self, candidate: T) -> bool:
        """Check if candidate does NOT satisfy specification."""
        return not self.spec.is_satisfied_by(candidate)

    def to_sql_filter(self):
        """Convert to SQL NOT filter."""
        from sqlalchemy import not_
        return not_(self.spec.to_sql_filter())
