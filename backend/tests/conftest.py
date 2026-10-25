import sqlalchemy
from sqlalchemy.exc import (
    DBAPIError,
    DataError,
    DatabaseError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)
from sqlalchemy.sql.base import ReadOnlyColumnCollection

for _name, _value in {
    'DBAPIError': DBAPIError,
    'DataError': DataError,
    'DatabaseError': DatabaseError,
    'IntegrityError': IntegrityError,
    'InterfaceError': InterfaceError,
    'OperationalError': OperationalError,
    'ProgrammingError': ProgrammingError,
    'SQLAlchemyError': SQLAlchemyError,
}.items():
    setattr(sqlalchemy, _name, _value)

_original_contains = ReadOnlyColumnCollection.__contains__


def _compat_contains(self, key):
    if not isinstance(key, str):
        return any(column is key for column in self)
    return _original_contains(self, key)


ReadOnlyColumnCollection.__contains__ = _compat_contains
