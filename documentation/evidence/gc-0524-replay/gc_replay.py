"""Deterministic target-traffic replay of the Great Circle wish set.

Field case 2026-11-24 (The Great Circle / "Indiana Jones and the Great
Circle" table, sha256 4e0dc0b54a5d96526d680042fe323bcfc4421327559c201f0b688279fff18c2b):
every trainer build after 0.41 crashed the game ~60-77 s after attach
while the trainer sat read-only-idle; the game build did not change and
worked with 0.41.  The replay drives one tree's TrainerEngine (0.41
worktree vs the 0.52.3 code baseline) with the same GC table, the same
11 wishes, and an identical synthetic module image (field RVAs from the
0.52.2 session log; the two A/B-variant patterns are deliberately absent
-> ScanMiss, exactly as in the field).  Every target memory call is
recorded; the two runs are then diffed by gc_replay_diff.py.

The table file is local-only input (an original game table) and is
never distributed; pass its path as the second argument.  The module
base is a synthetic constant - the field base (0x7ff70b2a0000) is
irrelevant to the diff because the RVAs are exact and identical in
both runs.

Usage:
    python gc_replay.py <tree_root> <table.ct> <out.json>

Requires the pinned NASM in the environment (CT2TRAINER_NASM) for the
AA assembly step.
"""
import sys
import json
import re
import tempfile
import hashlib
import threading
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

TREE = Path(sys.argv[1]).resolve()
TABLE = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(TREE / "src"))

import ct2trainer  # noqa: E402  (verify which tree loaded)
from ct2trainer.native import memory as _memmod  # noqa: E402
from ct2trainer.native.compiler import compile_table  # noqa: E402
from ct2trainer.native.engine import TrainerEngine  # noqa: E402
from ct2trainer.native.hooks import QuiescenceProof  # noqa: E402
from ct2trainer.native.memory import (  # noqa: E402
    _compile_pattern, _pattern_anchor, _candidate_offsets)

ScanMiss = getattr(_memmod, "ScanMiss", OSError)

PROCESS_NAME = "TheGreatCircle.exe"
MODULE_BASE = 0x140000000
MODULE_SIZE = 122609664          # field module size (0.52.2 log)
# Just above the module end + 16 KiB margin: still within the +/-2 GiB
# relative-jump range of every module patch site, and never inside the
# simulated module image.
MODULE_END = MODULE_BASE + MODULE_SIZE
ALLOC_BASE = MODULE_END + 0x10000
ALLOC_BLOCK = 0x10000           # 64 KiB deterministic stride
FILLER = 0xEE
WISHES = [1, 6, 7, 12, 13, 16, 19, 20, 21, 24, 31]

# Field session 0.52.2 (2026-11-24): symbol -> (rva, pattern).
# aobhealth2 / aobammo2 are deliberately NOT placed -> ScanMiss, as in field.
PLACEMENTS = {
    "aobhealth": (0x13FFA46,
                  "F3 0F 10 1C 82 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 76 ?? 0F 2F 56 54 73"),
    "aobstamina": (0x1D1EEBA,
                   "41 03 40 0C 66 0F 6E C0 0F 5B C0 F3 ?? 0F 58 ?? ?? 0F 28 ?? "
                   "F3 0F 10 ?? ?? ?? 00 00 0F 2E ?? 0F 84 ?? ?? 00 00"),
    "aoboxygen": (0x15120CD,
                  "F3 ?? 0F 10 ?? 0F 2F ?? 76 06 F3 0F 5C ?? EB ?? ?? 0F 28 ?? "
                  "F3 ?? 0F 11 ?? ?? C6"),
    "aobammo": (0x1C7947F,
                "8B 57 20 48 8B CB E8 ?? ?? ?? ?? ?? 8B ?? ?? ?? ?? 8B ?? ?? ?? 00 00 E8"),
    "aobreload_1": (0x1461D19, "8B 50 14 03 D6 79 ?? ?? ?? EB ?? 3B ?? ?? 0F 4F"),
    "aobreload_2": (0x14672E8,
                    "0F 84 ?? ?? 00 00 ?? 8B ?? ?? 80 ?? ?? 00 74 ?? ?? 8B ?? ?? ?? "
                    "00 00 80 ?? ?? 00 75 ?? 80"),
    "aobfood": (0x1E0307F, "4A 89 ?? ?? ?? ?? 8B ?? ?? 3B ?? 7C ?? FF C8 ?? 89 ?? 20"),
    "aobuseitem": (0x1A60123,
                   "FF CB ?? ?? ?? ?? ?? ?? ?? ?? ?? 7D ?? 8B ?? ?? 8D ?? 18 E8"),
    "aobdurability": (0x1C79584, "84 C0 74 ?? F3 0F 10 ?? ?? EB ?? 0F 57 ?? F3 0F 58 42 0C"),
    "aobstealthmode": (0x11F0CF3,
                       "0F 87 ?? ?? 00 00 F3 0F 10 ?? ?? F3 0F 10 ?? ?? 0F ?? ?? "
                       "0F ?? ?? 0F ?? ?? 72 ?? F3 0F 58"),
    "aobcurrencymultplier": (0x1A60BDB,
                             "41 8B F0 48 8B DA 45 85 C0 0F 88 ?? ?? 00 00 ?? 85 ?? "
                             "0F 84 ?? ?? 00 00"),
}


def _json_default(obj):
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    if isinstance(obj, tuple):
        return list(obj)
    return str(obj)


class ReplayMemoryError(OSError):
    """Stand-in for the tree's ProcessMemoryError (replay-local)."""


def _scan(data, pattern):
    """All absolute offsets in *data* matching *pattern* (tree semantics)."""
    matcher, pattern_size = _compile_pattern(pattern)
    anchor, anchor_offset = _pattern_anchor(pattern)
    out = []
    for candidate in _candidate_offsets(data, anchor, anchor_offset):
        if candidate < 0 or candidate + pattern_size > len(data):
            continue
        if matcher.match(data, candidate):
            out.append(candidate)
    return out


def build_module_image():
    module = bytearray([FILLER] * MODULE_SIZE)
    for symbol, (rva, pattern) in sorted(PLACEMENTS.items()):
        matcher, pattern_size = _compile_pattern(pattern)
        anchor, anchor_offset = _pattern_anchor(pattern)
        # per-byte token list
        byte_tokens = re.findall(r"[0-9A-Fa-f]{2}|\?\?", pattern)
        cursor = 0
        for token in byte_tokens:
            if token == "??":
                cursor += 1
            else:
                module[rva + cursor] = int(token, 16)
                cursor += 1
        # verify it now matches exactly at rva and nowhere else
        matches = _scan(bytes(module), pattern)
        if rva not in matches or len(matches) != 1:
            raise AssertionError(
                f"pattern for {symbol} matches {len(matches)}x, expected exactly "
                f"1 at rva {rva:#x}: {sorted(hex(m) for m in matches)[:8]}")
    return module


class RecordingMemory:
    def __init__(self, name, module):
        self.name = name
        self.pid = 424242
        self.creation_time = 134399935579190145
        self.pointer_size = 8
        self.alive = True
        self.closed = False
        self.module_base = MODULE_BASE
        self.module_size = MODULE_SIZE
        self.module_image = module
        self.allocs = {}          # address -> bytearray
        self._protect = {}        # address -> protect_allocation request
        self._next_alloc = ALLOC_BASE
        self._lock = threading.RLock()
        self.phase = "init"
        self.log = []
        self._seq = 0
        self.scan_counts = 0
        self.read_counts = 0
        self.last_scan_diagnostics = None

    @property
    def identity(self):
        return (self.pid, self.creation_time)

    def _record(self, op, **kw):
        self._seq += 1
        self.log.append({"seq": self._seq, "phase": self.phase, "op": op, **kw})

    def is_alive(self):
        return self.alive

    def close(self):
        self.closed = True

    def module(self, name):
        if name.casefold() != PROCESS_NAME.casefold():
            raise ReplayMemoryError("Unknown module: " + name)
        return (MODULE_BASE, MODULE_SIZE)

    def _alloc_for(self, address):
        for addr, buf in self.allocs.items():
            if addr <= address < addr + len(buf):
                return addr
        return None

    def _locate(self, address):
        base = address - MODULE_BASE
        if 0 <= base < MODULE_SIZE:
            return "module", base
        alloc_addr = self._alloc_for(address)
        if alloc_addr is not None:
            return "alloc", address - alloc_addr
        raise ReplayMemoryError("address not committed: %x" % address)

    def read(self, address, size):
        self.read_counts += 1
        if size <= 0 or address + size <= address:
            raise ReplayMemoryError("invalid read range")
        region, off = self._locate(address)
        if region == "module":
            if off + size > MODULE_SIZE:
                raise ReplayMemoryError("read out of module")
            return bytes(self.module_image[off:off + size])
        buf = self.allocs[self._alloc_for(address)]
        if off + size > len(buf):
            raise ReplayMemoryError("read out of allocation")
        return bytes(buf[off:off + size])

    def write(self, address, data):
        data = bytes(data)
        region, off = self._locate(address)
        if region == "module":
            if off + len(data) > MODULE_SIZE:
                raise ReplayMemoryError("write out of module")
            self.module_image[off:off + len(data)] = data
        else:
            buf = self.allocs[self._alloc_for(address)]
            if off + len(data) > len(buf):
                raise ReplayMemoryError("write out of allocation")
            buf[off:off + len(data)] = data
        self._record("write", addr=hex(address), size=len(data),
                     data=data.hex(), region=region)

    def _scan_range(self, data, base, pattern):
        return [base + c for c in _scan(data, pattern)]

    def scan_module(self, name, pattern):
        self.module(name)
        self.scan_counts += 1
        matches = self._scan_range(bytes(self.module_image), MODULE_BASE, pattern)
        if not matches:
            raise ScanMiss("The module byte pattern was not found in readable committed memory.")
        self.last_scan_diagnostics = {
            "match_count": len(matches),
            "match_addresses": matches,
            "module": name,
            "module_base": MODULE_BASE,
        }
        self._record("scan_module", pattern=pattern, result=hex(matches[0]),
                     match_count=len(matches))
        return matches[0]

    def scan_region(self, start, end, pattern, *, checkpoint=None):
        matches = []
        base = start - MODULE_BASE
        if 0 <= base and end <= MODULE_BASE + MODULE_SIZE:
            data = bytes(self.module_image[base:end - MODULE_BASE])
            matches = self._scan_range(data, start, pattern)
        for alloc_addr, buf in self.allocs.items():
            if alloc_addr >= start and alloc_addr + len(buf) <= end:
                matches.extend(self._scan_range(bytes(buf), alloc_addr, pattern))
        self._record("scan_region", start=hex(start), end=hex(end),
                     pattern=pattern, match_count=len(matches),
                     result=hex(matches[0]) if matches else None)
        if not matches:
            raise ScanMiss("The module byte pattern was not found in readable committed memory.")
        return min(matches)

    def scan_matches(self, pattern, start=0, end=None, protection="",
                     alignment_type=0, alignment_parameter=None,
                     max_results=65536, *, checkpoint=None):
        matches = []
        for alloc_addr, buf in self.allocs.items():
            if start <= alloc_addr and (end is None or alloc_addr < end):
                matches.extend(self._scan_range(bytes(buf), alloc_addr, pattern))
        base = start - MODULE_BASE
        if 0 <= base and (end is None or MODULE_BASE + MODULE_SIZE < end):
            end_abs = min(MODULE_BASE + MODULE_SIZE, end) if end else MODULE_BASE + MODULE_SIZE
            data = bytes(self.module_image[base:end_abs - MODULE_BASE])
            matches.extend(self._scan_range(data, start, pattern))
        return sorted(matches)[:max_results]

    def resolve(self, expression, symbols=None):
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError("Invalid address expression.")
        expression = expression.strip()
        parsed = re.fullmatch(
            r'("[^"\r\n]+"|[A-Za-z_][A-Za-z0-9_.$]*|(?:0[xX]|\$)?[0-9A-Fa-f]+)'
            r"((?:\s*[+-]\s*(?:0[xX]|\$)?[0-9A-Fa-f]+)*)", expression)
        if not parsed:
            raise ValueError("Unsupported address expression: " + expression)
        atom, suffix = parsed.groups()
        quoted = atom.startswith('"')
        atom = atom[1:-1] if quoted else atom
        address = None
        if not quoted and symbols is not None:
            symbol_matches = [value for key, value in symbols.items()
                              if key.casefold() == atom.casefold()]
            if len(symbol_matches) > 1:
                raise ValueError("Ambiguous symbol name differing only by case.")
            if symbol_matches:
                address = symbol_matches[0]
        if address is None and not quoted \
                and re.fullmatch(r"(?:0[xX]|\$)?[0-9A-Fa-f]+", atom):
            address = int(atom.removeprefix("$"), 16)
        if address is None:
            if not quoted:
                raise ReplayMemoryError("Unknown symbol: " + atom)
            address = MODULE_BASE
        for sign, value in re.findall(r"([+-])\s*((?:0[xX]|\$)?[0-9A-Fa-f]+)", suffix):
            delta = int(value.removeprefix("$"), 16)
            address += delta if sign == "+" else -delta
        self._range(address, 1)
        self._record("resolve", expression=expression, result=hex(address))
        return address

    def resolve_pointer(self, address, offsets, symbols=None):
        current = self.resolve(address, symbols) if isinstance(address, str) else int(address)
        for offset in reversed(list(offsets)):
            pointer = int.from_bytes(self.read(current, self.pointer_size), "little")
            if pointer == 0:
                raise ReplayMemoryError("The pointer chain contains a null pointer.")
            current = pointer + offset
        return current

    def resolve_export(self, module_name, export_name, *, pointer_size=None):
        self._record("resolve_export", module=module_name, export=export_name)
        raise ReplayMemoryError("resolve_export unexpected in replay: "
                                + module_name + "." + export_name)

    def _range(self, address, size, *, limit=67108864):
        if size <= 0 or size > limit:
            raise ReplayMemoryError("invalid range size")
        self._locate(address)

    def allocate(self, size, near=None, max_distance=2147418112):
        addr = self._next_alloc
        self._next_alloc += ALLOC_BLOCK
        self.allocs[addr] = bytearray(size)
        self._record("allocate", size=size,
                     near=hex(near) if near is not None else None,
                     result=hex(addr))
        return addr

    def allocation_size(self, address):
        alloc_addr = self._alloc_for(address)
        if alloc_addr is None:
            raise ReplayMemoryError("not an owned allocation: %x" % address)
        return len(self.allocs[alloc_addr])

    def is_executable(self, address, size):
        self._locate(address)
        return True

    def protect_allocation(self, address, executable=True, writable=False):
        self._protect[address] = (executable, writable)
        self._record("protect_allocation", addr=hex(address),
                     executable=executable, writable=writable)

    def _query(self, address):
        """VirtualQueryEx stand-in for committed regions (hook guard path)."""
        alloc_addr = self._alloc_for(address)
        if alloc_addr is not None:
            size = len(self.allocs[alloc_addr])
            executable, writable = self._protect.get(
                alloc_addr, (True, False))
            protect = (0x40 if writable else 0x20) if executable else 0x04
            return SimpleNamespace(
                BaseAddress=alloc_addr, AllocationBase=alloc_addr,
                RegionSize=size, State=0x1000, Protect=protect)
        base = address - MODULE_BASE
        if 0 <= base < MODULE_SIZE:
            return SimpleNamespace(
                BaseAddress=MODULE_BASE, AllocationBase=MODULE_BASE,
                RegionSize=MODULE_SIZE, State=0x1000, Protect=0x20)
        raise ReplayMemoryError("no committed region at %x" % address)

    def release(self, address):
        self._record("release", addr=hex(address))


class FakeCoordinator:
    """Test-style coordinator: yields an always-valid proof, records holds."""

    def __init__(self):
        self.holds = []

    @contextmanager
    def hold(self, memory, ranges):
        self.holds.append(("hold", tuple(ranges)))
        yield QuiescenceProof(memory.identity, tuple(ranges),
                              "replay-safe-point", lambda: True)

    @contextmanager
    def hold_data(self, memory, ranges):
        self.holds.append(("hold_data", tuple(ranges)))
        yield QuiescenceProof(memory.identity, tuple(ranges),
                              "replay-data-safe-point", lambda: True)

    @contextmanager
    def hold_entries(self, memory, code, literal_windows=(),
                     exclusion_ranges=()):
        # windows are (address, original, patched, active); proof ranges are
        # (address, length) of the patched bytes, plus the literal data ranges.
        ranges = tuple((w[0], len(w[2])) for w in code) + tuple(exclusion_ranges)
        self.holds.append(("hold_entries", ranges))
        yield QuiescenceProof(memory.identity, ranges,
                              "replay-entries-safe-point", lambda: True)


def main():
    module = build_module_image()
    plan = compile_table(TABLE, PROCESS_NAME)
    mem = RecordingMemory(PROCESS_NAME, module)
    coord = FakeCoordinator()
    out = {"tree": str(TREE), "ct2trainer_file": ct2trainer.__file__,
           "wishes": {}, "final": {}, "scans": [], "resolves": [],
           "writes": [], "allocs": [], "protects": [], "releases": [],
           "module_diff": [], "alloc_contents": {},
           "scan_counts": 0, "read_counts": 0, "holds": []}
    initial_module = bytes(module)

    with tempfile.TemporaryDirectory() as td:
        engine = TrainerEngine(
            plan,
            Path(td) / "state",
            lambda name: mem,
            Path(td) / "shared",
            hook_coordinator=coord,
        )
        mem.phase = "attach"
        engine.poll()
        out["connected"] = bool(getattr(engine, "connected", None))
        out["status_attach"] = engine.status
        if not out["connected"]:
            out["error"] = "attach failed: " + str(engine.status)
            OUT.write_text(json.dumps(out, indent=1, default=_json_default),
                           encoding="utf-8")
            return
        for w in WISHES:
            entry = plan["entries"][w] if w < len(plan["entries"]) else None
            label = entry.get("label", "?") if entry else "?"
            mem.phase = "restore"
            try:
                ok = engine.toggle(w, True)
                out["wishes"][w] = {"label": label,
                                    "result": "enabled" if ok else "refused"}
            except Exception as exc:
                import traceback
                out["wishes"][w] = {"label": label,
                                    "result": "failed: " + str(exc),
                                    "trace": traceback.format_exc()}
        mem.phase = "steady"
        applied_module = bytes(mem.module_image)
        for _ in range(5):
            try:
                engine.poll()
            except Exception as exc:
                out["steady_error"] = str(exc)
                break
        mem.phase = "close"
        try:
            engine.close()
            out["close"] = "ok"
        except Exception as exc:
            out["close"] = "failed: " + str(exc)
        out["final"] = {
            "applied": sorted(engine.applied.keys()),
            "blocked": bool(engine.blocked),
            "status": engine.status,
        }

    for item in mem.log:
        if item["op"] in ("scan_module", "scan_region"):
            out["scans"].append(item)
        elif item["op"] == "resolve":
            out["resolves"].append(item)
        elif item["op"] == "write":
            out["writes"].append(item)
        elif item["op"] == "allocate":
            out["allocs"].append(item)
        elif item["op"] == "protect_allocation":
            out["protects"].append(item)
        elif item["op"] == "release":
            out["releases"].append(item)
    out["scan_counts"] = mem.scan_counts
    out["read_counts"] = mem.read_counts
    out["holds"] = coord.holds

    # module diff: while-applied (initial vs applied snapshot) and final
    # (initial vs post-close; expected empty = clean restore).
    out["module_diff"] = []
    out["module_diff_applied"] = []
    for name, snapshot in (("module_diff", bytes(mem.module_image)),
                           ("module_diff_applied", applied_module)):
        i = 0
        while i < MODULE_SIZE:
            if snapshot[i] != initial_module[i]:
                j = i
                while j < MODULE_SIZE and snapshot[j] != initial_module[j]:
                    j += 1
                out[name].append({
                    "rva": hex(i),
                    "addr": hex(MODULE_BASE + i),
                    "before": initial_module[i:j].hex(),
                    "after": snapshot[i:j].hex(),
                })
                i = j
            else:
                i += 1
    for addr, buf in mem.allocs.items():
        out["alloc_contents"][hex(addr)] = bytes(buf).hex()

    plan_norm = json.dumps(
        {k: v for k, v in plan.items()
         if k not in ("trainer_id", "title", "debug_log", "generated_at",
                      "generator_version")},
        sort_keys=True, ensure_ascii=False)
    out["plan_canonical_sha256"] = hashlib.sha256(
        plan_norm.encode("utf-8")).hexdigest()
    OUT.write_text(json.dumps(out, indent=1, default=_json_default),
                   encoding="utf-8")
    print("replay done:", OUT)
    print("connected:", out.get("connected"))
    print("wishes:", json.dumps({k: v.get("result") for k, v in out["wishes"].items()}))
    print("writes:", len(out["writes"]), "allocs:", len(out["allocs"]),
          "module_diff ranges:", len(out["module_diff"]),
          "alloc_regions:", len(out["alloc_contents"]))
    print("final:", out["final"])


if __name__ == "__main__":
    main()
