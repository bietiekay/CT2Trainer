"""executeCodeEx route: typed one-shot target calls from CT Lua scripts.

The pinned corpus (case-08, origin: Clair Obscure Expedition 33,
record "Add XP +?") invokes typed target calls as::

    local func = executeCodeEx(0,nil,Find,0,Data)
    executeCodeEx(0,nil,process,Data,func)

This module binds that Lua-facing call shape to the tested call-broker
contract layer (``src/ct2trainer/native/call_broker.py``): one immutable
entry per distinct function address and integer words only. The CE call
shape is mapped to exactly the two-integer-word c-variant wire operation
(``Operation.CDECL_ADD``) of the owned ABI
(``target_broker.protocol``); every other arity is a named contract
refusal, never a silent conversion. CE marshal tables (``{type=...,
value=...}`` arguments) and the remaining wire operations (wide, mixed,
boolean, string echo) stay outside this route until the live-target
execution gate defines the target's function signatures.

Fail-closed contract (named refusals, no silent recovery):

- ``TypedCallNotAttached``: the trainer is closed, the target is not
  attached, or the session's call-broker binding is absent/ended.
- ``TypedCallContractError``: the call shape or the typed wire contract
  refuses the arguments (wrong handle, non-nil reserved slot, function not
  a positive address, arity without a wire operation, non-integer words,
  out-of-range words).
- ``TypedCallBusy``: another one-shot call is still outstanding.
- ``TypedCallRefused``: the target refused the call or it ended in a
  non-DONE terminal state; the exact target error code is preserved.
- ``TypedCallUncertain``: lost acknowledgement, unknown target state, or a
  caller deadline while the call may still run; no retry is permitted.
"""
from __future__ import annotations

from .call_broker import (ArgValue, ArgumentContractError, CallBroker,
                          CallBrokerClosed, CallBrokerError,
                          CallBrokerUncertain, ReceiptStatus)
from .target_broker import CallContext
from .target_broker.protocol import Operation

#: One explicit caller deadline for the whole submit+wait round trip; the
#: foundation caps explicit contexts at 30 seconds.
TYPED_CALL_DEADLINE_SECONDS = 30.0

#: The CE call shape maps to exactly one owned wire operation: the
#: two-integer-word c-variant add. The remaining wire operations (wide,
#: mixed, boolean, string) have no CE call-shape mapping in this profile and
#: stay refused; they remain available on the broker itself.
_ARITY_OPERATIONS = {2: Operation.CDECL_ADD}


class TypedCallError(RuntimeError):
    """Named refusal of the typed target call route."""


class TypedCallNotAttached(TypedCallError):
    pass


class TypedCallContractError(TypedCallError):
    pass


class TypedCallBusy(TypedCallError):
    pass


class TypedCallRefused(TypedCallError):
    pass


class TypedCallUncertain(TypedCallError):
    pass


def execute_code_ex(broker: CallBroker, arguments: tuple | list) -> int | float:
    """Validate and route one executeCodeEx call through the call broker.

    ``arguments`` is the Lua argument list ``(handle, reserved, function,
    arg1, ..., argN)``: handle must be the default 0, reserved must be nil,
    function is the target entry address, and every remaining argument is
    one integer wire word. Returns the typed DONE result (integer or
    floating-point word); every refusal raises a named ``TypedCallError``
    with no target submission.
    """
    if not isinstance(broker, CallBroker):
        raise TypedCallNotAttached('The typed call broker binding is not available')
    if type(arguments) is not tuple and type(arguments) is not list:
        raise TypedCallContractError('Typed call arguments must be a list of words')
    arguments = tuple(arguments)
    if len(arguments) < 4:
        raise TypedCallContractError(
            'executeCodeEx requires handle, reserved slot, function and at least one word')
    handle, reserved, function = arguments[0], arguments[1], arguments[2]
    words = arguments[3:]
    if type(handle) is not int or handle != 0:
        raise TypedCallContractError('executeCodeEx admits only the default handle 0')
    if reserved is not None:
        raise TypedCallContractError('executeCodeEx reserved slot must stay nil')
    if type(function) is not int or function <= 0:
        raise TypedCallContractError('executeCodeEx function must be a positive target address')
    for word in words:
        if type(word) is not int:
            raise TypedCallContractError(
                'executeCodeEx arguments must be integer words; CE marshal tables '
                'are outside the owned wire ABI')
    operation = _ARITY_OPERATIONS.get(len(words))
    if operation is None:
        raise TypedCallContractError(
            'The typed wire contract admits exactly two integer argument words, '
            f'not {len(words)}')
    context = CallContext.seconds(TYPED_CALL_DEADLINE_SECONDS)
    try:
        # The entry name is derived from the bound address, so re-binding the
        # same function is idempotent and a different function never collides.
        entry_name = 'fn-' + format(function, 'x')
        broker.bind_entry(entry_name, function)
        call = broker.marshal(operation, tuple(ArgValue(word) for word in words),
                              entry_name=entry_name)
        receipt = broker.submit(call, context)
        receipt = broker.wait(receipt, CallContext.seconds(TYPED_CALL_DEADLINE_SECONDS))
    except CallBrokerClosed as exc:
        raise TypedCallNotAttached('The typed call broker session ended with the target') from exc
    except CallBrokerUncertain as exc:
        raise TypedCallUncertain(str(exc)) from exc
    except ArgumentContractError as exc:
        raise TypedCallContractError(str(exc)) from exc
    except CallBrokerError as exc:
        if 'one outstanding invocation' in str(exc):
            raise TypedCallBusy(str(exc)) from exc
        raise TypedCallContractError(str(exc)) from exc
    if receipt.status == ReceiptStatus.DONE:
        result = receipt.result
        if type(result) not in (int, float):
            raise TypedCallRefused(
                f'The typed call returned a non-word result {result!r} outside the wire contract')
        return result
    if receipt.status in (ReceiptStatus.REFUSED, ReceiptStatus.CANCELLED):
        raise TypedCallRefused(
            f'The target ended the typed call {receipt.status.name} (error {receipt.error})')
    raise TypedCallUncertain(
        f'The typed call ended {receipt.status.name}; its outcome is unproven, '
        'no retry is permitted')
