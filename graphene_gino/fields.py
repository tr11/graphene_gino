from functools import partial
from typing import Any

from graphene.utils.thenables import maybe_thenable
from graphql_relay import ConnectionArguments, Edge

from graphene.relay import Connection, ConnectionField
from graphene.relay.connection import PageInfo
from graphql_relay.connection.arrayconnection import (
    get_offset_with_default,
    offset_to_cursor,
)


async def connection_from_gino_array_slice(
    array_slice,
    args: ConnectionArguments = None,
    slice_start: int = 0,
    array_length: int = None,
    array_slice_length: int = None,
    connection_type: Any = Connection,
    edge_type: Any = Edge,
    page_info_type: Any = PageInfo,
) -> Connection:
    """Create a connection object from a slice of the result set."""
    args = args or {}
    before = args.get("before")
    after = args.get("after")
    first = args.get("first")
    last = args.get("last")
    if array_slice_length is None:
        array_slice_length = len(array_slice)
    slice_end = slice_start + array_slice_length
    if array_length is None:
        array_length = slice_end
    before_offset = get_offset_with_default(before, array_length)
    after_offset = get_offset_with_default(after, -1)

    start_offset = max(slice_start - 1, after_offset, -1) + 1
    end_offset = min(slice_end, before_offset, array_length)

    if isinstance(first, int):
        if first < 0:
            raise ValueError("Argument 'first' must be a non-negative integer.")

        end_offset = min(end_offset, start_offset + first)
    if isinstance(last, int):
        if last < 0:
            raise ValueError("Argument 'last' must be a non-negative integer.")

        start_offset = max(start_offset, end_offset - last)

    # If supplied slice is too large, trim it down before mapping over it.
    trimmed_slice = await array_slice[
        start_offset - slice_start : array_slice_length - (slice_end - end_offset)
    ].gino.all()

    edges = [
        edge_type(node=value, cursor=offset_to_cursor(start_offset + index))
        for index, value in enumerate(trimmed_slice)
    ]
    first_edge_cursor = edges[0].cursor if edges else None
    last_edge_cursor = edges[-1].cursor if edges else None
    upper_bound = before_offset if before else array_length

    return connection_type(
        edges=edges,
        page_info=page_info_type(
            start_cursor=first_edge_cursor,
            end_cursor=last_edge_cursor,
            has_previous_page=start_offset > 0,
            has_next_page=isinstance(first, int) and end_offset < upper_bound,
        ),
    )


class GinoConnectionSlice:
    def __init__(self, model, query):
        self.query = query
        self.model = model

    def __getitem__(self, item):
        if isinstance(item, slice):
            start = item.start or 0
            query = self.query.offset(start)
            if item.stop:
                query = query.limit(item.stop - start)
            return query

    async def length(self):
        db = self.model.__metadata__
        return (
            await db.select([db.func.count()])
            .select_from(self.query.alias("a"))
            .gino.scalar()
        )


class GinoConnectionField(ConnectionField):
    @classmethod
    async def resolve_connection(cls, connection_type, root, args, resolved):
        if isinstance(resolved, connection_type):
            return resolved
        array_slice = GinoConnectionSlice(resolved._model, resolved.join(root))
        len_ = await array_slice.length()

        connection = await connection_from_gino_array_slice(
            array_slice,
            args,
            slice_start=0,
            array_length=len_,
            array_slice_length=len_,
            connection_type=connection_type,
            edge_type=connection_type.Edge,
            page_info_type=PageInfo,
        )

        connection.iterable = resolved
        return connection

    @property
    def model(self):
        return self.type._meta.node._meta.model

    @classmethod
    def connection_resolver(cls, resolver, connection_type, root, info, **args):
        resolved = resolver(root, info, **args)
        on_resolve = partial(cls.resolve_connection, connection_type, root, args)
        return maybe_thenable(resolved, on_resolve)


def default_connection_field_factory(relationship, registry, **field_kwargs):
    model_type = registry.get_type_for_model(relationship.other)

    class ModelConnection(Connection):
        class Meta:
            node = model_type

    conn = GinoConnectionField(ModelConnection, **field_kwargs)
    return conn
