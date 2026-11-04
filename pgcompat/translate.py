"""SQLite SQL, as the services write it, turned into Postgres SQL for psycopg.

sqlglot does the general translation; the transforms here cover what it leaves in SQLite's dialect and
what this codebase relies on: printf('%04d') folios, COLLATE NOCASE comparisons, INSERT OR IGNORE,
json_extract over TEXT payloads, `a IS NOT b` between columns, and the `?` parameters.
"""
import re
from functools import lru_cache

import sqlglot
from sqlglot import exp

PARAM = '\x00P\x00'
NAMED = '\x00N'
_NAMED = re.compile('\x00N(\\w+)\x00N')
_PRINTF_PAD = re.compile(r"^%0(\d+)d$")
# SQLite reads `a IS b` / `a IS NOT b` as null-safe equality for any operands; sqlglot only parses it with NULL.
_IS_NOT = re.compile(r"\bIS\s+NOT\s+(?!NULL\b|TRUE\b|FALSE\b|DISTINCT\b)", re.I)
_IS = re.compile(r"\bIS\s+(?!NOT\b|NULL\b|TRUE\b|FALSE\b|DISTINCT\b)", re.I)


def _nocase(node):
    """`x COLLATE NOCASE` → LOWER(x): SQLite's case-insensitive comparison and ordering."""
    if isinstance(node, exp.Collate) and node.expression.name.upper() == 'NOCASE':
        return exp.Lower(this=node.this)
    return node


def _comparison_nocase(node):
    """`a = b COLLATE NOCASE` compares both sides without case, as SQLite does."""
    if isinstance(node, (exp.EQ, exp.NEQ)) and isinstance(node.expression, exp.Lower) and not isinstance(node.this, exp.Lower):
        node.set('this', exp.Lower(this=node.this))
    return node


def _functions(node):
    if isinstance(node, exp.Anonymous):
        name = node.name.upper()
        args = node.expressions
        if name == 'PRINTF' and len(args) == 2 and isinstance(args[0], exp.Literal):
            if match := _PRINTF_PAD.match(args[0].this):
                return exp.func('LPAD', exp.cast(args[1], 'TEXT'), exp.Literal.number(int(match.group(1))), exp.Literal.string('0'))
    if isinstance(node, (exp.JSONExtract, exp.JSONExtractScalar)):
        # json_extract(payload,'$.client') over a TEXT column: the scalar as text.
        path = node.expression
        key = path.this if isinstance(path, exp.Literal) else path.sql()
        if isinstance(path, exp.JSONPath):
            key = '.'.join(str(p.this) for p in path.expressions if isinstance(p, exp.JSONPathKey))
        key = str(key)
        if key.startswith('$.'):
            key = key[2:]
        parts = [exp.Literal.string(k) for k in key.split('.') if k]
        return exp.func('JSONB_EXTRACT_PATH_TEXT', exp.cast(node.this, 'JSONB'), *parts)
    if isinstance(node, exp.Placeholder):
        # `?` positional, or `:name` named (consumables use named parameters).
        name = node.name
        return exp.Var(this=f'{NAMED}{name}{NAMED}' if name and name != '?' else PARAM)
    if isinstance(node, exp.Column) and node.name.lower() == 'rowid' and not node.table:
        # SQLite's implicit row number, used to read tables in insertion order: Postgres's physical row id.
        return exp.column('ctid')
    if isinstance(node, (exp.Add, exp.Sub)):
        # SQLite adds comparisons as 0/1 (e.g. "exactly one of these is set"); Postgres needs them as integers.
        for side in ('this', 'expression'):
            operand = node.args.get(side)
            inner = operand.unnest() if isinstance(operand, exp.Paren) else operand
            if isinstance(inner, exp.Predicate) or isinstance(inner, exp.Not):
                node.set(side, exp.cast(exp.paren(inner, copy=False), 'INT'))
    return node


_TRUTHY = (exp.Column, exp.Placeholder, exp.Literal, exp.Anonymous, exp.Coalesce, exp.Max, exp.Min, exp.Sum, exp.Count, exp.Cast)


def _as_condition(node):
    """SQLite reads any number as a truth value; Postgres wants a boolean: x → (x) <> 0."""
    inner = node.unnest() if isinstance(node, exp.Paren) else node
    if isinstance(inner, _TRUTHY) and not (isinstance(inner, exp.Cast) and inner.to.this == exp.DataType.Type.BOOLEAN):
        return exp.NEQ(this=exp.paren(inner, copy=False), expression=exp.Literal.number(0))
    return node


def _booleans(node):
    if isinstance(node, (exp.And, exp.Or)):
        node.set('this', _as_condition(node.this))
        node.set('expression', _as_condition(node.expression))
    elif isinstance(node, (exp.Not, exp.Where, exp.Having)):
        node.set('this', _as_condition(node.this))
    elif isinstance(node, exp.If):
        node.set('this', _as_condition(node.this))
    elif isinstance(node, exp.Is) and isinstance(node.this, exp.Placeholder):
        # `? IS NULL` with a None parameter has no type for Postgres; only its nullness matters.
        node.set('this', exp.cast(node.this, 'TEXT'))
    return node


def _insert_or_ignore(tree):
    if isinstance(tree, exp.Insert) and (tree.args.get('alternative') or '').upper() == 'IGNORE':
        tree.set('alternative', None)
        tree.set('conflict', exp.OnConflict(action=exp.Var(this='DO NOTHING')))
    return tree


@lru_cache(maxsize=4096)
def to_postgres(sql: str) -> str:
    """Postgres SQL with psycopg `%s` parameters and literal `%` escaped."""
    source = _IS_NOT.sub('IS DISTINCT FROM ', sql)
    source = _IS.sub('IS NOT DISTINCT FROM ', source)
    statements = [s for s in sqlglot.parse(source, read='sqlite') if s is not None]
    out = []
    for tree in statements:
        tree = _insert_or_ignore(tree)
        tree = tree.transform(_nocase).transform(_comparison_nocase).transform(_booleans).transform(_functions)
        out.append(tree.sql(dialect='postgres'))
    text = ';\n'.join(out)
    return _NAMED.sub(r'%(\1)s', text.replace('%', '%%').replace(PARAM, '%s'))


def explicit_id(sql: str) -> bool:
    """Whether an INSERT names the id column itself."""
    match = re.match(r"\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+\"?\w+\"?\s*\(([^)]*)\)", sql, re.I)
    return bool(match) and 'id' in [c.strip().strip('"').lower() for c in match.group(1).split(',')]


def insert_target(sql: str):
    """The table an INSERT writes to, or None: to return its new id like sqlite3's lastrowid."""
    match = re.match(r"\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+\"?(\w+)\"?", sql, re.I)
    return match.group(1).lower() if match else None
