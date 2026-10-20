"""Pinned static plan model for AA ``luaCall(...)`` programs.

The native compiler routes single-line ``luaCall`` records to the owned Lua
program profile.  Tables in the pinned corpus additionally call CE helper
functions such as ``lua_aobscan("symbol","mod.exe","EB ** ...")`` from inside
``luaCall``; those helpers are not part of the owned profile and must be
resolved through an explicit, injectable binding at runtime.

This module is a pure static planning layer: it never executes Lua, never
reads a target process and never modifies a source.  It pins, once and
deterministically:

    * which ``luaCall`` operations a program carries, per phase, with the
      exact 1-based line number;
    * which of those operations reference an AOB helper
      (``lua_aobscan`` / ``ct2trainerNthAOB``) together with the
      normalized symbol / module / pattern / occurrence arguments;
    * which Lua functions and AOB port a runtime binding must provide
      (``validate_luacall_binding``), refusing by name when a reference is
      unsatisfied;
    * a deterministic operation order for later engine integration
      (``plan_luacall_ops``) — plan only, no execution.

Pinned decisions (fail-closed, no silent defaults):

    * The program envelope must carry exactly ``[ENABLE]`` then an optional
      ``[DISABLE]`` (case-insensitive, exact lines) — identical to the Lua
      program profile.  ``{$lua}``/``{$asm}`` mode sections are refused:
      mixed programs are planned by the Lua program profile path.
    * A ``luaCall`` in the preamble (before ``[ENABLE]``) executes when the
      table is enabled and is attributed to the ``enable`` phase.
    * Call expressions are a strict single-line grammar:
      ``name(arg, arg, ...)`` where each argument is a string literal
      (single or double quoted, escapes limited to ``\\`` ``\\"`` ``\\'``
      ``\\n`` ``\\t`` ``\\r``), a decimal number, or a plain Lua identifier.
      Nested calls, extra statements, trailing content and any other syntax
      are refused (no side-effect inference).
    * AOB helpers are recognized case-sensitively on the exact names
      ``lua_aobscan`` (3 arguments) and ``ct2trainerNthAOB``
      (3 or 4 arguments; the fourth is the occurrence number).  Any other
      argument shape for these names is a parse refusal.
    * AOB patterns keep the corpus wildcard spelling (``**``) at the source
      level and are stored in the canonical ``?`` form after the same
      ``* -> ?`` translation as the reviewed nth-AOB adapter, so both
      helpers share one pattern semantics.
    * One AOB symbol may carry exactly one definition (module, pattern,
      occurrence) across the whole program; identical repetitions are kept
      as separate operations in source order.
    * ``one_shot`` is true when the program carries operations in the
      enable phase and none in the disable phase — the single publish is
      irreversible (wish-save contract).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .aa import AAError, normalize_pattern, validate_symbol
from .patterns import pattern_has_placeholder_token
from .lua_program import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_LINES,
    _AALex,
    _LUA_CALL,
    _MODE,
    _PHASE,
    _lua_call_source,
    LuaProgramError,
)
from .nth_aob import MAX_RESULTS, NthAOBError, _module_name


SCHEMA = 'ct2trainer-aa-luacall-plan/v1'
MAX_LUA_CALLS = 64
MAX_CALL_ARGUMENTS = 64
MAX_STRING_BYTES = 8192
MAX_EXPRESSION_BYTES = 16384
MAX_NUMBER_VALUE = 2 ** 31 - 1
MAX_FUNCTION_NAME = 128
AOB_FUNCTIONS = ('lua_aobscan', 'ct2trainerNthAOB')
_ESCAPE = {'\\\\': '\\', '\\"': '"', "'\\'": "'", '\\n': '\n',
           '\\t': '\t', '\\r': '\r'}
_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
# Integer or simple decimal (corpus shape: speedhack_setSpeed(2.5)); exponents
# and leading-dot forms stay outside the pinned grammar.
_NUMBER = re.compile(r'[0-9]+(?:\.[0-9]+)?')


class LuaCallError(ValueError):
    """Base error for the pinned luaCall plan model."""


class LuaCallParseError(LuaCallError):
    """Malformed program or call expression; the optional line is 1-based."""

    def __init__(self, message: str, *, line: int | None = None):
        self.line = line
        super().__init__(f'line {line}: {message}' if line is not None else message)


class LuaCallBindingRefused(LuaCallError):
    """A binding does not satisfy a reference carried by a plan."""

    def __init__(self, message: str, *, line: int | None = None):
        self.line = line
        super().__init__(f'line {line}: {message}' if line is not None else message)


@dataclass(frozen=True)
class LuaCallArgument:
    """One strict argument: ``string`` | ``number`` | ``symbol`` value."""
    kind: str
    value: Any


@dataclass(frozen=True)
class ParsedCall:
    """Deterministic AST for one ``name(arg, arg, ...)`` expression."""
    function: str
    arguments: tuple


@dataclass(frozen=True)
class LuaCallOp:
    """One ``luaCall`` line in one phase, with its AOB reference if any."""
    phase: str
    line: int
    expression: str
    function: str
    arguments: tuple
    aob: dict | None = None

    def as_dict(self) -> dict:
        return {'phase': self.phase, 'line': self.line,
                'expression': self.expression, 'function': self.function,
                'arguments': [[argument.kind, argument.value] for argument in self.arguments],
                'aob': dict(self.aob) if self.aob is not None else None}


@dataclass(frozen=True)
class LuaCallPlan:
    """All luaCall references of one program, in source order."""
    schema: str
    one_shot: bool
    operations: tuple
    aob_symbols: tuple

    def report(self) -> dict:
        return {'schema': self.schema, 'one_shot': self.one_shot,
                'operations': [op.as_dict() for op in self.operations],
                'aob_symbols': list(self.aob_symbols)}


def _canonical_argument(argument: LuaCallArgument) -> str:
    if argument.kind == 'string':
        return '"' + str(argument.value).replace('\\', '\\\\').replace('"', '\\"') + '"'
    if argument.kind == 'number':
        return str(argument.value)
    return str(argument.value)


def _parse_identifier(text: str, index: int, line: int | None) -> tuple[str, int]:
    match = _IDENTIFIER.match(text, index)
    if match is None or len(match.group()) > MAX_FUNCTION_NAME:
        raise LuaCallParseError('expected a plain Lua identifier', line=line)
    return match.group(), match.end()


def _parse_string(text: str, index: int, line: int | None) -> tuple[str, int]:
    quote = text[index]
    index += 1
    chars: list[str] = []
    while index < len(text):
        char = text[index]
        if char == '\\':
            escape = text[index:index + 2]
            if escape not in _ESCAPE:
                raise LuaCallParseError(
                    f'unsupported escape {escape!r} in a quoted string', line=line)
            chars.append(_ESCAPE[escape])
            index += 2
            continue
        if char == quote:
            value = ''.join(chars)
            if len(value.encode('utf-8')) > MAX_STRING_BYTES:
                raise LuaCallParseError('string argument exceeds its byte bound', line=line)
            return value, index + 1
        chars.append(char)
        index += 1
    raise LuaCallParseError('unterminated quoted string', line=line)


def _parse_argument(text: str, index: int, line: int | None) -> tuple[LuaCallArgument, int]:
    if index >= len(text):
        raise LuaCallParseError('missing call argument', line=line)
    char = text[index]
    if char in {'"', "'"}:
        value, index = _parse_string(text, index, line)
        return LuaCallArgument('string', value), index
    if char in '0123456789':
        match = _NUMBER.match(text, index)
        if match is None:
            raise LuaCallParseError('numbers must be plain decimal arguments', line=line)
        raw = match.group()
        try:
            value = float(raw) if '.' in raw else int(raw)
        except (OverflowError, ValueError) as exc:
            raise LuaCallParseError('numeric argument exceeds its bound', line=line) from exc
        if value > MAX_NUMBER_VALUE:
            raise LuaCallParseError('numeric argument exceeds its bound', line=line)
        return LuaCallArgument('number', value), match.end()
    if ('a' <= char <= 'z') or ('A' <= char <= 'Z') or char == '_':
        value, index = _parse_identifier(text, index, line)
        return LuaCallArgument('symbol', value), index
    raise LuaCallParseError(f'unsupported call argument at {char!r}', line=line)


def parse_luacall(expression: str, *, line: int | None = None) -> ParsedCall:
    """Parse one strict ``name(arg, ...)`` call expression.

    Returns a deterministic :class:`ParsedCall`; any other syntax is refused
    with :class:`LuaCallParseError` (no side-effect inference, no nesting).
    The optional 1-based ``line`` is carried into every refusal.
    """
    if type(expression) is not str:
        raise LuaCallParseError('luaCall expression must be text', line=line)
    text = expression.strip()
    if '\n' in text or '\r' in text:
        raise LuaCallParseError('luaCall expression must be a single line', line=line)
    if not text or len(text) > MAX_EXPRESSION_BYTES:
        raise LuaCallParseError('luaCall expression must be a bounded nonempty line', line=line)
    index = 0
    function, index = _parse_identifier(text, 0, line)
    while index < len(text) and text[index] in ' \t':
        index += 1
    if index >= len(text) or text[index] != '(':
        raise LuaCallParseError('call requires an open parenthesis', line=line)
    index += 1
    arguments: list[LuaCallArgument] = []
    while True:
        while index < len(text) and text[index] in ' \t':
            index += 1
        if index >= len(text):
            raise LuaCallParseError('call expression is missing a closing parenthesis', line=line)
        if text[index] == ')':
            index += 1
            break
        argument, index = _parse_argument(text, index, line)
        arguments.append(argument)
        if len(arguments) > MAX_CALL_ARGUMENTS:
            raise LuaCallParseError('call exceeds its argument bound', line=line)
        while index < len(text) and text[index] in ' \t':
            index += 1
        if index >= len(text):
            raise LuaCallParseError('call expression is missing a closing parenthesis', line=line)
        if text[index] == ',':
            index += 1
            while index < len(text) and text[index] in ' \t':
                index += 1
            if index >= len(text) or text[index] == ')':
                raise LuaCallParseError('a comma requires a following argument', line=line)
            continue
        if text[index] == ')':
            index += 1
            break
        raise LuaCallParseError('call arguments require commas between them', line=line)
    while index < len(text) and text[index] in ' \t':
        index += 1
    if index != len(text):
        raise LuaCallParseError('call expression has trailing content', line=line)
    return ParsedCall(function, tuple(arguments))


def _canonical_expression(call: ParsedCall) -> str:
    return (call.function + '('
            + ', '.join(_canonical_argument(argument) for argument in call.arguments)
            + ')')


def _string_argument(call: ParsedCall, position: int, label: str, line: int) -> str:
    argument = call.arguments[position]
    if argument.kind != 'string':
        raise LuaCallParseError(
            f'{label} of {call.function} must be a quoted string', line=line)
    return str(argument.value)


def _recognize_aob(call: ParsedCall, line: int) -> dict | None:
    if call.function not in AOB_FUNCTIONS:
        return None
    count = len(call.arguments)
    if count not in (3, 4):
        raise LuaCallParseError(
            f'{call.function} requires 3 or 4 arguments, got {count}', line=line)
    try:
        symbol = validate_symbol(_string_argument(call, 0, 'symbol', line))
        module = _module_name(_string_argument(call, 1, 'module', line))
        raw = _string_argument(call, 2, 'pattern', line).replace('*', '?')
        # WP-57: luaCall AOB keeps its fixed-byte contract; placeholder
        # tokens keep the pre-placeholder nibble refusal, byte-identical.
        if pattern_has_placeholder_token(raw):
            raise AAError('AOB pattern contains an invalid hexadecimal/wildcard nibble.')
        pattern = normalize_pattern(raw)
    except (AAError, NthAOBError) as exc:
        raise LuaCallParseError(str(exc), line=line) from exc
    if count == 3:
        occurrence = 1
    else:
        argument = call.arguments[3]
        if argument.kind != 'number':
            raise LuaCallParseError(
                f'{call.function} occurrence must be a decimal number', line=line)
        occurrence = int(argument.value)
        if not 1 <= occurrence <= MAX_RESULTS:
            raise LuaCallParseError(
                f'{call.function} occurrence is outside its bounded range', line=line)
    return {'symbol': symbol, 'module': module,
            'pattern': pattern, 'occurrence': occurrence}


def _check_aob_conflicts(operations: list[LuaCallOp]) -> None:
    definitions: dict[str, tuple] = {}
    for operation in operations:
        if operation.aob is None:
            continue
        key = operation.aob['symbol'].casefold()
        value = (operation.aob['module'].casefold(),
                 operation.aob['pattern'], operation.aob['occurrence'])
        previous = definitions.get(key)
        if previous is not None and previous != value:
            raise LuaCallParseError(
                f"AOB symbol '{operation.aob['symbol']}' is defined more than "
                'once with different arguments', line=operation.line)
        definitions[key] = value


def analyze_luacall_program(source: str) -> LuaCallPlan:
    """Plan every ``luaCall`` reference of one AA program, statically.

    Phase structure mirrors the Lua program profile (``[ENABLE]`` then
    optional ``[DISABLE]``); mode sections are refused.  The returned plan
    carries operations in source order and a canonical AOB symbol list.
    """
    if type(source) is not str:
        raise LuaCallParseError('AA program source must be text')
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    try:
        size = len(source.encode('utf-8'))
    except UnicodeError as exc:
        raise LuaCallParseError('AA program source must be valid UTF-8 text') from exc
    if size > MAX_SOURCE_BYTES:
        raise LuaCallParseError('AA program source exceeds its size bound')
    lines = source.split('\n')
    if len(lines) > MAX_SOURCE_LINES:
        raise LuaCallParseError('AA program source exceeds its line bound')
    aa = _AALex()
    phase = 'preamble'
    seen: list[str] = []
    operations: list[LuaCallOp] = []
    for line_index, line in enumerate(lines):
        marker = _MODE.fullmatch(line)
        if marker is not None and aa.neutral:
            raise LuaCallParseError(
                'AA mode sections are planned by the Lua program profile, '
                'not the luacall plan model', line=line_index + 1)
        was_quoted = aa.quote
        visible = aa.line(line, allow_lua_call=True)
        header = _PHASE.fullmatch(visible) if not was_quoted else None
        if header is not None:
            next_phase = header.group(1).casefold()
            if next_phase in seen or (next_phase == 'disable' and seen != ['enable']):
                raise LuaCallParseError(
                    'AA program phases are duplicated or out of order',
                    line=line_index + 1)
            seen.append(next_phase)
            phase = next_phase
        elif not was_quoted and _LUA_CALL.match(visible) is not None:
            try:
                body = _lua_call_source(visible, aa)
            except LuaProgramError as exc:
                raise LuaCallParseError(str(exc), line=line_index + 1) from exc
            if len(operations) >= MAX_LUA_CALLS:
                raise LuaCallParseError(
                    'AA program exceeds its luaCall bound', line=line_index + 1)
            call = parse_luacall(body, line=line_index + 1)
            operation_phase = 'enable' if phase == 'preamble' else phase
            operations.append(LuaCallOp(
                phase=operation_phase, line=line_index + 1,
                expression=_canonical_expression(call), function=call.function,
                arguments=call.arguments, aob=_recognize_aob(call, line_index + 1)))
    try:
        aa.finish()
    except LuaProgramError as exc:
        raise LuaCallParseError(str(exc)) from exc
    if seen not in (['enable'], ['enable', 'disable']):
        raise LuaCallParseError(
            'AA program requires exactly [ENABLE] then [DISABLE]')
    _check_aob_conflicts(operations)
    one_shot = (any(op.phase == 'enable' for op in operations)
                and not any(op.phase == 'disable' for op in operations))
    return LuaCallPlan(
        schema=SCHEMA, one_shot=one_shot, operations=tuple(operations),
        aob_symbols=tuple(sorted({op.aob['symbol'] for op in operations
                                  if op.aob is not None}, key=str.casefold)))


class NthAobPort(ABC):
    """Injectable runtime port resolving one nth-AOB reference.

    The static plan never scans a target; the engine binds this port for a
    verified target process and calls ``scan`` at publish time.
    """

    @abstractmethod
    def scan(self, *, symbol: str, module: str, pattern: str,
             occurrence: int) -> int:
        """Return the resolved address of the occurrence-th match."""


class LuaCallBinding(ABC):
    """What a runtime must provide for a plan's Lua references.

    Mirrors the dependency-inversion style of the AA directive ports: the
    plan names its references, the binding proves it covers them, and the
    engine injects the concrete implementation later.
    """

    @abstractmethod
    def function_names(self) -> frozenset:
        """Lua function names provided for this target."""

    @abstractmethod
    def aob_port(self) -> NthAobPort | None:
        """Injectable AOB port for AOB references, or ``None``."""


def validate_luacall_binding(plan: LuaCallPlan, binding: Any) -> None:
    """Refuse, by exact name, any plan reference the binding does not cover.

    Checks run in source order over the plan's operations:
    every referenced Lua function must be provided, and every AOB
    reference requires the binding's ``aob_port`` field.
    """
    if type(plan) is not LuaCallPlan:
        raise LuaCallBindingRefused('binding validation requires a LuaCallPlan')
    if binding is None or not isinstance(binding, LuaCallBinding):
        raise LuaCallBindingRefused(
            "binding is missing 'function_names'/'aob_port' (no binding given)")
    names = binding.function_names()
    if type(names) is not frozenset or not all(type(name) is str for name in names):
        raise LuaCallBindingRefused(
            "binding 'function_names' must be a frozenset of str")
    port = binding.aob_port()
    if port is not None and not isinstance(port, NthAobPort):
        raise LuaCallBindingRefused("binding 'aob_port' must be a NthAobPort")
    for operation in plan.operations:
        if operation.function not in names:
            raise LuaCallBindingRefused(
                f"binding does not provide Lua function '{operation.function}'",
                line=operation.line)
        if operation.aob is not None and port is None:
            raise LuaCallBindingRefused(
                f"binding 'aob_port' is required for AOB reference "
                f"'{operation.aob['symbol']}'", line=operation.line)


def plan_luacall_ops(plan: LuaCallPlan) -> list[dict]:
    """Deterministic operation order for engine integration (plan only).

    Operations are ordered by phase (enable before disable) and then by
    line number; nothing is executed and no target is touched.
    """
    if type(plan) is not LuaCallPlan:
        raise LuaCallError('operation planning requires a LuaCallPlan')
    order = {'enable': 0, 'disable': 1}
    operations = sorted(plan.operations,
                        key=lambda op: (order[op.phase], op.line, op.expression))
    return [{'op': 'luacall',
             'phase': op.phase,
             'line': op.line,
             'expression': op.expression,
             'function': op.function,
             'arguments': [[argument.kind, argument.value] for argument in op.arguments],
             'aob': dict(op.aob) if op.aob is not None else None,
             'port': 'aob' if op.aob is not None else 'lua'}
            for op in operations]


def has_luacall(source: str) -> bool:
    """Return True for pure-AA programs carrying at least one visible luaCall.

    Mode sections (``{$lua}``/``{$asm}``) route the record to the Lua program
    profile instead, which is the plan model's explicit domain exclusion: a
    mode marker in neutral position decides the result as False immediately,
    regardless of line order, and the detector never lexes past the marker
    (the AA lexer does not own delimiter lines).  Quoted or commented text
    never counts.  Lexical errors are the caller's program parser to report,
    not this detector's.
    """
    if type(source) is not str:
        return False
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    aa = _AALex()
    for line in source.split('\n'):
        marker = _MODE.fullmatch(line)
        if aa.neutral and marker is not None:
            return False
        was_quoted = aa.quote
        visible = aa.line(line, allow_lua_call=True)
        if not was_quoted and _LUA_CALL.match(visible) is not None:
            return True
    return False


def validate_luacall_plan(report: Any) -> None:
    """Fail-closed shape check for one serialized ``lua_call_plan`` report.

    Every field is bounded exactly as the producer bounds it, so a tampered
    plan (wrong schema, oversized lists, malformed AOB references) is refused
    before any engine logic reads it.
    """
    if (type(report) is not dict
            or set(report) != {'schema', 'one_shot', 'operations', 'aob_symbols'}):
        raise LuaCallParseError('luaCall plan report has an invalid shape')
    if report['schema'] != SCHEMA:
        raise LuaCallParseError('luaCall plan report carries an unknown schema')
    if type(report['one_shot']) is not bool:
        raise LuaCallParseError('luaCall plan one-shot flag must be a boolean')
    operations = report['operations']
    if not isinstance(operations, list) or len(operations) > MAX_LUA_CALLS:
        raise LuaCallParseError('luaCall plan operation list is out of bounds')
    for operation in operations:
        if (type(operation) is not dict
                or set(operation) != {'phase', 'line', 'expression', 'function',
                                      'arguments', 'aob'}):
            raise LuaCallParseError('luaCall plan operation has an invalid shape')
        if operation['phase'] not in {'enable', 'disable'}:
            raise LuaCallParseError('luaCall plan operation phase is invalid')
        if type(operation['line']) is not int or not 1 <= operation['line'] <= MAX_SOURCE_LINES:
            raise LuaCallParseError('luaCall plan operation line is out of bounds')
        if (type(operation['expression']) is not str or not operation['expression']
                or len(operation['expression'].encode('utf-8')) > MAX_EXPRESSION_BYTES):
            raise LuaCallParseError('luaCall plan operation expression is out of bounds')
        if type(operation['function']) is not str or not 1 <= len(operation['function']) <= MAX_FUNCTION_NAME:
            raise LuaCallParseError('luaCall plan operation function name is out of bounds')
        arguments = operation['arguments']
        if not isinstance(arguments, list) or len(arguments) > MAX_CALL_ARGUMENTS:
            raise LuaCallParseError('luaCall plan operation argument list is out of bounds')
        for argument in arguments:
            if (not isinstance(argument, list) or len(argument) != 2
                    or argument[0] not in {'string', 'number', 'symbol'}):
                raise LuaCallParseError('luaCall plan argument kind is invalid')
        aob = operation['aob']
        if aob is not None:
            if (type(aob) is not dict
                    or set(aob) != {'symbol', 'module', 'pattern', 'occurrence'}
                    or type(aob['symbol']) is not str or type(aob['module']) is not str
                    or type(aob['pattern']) is not str or type(aob['occurrence']) is not int
                    or not 1 <= aob['occurrence'] <= MAX_RESULTS):
                raise LuaCallParseError('luaCall plan AOB reference is malformed')
    symbols = report['aob_symbols']
    if (not isinstance(symbols, list) or len(symbols) > MAX_LUA_CALLS
            or len({str(symbol).casefold() for symbol in symbols}) != len(symbols)):
        raise LuaCallParseError('luaCall plan AOB symbol list is malformed')
    for symbol in symbols:
        if type(symbol) is not str:
            raise LuaCallParseError('luaCall plan AOB symbols must be text')


def plan_from_report(report: Any) -> LuaCallPlan:
    """Rebuild the frozen plan from a validated serialized report."""
    validate_luacall_plan(report)
    operations = tuple(
        LuaCallOp(phase=operation['phase'], line=operation['line'],
                  expression=operation['expression'], function=operation['function'],
                  arguments=tuple(LuaCallArgument(kind=argument[0], value=argument[1])
                                  for argument in operation['arguments']),
                  aob=dict(operation['aob']) if operation['aob'] is not None else None)
        for operation in report['operations'])
    return LuaCallPlan(schema=SCHEMA, one_shot=report['one_shot'],
                       operations=operations, aob_symbols=tuple(report['aob_symbols']))
