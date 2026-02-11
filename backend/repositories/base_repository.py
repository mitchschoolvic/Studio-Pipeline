"""
Base repository providing common CRUD operations.
"""

from typing import Generic, TypeVar, List, Optional, Type, Dict, Any
from sqlalchemy.orm import Session

T = TypeVar('T')


class BaseRepository(Generic[T]):
    """
    Generic base repository providing common CRUD operations.
    All specific repositories should inherit from this class.
    """

    def __init__(self, db: Session, model: Type[T]):
        """
        Initialize the repository.

        Args:
            db: SQLAlchemy database session
            model: SQLAlchemy model class
        """
        self.db = db
        self.model = model

    def create(self, obj: T) -> T:
        """
        Create a new record in the database.

        Args:
            obj: Model instance to create

        Returns:
            Created model instance
        """
        self.db.add(obj)
        self.db.flush()
        return obj

    def get_by_id(self, id: str) -> Optional[T]:
        """
        Retrieve a record by its ID.

        Args:
            id: Primary key value

        Returns:
            Model instance or None if not found
        """
        return self.db.query(self.model).filter(self.model.id == id).first()

    def get_all(self, limit: Optional[int] = None, offset: int = 0) -> List[T]:
        """
        Retrieve all records.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of model instances
        """
        query = self.db.query(self.model)
        if limit:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)
        return query.all()

    def update(self, obj: T) -> T:
        """
        Update an existing record.

        Args:
            obj: Model instance with updated values

        Returns:
            Updated model instance
        """
        self.db.flush()
        return obj

    def delete(self, obj: T) -> None:
        """
        Delete a record from the database.

        Args:
            obj: Model instance to delete
        """
        self.db.delete(obj)
        self.db.flush()

    def delete_by_id(self, id: str) -> bool:
        """
        Delete a record by its ID.

        Args:
            id: Primary key value

        Returns:
            True if deleted, False if not found
        """
        obj = self.get_by_id(id)
        if obj:
            self.delete(obj)
            return True
        return False

    def count(self) -> int:
        """
        Count total records.

        Returns:
            Total number of records
        """
        return self.db.query(self.model).count()

    def exists(self, id: str) -> bool:
        """
        Check if a record exists by ID.

        Args:
            id: Primary key value

        Returns:
            True if exists, False otherwise
        """
        return self.db.query(self.model).filter(self.model.id == id).count() > 0

    def filter_by(self, **filters: Any) -> List[T]:
        """
        Filter records by arbitrary criteria.

        Args:
            **filters: Keyword arguments for filtering

        Returns:
            List of matching model instances
        """
        query = self.db.query(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.filter(getattr(self.model, key) == value)
        return query.all()
