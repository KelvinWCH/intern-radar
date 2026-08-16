from psycopg import Connection, sql
from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from job_backend.common.text_matching import normalized_text
from job_backend.persistence.models import Document, Filter, Junction, Order, ReadPage, ReadQuery
from job_backend.persistence.projections import READ_FIELDS

_DOCUMENT = TypeAdapter(Document)
_VALUE = TypeAdapter(str | None)


def _value(field: str, timezone: str) -> sql.Composable:
    if field == "@revision":
        return sql.SQL("to_jsonb(r.revision)")
    if field == "@key":
        return sql.SQL("to_jsonb(r.key)")
    if field == "@status":
        return sql.SQL(
            "to_jsonb(COALESCE((SELECT u.data ->> 'status' FROM job_record_reads u "
            "WHERE u.collection = 'job_user_data' AND u.key = r.key), 'new'))"
        )
    if field == "@match_score":
        return sql.SQL(
            "(SELECT m.data -> 'score' FROM job_records m "
            "WHERE m.collection = 'job_matches' AND m.key = r.key)"
        )
    if field == "@location":
        return sql.SQL(
            "to_jsonb(COALESCE((SELECT string_agg(v, ' ') FROM "
            "jsonb_array_elements_text(r.data -> 'locations') v), ''))"
        )
    if field == "@labels":
        return sql.SQL(
            "to_jsonb(concat_ws(' ', r.data ->> 'title', r.data ->> 'company', {}))"
        ).format(_text("@location", timezone))
    if field == "@elapsed":
        return sql.SQL(
            "to_jsonb(greatest(0, floor(COALESCE(NULLIF({finish}, 0), "
            "extract(epoch FROM clock_timestamp())) - {start})))"
        ).format(
            finish=number_expression("finished_at", timezone),
            start=number_expression("started_at", timezone),
        )
    if field == "@outside_gta":
        return sql.SQL(
            "to_jsonb(CASE WHEN r.data -> 'is_toronto_area' = 'true'::jsonb THEN 0 ELSE 1 END)"
        )
    if field == "@event_day":
        return sql.SQL(
            "to_jsonb((to_timestamp({}::double precision) AT TIME ZONE {})::date::text)"
        ).format(number_expression("occurred_at", timezone), sql.Literal(timezone))
    if field == "@engineering":
        return sql.SQL(
            "to_jsonb(CASE WHEN r.data ->> 'title' ~* "
            "'\\y(developers?|dev|swe|sde|engineers?|engineering|eng)\\y' "
            "THEN 0 ELSE 1 END)"
        )
    if field == "@day":
        number = number_expression("date_posted", timezone)
        return sql.SQL(
            "to_jsonb((CASE WHEN {n} IS NULL "
            "THEN to_timestamp({seen}::double precision) AT TIME ZONE {zone} "
            "ELSE to_timestamp({n}::double precision) AT TIME ZONE "
            "CASE WHEN mod({n}, 86400) = 0 THEN 'UTC' ELSE {zone} END END)::date::text)"
        ).format(
            n=number,
            seen=number_expression("first_seen_at", timezone),
            zone=sql.Literal(timezone),
        )
    return (
        sql.SQL("r.data -> {}").format(sql.Literal(field))
        if "." not in field
        else sql.SQL("r.data #> {}").format(sql.Literal(field.split(".")))
    )


def _text(field: str, timezone: str) -> sql.Composable:
    if field == "@key":
        return sql.SQL("r.key")
    if not field.startswith("@"):
        return (
            sql.SQL("(r.data ->> {})").format(sql.Literal(field))
            if "." not in field
            else sql.SQL("(r.data #>> {})").format(sql.Literal(field.split(".")))
        )
    return sql.SQL("({} #>> '{{}}')").format(_value(field, timezone))


def number_expression(field: str, timezone: str) -> sql.Composed:
    value = _value(field, timezone)
    return sql.SQL("(CASE WHEN jsonb_typeof({v}) = 'number' THEN ({text})::numeric END)").format(
        v=value, text=_text(field, timezone)
    )


def filter_expression(
    predicate: Filter | Junction, query: ReadQuery, params: list[object]
) -> sql.Composable:
    if isinstance(predicate, Junction):
        if not predicate.children:
            return sql.SQL("TRUE" if predicate.mode == "and" else "FALSE")
        return sql.SQL("({})").format(
            sql.SQL(" AND " if predicate.mode == "and" else " OR ").join(
                filter_expression(child, query, params) for child in predicate.children
            )
        )
    field, op, value = predicate.field, predicate.op, predicate.value
    expression = _value(field, query.timezone)
    if op in {"eq", "ne"}:
        params.append(Jsonb(value))
        if value is not None:
            comparison = sql.SQL("{} {} %s::jsonb").format(
                expression, sql.SQL("=" if op == "eq" else "<>")
            )
            return (
                comparison
                if op == "eq"
                else sql.SQL("({} IS NULL OR {})").format(expression, comparison)
            )
        return sql.SQL("COALESCE({}, 'null'::jsonb) {} %s::jsonb").format(
            expression, sql.SQL("=" if op == "eq" else "<>")
        )
    if op == "in":
        if not isinstance(value, list):
            raise ValueError("Membership filters require a list")
        params.append([Jsonb(item) for item in value])
        comparison = sql.SQL("{} = ANY(%s::jsonb[])").format(expression)
        return (
            sql.SQL("({} IS NULL OR {})").format(expression, comparison)
            if None in value
            else comparison
        )
    if op == "contains":
        if not isinstance(value, str):
            raise ValueError("Text filters require a string")
        needle = normalized_text(value)
        if needle:
            haystack = (
                sql.SQL("r.search_body")
                if field == "@body"
                else sql.SQL("job_normalized_text(COALESCE({}, ''))").format(
                    _text(field, query.timezone)
                )
            )
        else:
            needle = value.strip().casefold()
            haystack = (
                sql.SQL(
                    "(SELECT casefold(COALESCE(j.data ->> 'raw_description', '') COLLATE "
                    '"pg_unicode_fast") FROM job_records j WHERE '
                    "j.collection = r.collection AND j.key = r.key)"
                )
                if field == "@body"
                else sql.SQL("casefold(COALESCE({}, '') COLLATE \"pg_unicode_fast\")").format(
                    _text(field, query.timezone)
                )
            )
        params.append(needle)
        return sql.SQL("strpos({}, %s) > 0").format(haystack)
    params.append(value)
    operators = {"ge": sql.SQL(">="), "gt": sql.SQL(">"), "lt": sql.SQL("<"), "le": sql.SQL("<=")}
    numeric = isinstance(value, int | float) and not isinstance(value, bool)
    expression = (
        number_expression(field, query.timezone) if numeric else _text(field, query.timezone)
    )
    return sql.SQL("{} {} %s").format(expression, operators[op])


def _base(query: ReadQuery, params: list[object]) -> sql.Composable:
    if query.source and not query.fields:
        raise ValueError("Source projections require an explicit field allowlist")
    if not query.source and query.collection not in READ_FIELDS:
        raise ValueError("No compact projection is defined for this collection")
    params.append(query.collection)
    return sql.SQL("r.collection = %s AND ({})").format(
        filter_expression(query.where, query, params)
    )


def _order(order: Order, query: ReadQuery, params: list[object]) -> sql.Composable:
    if order.ranks:
        params.append(Jsonb(dict(order.ranks)))
        expression = sql.SQL("COALESCE((%s::jsonb ->> {})::integer, 2)").format(
            _text(order.field, query.timezone)
        )
    elif order.numeric:
        expression = number_expression(order.field, query.timezone)
    else:
        expression = sql.SQL('casefold({} COLLATE "pg_unicode_fast") COLLATE "C"').format(
            _text(order.field, query.timezone)
        )
        if order.field == "@key":
            expression = sql.SQL("r.key")
    return sql.SQL("{} {} NULLS LAST").format(
        expression, sql.SQL("DESC" if order.descending else "ASC")
    )


def _group(query: ReadQuery) -> sql.Composable:
    if query.distinct is None:
        raise ValueError("Grouped reads require a distinct field")
    return sql.SQL("COALESCE({}, r.key)").format(_text(query.distinct, query.timezone))


def select_page(
    connection: Connection[tuple[object, ...]],
    query: ReadQuery,
    *,
    limit: int,
    offset: int = 0,
    count: bool = True,
) -> ReadPage:
    if not 1 <= limit <= 1000 or offset < 0:
        raise ValueError("Projected reads require a limit of 1..1000 and nonnegative offset")
    params: list[object] = []
    where = _base(query, params)
    table = sql.Identifier("job_records" if query.source else "job_record_reads")
    projection = (
        sql.SQL("r.data")
        if query.fields is None
        else sql.SQL("jsonb_build_object({})").format(
            sql.SQL(", ").join(
                part
                for field in query.fields
                for part in (sql.Literal(field), _value(field, query.timezone))
            )
        )
    )
    if query.distinct is None:
        source = sql.SQL("{} r WHERE {}").format(table, where)
    else:
        group = _group(query)
        inner = sql.SQL(", ").join(
            (
                sql.SQL("{} ASC").format(group),
                *(_order(item, query, params) for item in (*query.lead, *query.order)),
                sql.SQL("r.key"),
            )
        )
        source = sql.SQL("(SELECT DISTINCT ON ({}) r.* FROM {} r WHERE {} ORDER BY {}) r").format(
            group, table, where, inner
        )
    ordering = (
        sql.SQL(", ").join(_order(item, query, params) for item in query.order)
        if query.order
        else sql.SQL("r.key")
    )
    count_params: list[object] = []
    count_where = _base(query, count_params)
    statement = sql.SQL("SELECT {} FROM {} ORDER BY {} LIMIT %s OFFSET %s").format(
        projection, source, ordering
    )
    params.extend((limit, offset))
    counted = (
        sql.SQL("count(*)")
        if query.distinct is None
        else sql.SQL("count(DISTINCT {})").format(_group(query))
    )
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        total = None
        if count:
            row = connection.execute(
                sql.SQL("SELECT {} FROM {} r WHERE {}").format(counted, table, count_where),
                count_params,
            ).fetchone()
            if row is None or not isinstance(row[0], int):
                raise ValueError("Invalid database count")
            total = row[0]
        rows = connection.execute(statement, params).fetchall()
    return ReadPage([_DOCUMENT.validate_python(row[0], strict=True) for row in rows], total)


def grouped(
    connection: Connection[tuple[object, ...]],
    query: ReadQuery,
    fields: tuple[str, ...],
    sums: tuple[str, ...] = (),
) -> list[Document]:
    params: list[object] = []
    where = _base(query, params)
    if query.source:
        raise ValueError("Aggregates use compact read models")
    parts: list[sql.Composable] = []
    for field in fields:
        parts.extend((sql.Literal(field), _value(field, query.timezone)))
    counted = (
        sql.SQL("count(*)")
        if query.distinct is None
        else sql.SQL("count(DISTINCT {})").format(_group(query))
    )
    parts.extend((sql.Literal("count"), counted))
    for field in sums:
        parts.extend(
            (
                sql.Literal(field),
                sql.SQL("sum({})").format(number_expression(field, query.timezone)),
            )
        )
    group = (
        sql.SQL(" GROUP BY {}").format(
            sql.SQL(", ").join(_value(field, query.timezone) for field in fields)
        )
        if fields
        else sql.SQL("")
    )
    statement = sql.SQL("SELECT jsonb_build_object({}) FROM job_record_reads r WHERE {}{}").format(
        sql.SQL(", ").join(parts), where, group
    )
    rows = connection.execute(statement, params).fetchall()
    return [_DOCUMENT.validate_python(row[0], strict=True) for row in rows]


def distinct_values(
    connection: Connection[tuple[object, ...]], query: ReadQuery, field: str
) -> list[str]:
    params: list[object] = []
    where = _base(query, params)
    if query.source:
        raise ValueError("Distinct labels use compact read models")
    statement = sql.SQL("SELECT DISTINCT {} FROM job_record_reads r WHERE {}").format(
        _text(field, query.timezone), where
    )
    rows = connection.execute(statement, params).fetchall()
    return [
        value for row in rows if (value := _VALUE.validate_python(row[0], strict=True)) is not None
    ]
