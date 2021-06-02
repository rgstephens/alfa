from __future__ import annotations

import copy
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, AsyncGenerator, Collection, Dict, Optional, Tuple, Union

import aiopg
import aiopg.sa.result
from aiopg.sa import Engine, SAConnection, create_engine
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.base import DEFAULT_STATE_ATTR
from sqlalchemy.orm.mapper import Mapper
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.schema import Column, Table

logger = logging.getLogger(__name__)
__db_pool: Optional[Engine] = None
context_conn: ContextVar[SAConnection] = ContextVar('async_connection')


if TYPE_CHECKING:
    ColumnType = Column[Any]
else:
    ColumnType = Column


class AsyncQuery(orm.Query):  # type: ignore
    pass


class BaseModelClass:
    __table__: Table
    __mapper__: Mapper

    def _get_pk_field(self) -> Tuple[str, ColumnType]:
        result: Optional[Tuple[str, ColumnType]] = None
        for field_name, field in self.__mapper__.columns.items():
            if field.primary_key:
                result = field_name, field
                break
        assert result
        return result

    @property
    def _pk(self) -> Any:
        key, _ = self._get_pk_field()
        return getattr(self, key)

    @_pk.setter
    def _pk(self, value: Any) -> None:
        key, _ = self._get_pk_field()
        setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        values = copy.deepcopy(self.__dict__)
        if DEFAULT_STATE_ATTR in values:
            del values[DEFAULT_STATE_ATTR]
        return values

    @hybrid_property
    def query(self) -> AsyncQuery:
        result: AsyncQuery = AsyncQuery(self)
        return result

    @classmethod
    async def bulk_insert(cls, connection: SAConnection, values_list):  # type: ignore
        result = await connection.execute(cls.__table__.insert().values(values_list))
        try:
            return result.rowcount
        finally:
            result.close()

    def _prepare_saving(
        self,
        only_fields: Optional[Collection[Union[InstrumentedAttribute, str]]] = None,
        exclude_fields: Optional[Collection[Union[InstrumentedAttribute, str]]] = None,
        force_insert: bool = False,
    ) -> Tuple[ColumnType, Dict[str, Any]]:
        """
        Returns primary key field and values, which need to be saved
        """
        values = self.to_dict()
        if only_fields:
            only_fields = [k.key if isinstance(k, InstrumentedAttribute) else k for k in only_fields]
            values = {k: v for k, v in values.items() if k in only_fields}
        if exclude_fields:
            exclude_fields = [k.key if isinstance(k, InstrumentedAttribute) else k for k in exclude_fields]
            values = {k: v for k, v in values.items() if k not in exclude_fields}

        pk_field_name, pk_field = self._get_pk_field()
        if pk_field_name in values:
            if force_insert is False:
                values.pop(pk_field_name)
        return pk_field, values

    async def delete(self, connection: SAConnection) -> None:
        _, pk_field = self._get_pk_field()
        cursor = await connection.execute(self.__table__.delete().where(pk_field == self._pk))
        cursor.close()

    async def save(
        self,
        connection: SAConnection,
        only_fields: Optional[Collection[Union[InstrumentedAttribute, str]]] = None,
        exclude_fields: Optional[Collection[Union[InstrumentedAttribute, str]]] = None,
        force_insert: bool = False,
    ) -> bool:
        pk_field, values = self._prepare_saving(
            only_fields=only_fields, exclude_fields=exclude_fields, force_insert=force_insert
        )

        async def _execute(query: Union[Insert, Update], values: Dict[str, Any]) -> bool:
            cursor = await connection.execute(query.values(**values).returning(pk_field))
            try:
                if cursor.returns_rows:
                    _id = await cursor.scalar()
                    if _id:
                        self._pk = _id
                        return True
                else:
                    _rowcount: int = cursor.rowcount
                    return _rowcount > 0
            finally:
                cursor.close()
            return False

        if not self._pk or (force_insert is True):
            # INSERT flow
            return await _execute(self.__table__.insert(), values)
        else:
            # Update flow
            cursor = await connection.execute(self.__table__.update().where(pk_field == self._pk).values(**values))
            try:
                if cursor.rowcount:
                    return True
            finally:
                cursor.close()
        return False

    async def refresh(self, connection: SAConnection) -> None:
        _, pk_field = self._get_pk_field()
        res = dict(await fetchone(connection, self.__table__.select().where(pk_field == self._pk).limit(1)))
        for key, value in res.items():
            setattr(self, key, value)

    async def upsert(self, connection: SAConnection, constraint_column: Optional[ColumnType]) -> bool:
        if constraint_column not in [column.name for column in self.__table__.c]:
            raise Exception(f'Invalid constraint_column {constraint_column}')

        pk_field, values = self._prepare_saving()

        on_update_fields = {}
        for column in list(self.__table__.c):
            if column.onupdate and not values.get(column.name):
                on_update_fields[column.name] = column.onupdate.arg

        q = postgresql.insert(self.__table__).values(**values)

        values.update(on_update_fields)
        q = q.on_conflict_do_update(index_elements=[constraint_column], set_=values)

        cursor = await connection.execute(q.returning(pk_field))
        try:
            if cursor.returns_rows:
                _id = await cursor.scalar()
                if _id:
                    self._pk = _id
                    return True
            else:
                _rowcount: int = cursor.rowcount
                return _rowcount > 0
        finally:
            cursor.close()
        return False


async def _fetch(conn: SAConnection, query: ClauseElement, meth: str) -> aiopg.sa.result.RowProxy:
    if isinstance(query, AsyncQuery):
        query = query.statement
    res = await conn.execute(query)
    async with res.cursor:
        return await getattr(res, meth)()


async def fetchone(conn: SAConnection, query: ClauseElement) -> aiopg.sa.result.RowProxy:
    return await _fetch(conn, query, 'fetchone')


@asynccontextmanager
async def connection_context() -> AsyncGenerator[SAConnection, None]:

    """
    Acquires connection from pool, releases it on exit from context.

    You can use it with `AsyncQuery.auto_connection()` method call:
    >>> async with connection_context():
    >>>     await Model.query.auto_connection().count()
    >>>     await AnotherModel.query.auto_connection().count()

    Each of queries will use the same connection here.
    Also, you can start transaction with this:
    >>> async with connection_context() as connection:
    >>>     await Model.query.auto_connection().count()
    >>>     async with connection.begin():
    >>>         obj = await AnotherModel.query.auto_connection().first()
    >>>         obj.attr = 1
    >>>         await obj.save(connection)
    """
    conn = context_conn.get(None)
    if conn is None:
        assert __db_pool
        async with __db_pool.acquire() as conn:
            context_conn.set(conn)
            yield conn
        context_conn.set(None)
    else:
        yield conn


@asynccontextmanager
async def connection_context_with_transaction() -> AsyncGenerator[SAConnection, None]:
    async with connection_context() as conn:
        async with conn.begin():
            yield conn


class PoolAlreadyInitialized(Exception):
    pass


class PoolNotInitialized(Exception):
    pass


def get_connection_url(host: str, port: int, username: str, password: str, database: str) -> URL:
    return URL('postgresql', host=host, port=port, username=username, password=password, database=database)


async def init_db(
    connection_url: URL, echo: bool, pool_min_size: int, pool_max_size: int, pool_recycle_seconds: int
) -> Engine:
    global __db_pool
    if __db_pool is not None:
        raise PoolAlreadyInitialized('database already initialized')

    __db_pool = await create_engine(
        **connection_url.translate_connect_args(username='user'),
        echo=echo,
        minsize=pool_min_size,
        maxsize=pool_max_size,
        pool_recycle=pool_recycle_seconds,
    )
    logger.info('database pool opened')
    assert __db_pool
    return __db_pool


async def close_db() -> None:
    global __db_pool
    if __db_pool is not None:
        __db_pool.close()
        await __db_pool.wait_closed()
        logger.info('database pool closed')
        __db_pool = None


async def get_db_pool() -> Engine:
    global __db_pool
    if not __db_pool:
        raise PoolNotInitialized('database not initialized')
    return __db_pool


async def check_db_connection() -> Tuple[bool, str]:
    global __db_pool
    if __db_pool is None:
        return False, '__db_pool is None'

    try:
        async with connection_context() as conn:
            await conn.execute('select 1;')
    except Exception as exp:
        logger.exception('unknown connection error')
        return False, str(exp)
    else:
        return True, ''


ModelBase = declarative_base(cls=BaseModelClass)
