"""Pinned static block models for AA conditional and nested-assembly syntax.

The native AA grammar (``aa.py`` / ``aa_program.py``) still rejects
``{$if}`` blocks and nested ``autoassemble("Label")`` invocations
fail-closed; nothing in this module changes that behavior.  This module is a
pure static Stage-1 model for both construct families — no process, no
network, no CE input, no execution:

    * :func:`prune_conditionals` deterministically prunes
      ``{$if <name>=<value>}`` / ``{$if <name>!=<value>}`` / ``{$else}`` /
      ``{$endif}`` blocks: only the chosen branch survives, every decision
      is recorded, undefined define names are refused (never silent
      "false"), unbalanced blocks and duplicate ``{$else}`` markers are
      structural refusals, and nesting is bounded.
    * :func:`resolve_nested_assembly` resolves
      ``autoassemble("Label")`` / ``autoasm("Label")`` invocations against
      the program's own label definitions plus an injectable external label
      registry, producing a deterministic topological block order (callee
      before caller), refusing unknown labels, name collisions, duplicate
      invocations and cycles (named by path).
    * :func:`analyze_blocks` combines both models in one result with a
      deterministic error list.
    * :func:`label_spans`, :func:`parse_label`, :func:`parse_invocation`
      and :func:`extract_label_definitions` expose the same line-level
      rules as read-only helpers for pipeline wiring (AA program
      preparation, table-level label registries).

Pinned decisions (fail-closed, no silent defaults):

    * Conditional lines must be exactly ``{$if <cond>}``, ``{$else}`` or
      ``{$endif}`` (case-insensitive, surrounding whitespace allowed).  AA
      comments and strings are not lexed: a directive spelling on its own
      line is always a directive.
    * A condition is ``<name> = <value>`` or ``<name> != <value>`` where
      ``<name>`` must be a defined define and ``<value>`` is an integer
      literal (decimal, ``$``/``0x`` hex, optional sign) or another defined
      define name.  Any other shape is a structure refusal.
    * Define lookup is case-insensitive (AA define semantics); the
      ``defines`` mapping must use identifier keys and exact ``int`` values.
    * Label definitions are whole lines of the form ``name:`` (identifier,
      optional trailing ``//`` comment).  A label body runs until the next
      label line or end of source.  Address lines such as ``1000:`` are not
      named labels.
    * Invocations must be the exact whole-line form
      ``autoassemble("Label")`` / ``autoasm("Label")`` with a double-quoted
      identifier; any other spelling is opaque content.
    * Each label may be defined at most once and may be invoked at most
      once per program.  An internal definition may not collide with an
      external registry name (case-insensitive).
    * Cycle paths repeat their first label, e.g. ``("a", "b", "a")``.
    * Invocation depth: top-level invocations are depth 1; an invocation
      inside the body of label ``L`` is ``depth(L) + 1`` where ``depth(L)``
      is the depth of L's own single invocation (0 when L is never
      invoked).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SCHEMA = 'ct2trainer-aa-blocks/v1'
MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCE_LINES = 65536
MAX_CONDITIONAL_DEPTH = 16
MAX_LABELS = 256
MAX_INVOCATIONS = 256
MAX_NAME_LENGTH = 128

_IF = re.compile(r'\{\$if\s+(.+?)\s*\}\Z', re.IGNORECASE)
_ELSE = re.compile(r'\{\$else\}\Z', re.IGNORECASE)
_ENDIF = re.compile(r'\{\$endif\}\Z', re.IGNORECASE)
_CONDITION = re.compile(
    r'([A-Za-z_][A-Za-z0-9_]*)\s*(!?=)\s*'
    r'([A-Za-z_][A-Za-z0-9_]*|[+-]?(?:0x[0-9A-Fa-f]+|\$[0-9A-Fa-f]+|[0-9]+))\Z')
_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
_LABEL_LINE = re.compile(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?://.*)?\Z')
_INVOCATION = re.compile(
    r'\s*(?:autoassemble|autoasm)\s*\(\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)'
    r'\s*(?://.*)?\Z', re.IGNORECASE)


class BlockError(ValueError):
    """Base error for the pinned AA block models; ``line`` is 1-based."""

    def __init__(self, message: str, *, line: int | None = None):
        self.line = line
        super().__init__(f'line {line}: {message}' if line is not None else message)


class BlockStructureError(BlockError):
    """Unbalanced, duplicated or out-of-bounds block syntax."""


class UnknownLabelError(BlockError):
    """An invocation names a label that no registry defines."""

    def __init__(self, message: str, *, label: str, line: int | None = None):
        self.label = label
        super().__init__(message, line=line)


class LabelCollisionError(BlockError):
    """A label name is defined in both the program and the registry."""

    def __init__(self, message: str, *, label: str, line: int | None = None):
        self.label = label
        super().__init__(message, line=line)


class DuplicateInvocationError(BlockError):
    """The same label is autoassembled more than once."""

    def __init__(self, message: str, *, label: str, lines: tuple = ()):
        self.label = label
        self.lines = lines
        first = lines[0] if lines else None
        super().__init__(message, line=first or None)


class CycleError(BlockError):
    """A nested-assembly cycle; ``path`` repeats its first label."""

    def __init__(self, message: str, *, path: tuple, line: int | None = None):
        self.path = path
        super().__init__(message, line=line)


@dataclass(frozen=True)
class Decision:
    """One evaluated ``{$if}`` and the branch that survived the prune."""
    line: int
    condition: str
    chosen: str


@dataclass(frozen=True)
class BlockPlan:
    """Pruned program lines with the surviving branch of every decision.

    ``line_map`` gives the original 1-based line number of each pruned line,
    so downstream models can remap their context back to the source.
    """
    lines: tuple
    decisions: tuple
    max_depth: int
    line_map: tuple

    def report(self) -> dict:
        return {'schema': SCHEMA,
                'lines': list(self.lines),
                'decisions': [{'line': d.line, 'condition': d.condition,
                               'chosen': d.chosen} for d in self.decisions],
                'max_depth': self.max_depth,
                'line_map': list(self.line_map)}


@dataclass(frozen=True)
class Invocation:
    """One ``autoassemble`` invocation with its nesting depth."""
    label: str
    line: int
    depth: int


@dataclass(frozen=True)
class NestedPlan:
    """Resolved label graph: topological order and every invocation."""
    order: tuple
    invocations: tuple

    def report(self) -> dict:
        return {'schema': SCHEMA,
                'order': list(self.order),
                'invocations': [{'label': i.label, 'line': i.line,
                                 'depth': i.depth} for i in self.invocations]}


@dataclass(frozen=True)
class BlockAnalysis:
    """Combined block analysis with a deterministic error list."""
    block_plan: BlockPlan | None
    nested: NestedPlan | None
    errors: tuple

    @property
    def ok(self) -> bool:
        return not self.errors

    def report(self) -> dict:
        return {'schema': SCHEMA,
                'block_plan': self.block_plan.report()
                if self.block_plan is not None else None,
                'nested': self.nested.report() if self.nested is not None else None,
                'errors': [str(error) for error in self.errors]}


def _check_text(source: Any) -> str:
    if type(source) is not str:
        raise BlockStructureError('AA program source must be text')
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    # A trailing newline terminates the last line; it is not an extra line.
    if source.endswith('\n'):
        source = source[:-1]
    try:
        size = len(source.encode('utf-8'))
    except UnicodeError as exc:
        raise BlockStructureError('AA program source must be valid UTF-8 text') from exc
    if size > MAX_SOURCE_BYTES:
        raise BlockStructureError('AA program source exceeds its size bound')
    if len(source.split('\n')) > MAX_SOURCE_LINES:
        raise BlockStructureError('AA program source exceeds its line bound')
    return source


def _check_name(name: Any, context: str) -> str:
    if type(name) is not str or not _IDENTIFIER.fullmatch(name) \
            or len(name) > MAX_NAME_LENGTH:
        raise BlockStructureError(f'{context} names must be plain bounded identifiers')
    return name


def _normalize_defines(defines: Any) -> dict:
    if defines is None:
        defines = {}
    if type(defines) is not dict:
        raise BlockStructureError('defines must be a mapping')
    result = {}
    for name, value in defines.items():
        _check_name(name, 'defines')
        if type(value) is not int:
            raise BlockStructureError(f'define {name!r} must map to an exact integer')
        key = name.casefold()
        if key in result:
            raise BlockStructureError(f'define {name!r} is defined more than once')
        result[key] = value
    return result


def _normalize_registry(registry: Any) -> dict:
    if registry is None:
        registry = {}
    if type(registry) is not dict:
        raise BlockStructureError('label registry must be a mapping')
    result = {}
    for name, body in sorted(registry.items(), key=lambda item: str(item[0]).casefold()):
        _check_name(name, 'label registry')
        if type(body) is not str:
            raise BlockStructureError(f'label body for {name!r} must be text')
        body = body.replace('\r\n', '\n').replace('\r', '\n')
        if len(body.split('\n')) > MAX_SOURCE_LINES:
            raise BlockStructureError(f'label body for {name!r} exceeds its line bound')
        key = name.casefold()
        if key in result:
            raise BlockStructureError(f'label {name!r} is registered more than once')
        result[key] = {'name': name, 'lines': body.split('\n')}
    return result


def _operand_value(token: str, defines: dict, line: int | None) -> int:
    value = defines.get(token.casefold())
    if value is not None:
        return value
    try:
        if token.startswith(('0x', '0X', '$')):
            return int(token[1:], 16)
        return int(token, 10)
    except ValueError:
        raise BlockStructureError(f'undefined define {token!r}', line=line) from None


def _evaluate_condition(condition: str, defines: dict, line: int | None) -> bool:
    match = _CONDITION.fullmatch(condition.strip())
    if match is None:
        raise BlockStructureError(
            f'unsupported conditional expression: {condition.strip()!r}', line=line)
    left = _operand_value(match.group(1), defines, line)
    right = _operand_value(match.group(3), defines, line)
    return left == right if match.group(2) == '=' else left != right


def prune_conditionals(source: str, defines: dict | None = None) -> BlockPlan:
    """Prune conditional blocks deterministically; only chosen branches stay.

    ``defines`` maps define names to integer values.  Undefined names are
    refused (fail-closed, never treated as false); unbalanced blocks,
    duplicate ``{$else}`` markers and nesting beyond
    ``MAX_CONDITIONAL_DEPTH`` raise :class:`BlockStructureError` with the
    offending 1-based line.
    """
    source = _check_text(source)
    normalized = _normalize_defines(defines)
    lines = source.split('\n') if source else []
    output: list[str] = []
    line_map: list[int] = []
    decisions: list[Decision] = []
    stack: list[dict] = []
    max_depth = 0
    for index, line in enumerate(lines):
        number = index + 1
        stripped = line.strip()
        if _ELSE.fullmatch(stripped) is not None:
            if not stack:
                raise BlockStructureError('{$else} without a {$if}', line=number)
            frame = stack[-1]
            if frame['else_seen']:
                raise BlockStructureError('duplicate {$else} in one block', line=number)
            frame['else_seen'] = True
            frame['active'] = frame['chosen'] == 'else'
            continue
        if _ENDIF.fullmatch(stripped) is not None:
            if not stack:
                raise BlockStructureError('{$endif} without a {$if}', line=number)
            stack.pop()
            continue
        if _IF.fullmatch(stripped) is not None:
            match = _IF.fullmatch(stripped)
            condition = match.group(1)
            chosen = 'if' if _evaluate_condition(condition, normalized, number) else 'else'
            if len(stack) >= MAX_CONDITIONAL_DEPTH:
                raise BlockStructureError(
                    'conditional nesting exceeds its bound', line=number)
            stack.append({'line': number, 'chosen': chosen,
                          'else_seen': False, 'active': chosen == 'if'})
            decisions.append(Decision(number, condition, chosen))
            max_depth = max(max_depth, len(stack))
            continue
        if all(frame['active'] for frame in stack):
            output.append(line)
            line_map.append(number)
    if stack:
        raise BlockStructureError(
            f'unterminated {{$if}} opened at line {stack[-1]["line"]}',
            line=stack[-1]['line'])
    return BlockPlan(tuple(output), tuple(decisions), max_depth, tuple(line_map))


def resolve_nested_assembly(source: str, labels: dict | None = None) -> NestedPlan:
    """Resolve nested ``autoassemble`` invocations against label definitions.

    ``labels`` optionally maps external label names to their AA body text
    (table-level labels).  Internal definitions come from ``name:`` lines
    in the source.  Refusals: unknown labels, internal/external name
    collisions, duplicate definitions, duplicate invocations and cycles
    (with the cycle path).  The returned order is the deterministic
    topological order (callee before caller); ties break by definition
    line for internal labels and by name for external labels.
    """
    source = _check_text(source)
    external = _normalize_registry(labels)
    lines = source.split('\n') if source else []

    spans: dict[str, dict] = {}
    label_indices: list[int] = []
    for index, line in enumerate(lines):
        match = _LABEL_LINE.match(line)
        if match is None:
            continue
        name = match.group(1)
        key = name.casefold()
        if key in spans:
            raise BlockStructureError(
                f'label {name!r} is defined more than once', line=index + 1)
        spans[key] = {'name': name, 'line': index + 1, 'start': index + 1,
                      'end': len(lines)}
        label_indices.append(index)
    for position, index in enumerate(label_indices):
        end = label_indices[position + 1] if position + 1 < len(label_indices) else len(lines)
        for value in spans.values():
            if value['start'] == index + 1:
                value['end'] = end
                break
    if len(spans) + len(external) > MAX_LABELS:
        raise BlockStructureError('label count exceeds its bound')

    covered: set[int] = set()
    for value in spans.values():
        covered.update(range(value['start'] - 1, value['end']))

    for key, value in spans.items():
        if key in external:
            raise LabelCollisionError(
                f"label '{value['name']}' is defined in the program and the registry",
                label=value['name'], line=value['line'])

    known = {**{key: value['name'] for key, value in spans.items()},
             **{key: info['name'] for key, info in external.items()}}

    invocations: list[tuple] = []
    for index, line in enumerate(lines):
        number = index + 1
        if number - 1 in covered:
            continue
        match = _INVOCATION.match(line.strip())
        if match is None:
            continue
        invocations.append((match.group(1), number, 'top'))

    body_invocations: dict[str, list] = {}
    for key, value in spans.items():
        found = []
        for offset in range(value['start'] - 1, value['end']):
            match = _INVOCATION.match(lines[offset].strip())
            if match is not None:
                found.append((match.group(1), offset + 1))
        body_invocations[key] = found
    for key, info in external.items():
        found = []
        for offset, body_line in enumerate(info['lines']):
            match = _INVOCATION.match(body_line.strip())
            if match is not None:
                # line 0 = invocation inside an external registry body,
                # which has no line in the program source
                found.append((match.group(1), 0))
        body_invocations[key] = found

    if len(invocations) + sum(len(v) for v in body_invocations.values()) > MAX_INVOCATIONS:
        raise BlockStructureError('invocation count exceeds its bound')

    seen_lines: dict[str, list] = {}
    for label, number, _owner in invocations:
        seen_lines.setdefault(label.casefold(), []).append(number)
    for _key, found in body_invocations.items():
        for label, number in found:
            seen_lines.setdefault(label.casefold(), []).append(number)
    for key in sorted(seen_lines):
        if key not in known:
            source_lines = sorted(n for n in seen_lines[key] if n)
            raise UnknownLabelError(
                f"autoassembles unknown label '{key}'", label=key,
                line=source_lines[0] if source_lines else None)
        if len(seen_lines[key]) > 1:
            raise DuplicateInvocationError(
                f"label '{key}' is autoassembled more than once",
                label=key, lines=tuple(sorted(seen_lines[key])))

    adjacency: dict[str, list] = {key: [] for key in known}
    for key, found in body_invocations.items():
        adjacency[key] = [(label.casefold(), number) for label, number in found]

    def sort_key(item):
        key, _number = item
        if key in spans:
            return (0, spans[key]['line'], key)
        return (1, 0, key)

    for key in adjacency:
        adjacency[key].sort(key=sort_key)

    state: dict[str, int] = {}
    order: list[str] = []
    trail: list[str] = []

    def dfs(key):
        state[key] = 1
        trail.append(key)
        for target, _number in adjacency[key]:
            if state.get(target) == 1:
                start = trail.index(target)
                path = tuple(trail[start:]) + (target,)
                raise CycleError(
                    f'nested assembly cycle: {" -> ".join(path)}',
                    path=path, line=spans[key]['line'] if key in spans else None)
            if state.get(target, 0) == 0:
                dfs(target)
        trail.pop()
        state[key] = 2
        order.append(key)

    start_order = sorted(spans, key=lambda key: spans[key]['line']) + sorted(external)
    for key in start_order:
        if state.get(key, 0) == 0:
            dfs(key)

    # Every label has at most one invocation site (duplicates refused).
    site: dict[str, tuple] = {}
    for label, _number, _owner in invocations:
        site[label.casefold()] = ('top',)
    for owner_key, found in body_invocations.items():
        for label, _number in found:
            site[label.casefold()] = ('body', owner_key)

    invocation_depth: dict[str, int] = {}

    def depth_of(key):
        if key in invocation_depth:
            return invocation_depth[key]
        invocation_depth[key] = 0  # provisional; the graph is acyclic
        site_entry = site.get(key)
        if site_entry is not None:
            if site_entry[0] == 'top':
                invocation_depth[key] = 1
            else:
                invocation_depth[key] = depth_of(site_entry[1]) + 1
        return invocation_depth[key]

    for key in known:
        depth_of(key)

    ordered_invocations: list[Invocation] = []
    for label, number, _owner in invocations:
        ordered_invocations.append(Invocation(label, number, 1))
    for key in order:
        depth = invocation_depth.get(key, 0) + 1
        for label, number in body_invocations.get(key, []):
            ordered_invocations.append(Invocation(label, number, depth))

    ordered_labels = [known[key] for key in order]
    return NestedPlan(tuple(ordered_labels), tuple(ordered_invocations))


def analyze_blocks(source: str, defines: dict | None = None,
                   labels: dict | None = None) -> BlockAnalysis:
    """Combine pruning and nested-assembly resolution in one result.

    Conditionals are pruned first; the nested model runs on the pruned
    source, so constructs inside unchosen branches are dropped.  Nested
    errors are remapped to original source lines via the prune line map.
    Errors are reported deterministically: structural pruning errors first,
    then nested-assembly errors in encounter order.
    """
    errors: list[BlockError] = []
    block_plan: BlockPlan | None
    try:
        block_plan = prune_conditionals(source, defines)
    except BlockError as exc:
        errors.append(exc)
        block_plan = None
    nested: NestedPlan | None = None
    if block_plan is not None:
        pruned = '\n'.join(block_plan.lines)
        try:
            nested = resolve_nested_assembly(pruned, labels)
        except BlockError as exc:
            if exc.line is not None and 1 <= exc.line <= len(block_plan.line_map):
                exc.line = block_plan.line_map[exc.line - 1]
            lines = getattr(exc, 'lines', None)
            if lines:
                exc.lines = tuple(
                    block_plan.line_map[number - 1]
                    if 1 <= number <= len(block_plan.line_map) else number
                    for number in lines)
            errors.append(exc)
    return BlockAnalysis(block_plan, nested, tuple(errors))


def parse_label(line: str) -> str | None:
    """Return the name of a ``name:`` label definition line, else ``None``.

    Uses the exact whole-line rule pinned by :func:`resolve_nested_assembly`
    (identifier, optional trailing ``//`` comment); address lines such as
    ``1000:`` are not labels.
    """
    if type(line) is not str:
        raise BlockStructureError('label lines must be text')
    match = _LABEL_LINE.match(line)
    return match.group(1) if match is not None else None


def parse_invocation(line: str) -> str | None:
    """Return the label named by an ``autoassemble``/``autoasm`` line.

    Returns ``None`` when the line is not an invocation.  The spelling rule
    is identical to :func:`resolve_nested_assembly`: exact whole-line form
    with a double-quoted identifier, case-insensitive directive name,
    optional surrounding whitespace and optional trailing ``//`` comment.
    """
    if type(line) is not str:
        raise BlockStructureError('invocation lines must be text')
    match = _INVOCATION.match(line.strip())
    return match.group(1) if match is not None else None


def label_spans(source: str) -> tuple[tuple[str, int, int], ...]:
    """1-based ``(name, first_line, last_line)`` spans of label definitions.

    ``first_line`` is the label definition line; the body runs over lines
    ``first_line + 1 .. last_line`` (``last_line == first_line`` marks an
    empty body).  Spans follow the same rules as
    :func:`resolve_nested_assembly`: a body ends at the next label line or
    end of source.  Duplicate definitions (case-insensitive) are refused.
    """
    normalized = _check_text(source)
    lines = normalized.split('\n') if normalized else []
    starts: list[int] = []
    names: dict[int, str] = {}
    seen: set[str] = set()
    for index, line in enumerate(lines):
        match = _LABEL_LINE.match(line)
        if match is None:
            continue
        name = match.group(1)
        key = name.casefold()
        if key in seen:
            raise BlockStructureError(
                f'label {name!r} is defined more than once', line=index + 1)
        seen.add(key)
        starts.append(index)
        names[index] = name
    spans = []
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        spans.append((names[index], index + 1, end))
    return tuple(spans)


def extract_label_definitions(source: str) -> dict[str, str]:
    """Map each ``name:`` label definition to its body text.

    The body joins the lines after the definition up to the next label line
    or end of source with newlines (an empty body maps to ``""``).  Names
    are inserted in source order; duplicate definitions are refused, as in
    :func:`resolve_nested_assembly`.  The returned names keep the source
    spelling.
    """
    normalized = _check_text(source)
    lines = normalized.split('\n') if normalized else []
    result: dict[str, str] = {}
    for name, first, last in label_spans(normalized):
        result[name] = '\n'.join(lines[first:last])
    return result
