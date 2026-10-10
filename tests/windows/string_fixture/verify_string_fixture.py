"""Read-only Win32 observations of exact newly built owned String children.

The only mutations are the fixture's explicit stdin commands. This verifier
never calls WriteProcessMemory, changes target protection, injects or hooks.
"""
from __future__ import annotations

import argparse
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import queue
import struct
import subprocess
import threading


class MBI(c.Structure):
    _fields_ = [('BaseAddress', c.c_void_p), ('AllocationBase', c.c_void_p),
                ('AllocationProtect', w.DWORD), ('RegionSize', c.c_size_t),
                ('State', w.DWORD), ('Protect', w.DWORD), ('Type', w.DWORD)]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


kernel = c.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
kernel.OpenProcess.restype = w.HANDLE
kernel.CloseHandle.argtypes = [w.HANDLE]
kernel.CloseHandle.restype = w.BOOL
kernel.ReadProcessMemory.argtypes = [w.HANDLE, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
kernel.ReadProcessMemory.restype = w.BOOL
kernel.VirtualQueryEx.argtypes = [w.HANDLE, c.c_void_p, c.POINTER(MBI), c.c_size_t]
kernel.VirtualQueryEx.restype = c.c_size_t
kernel.GetProcessTimes.argtypes = [w.HANDLE] + [c.POINTER(w.FILETIME)] * 4
kernel.GetProcessTimes.restype = w.BOOL
kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
kernel.QueryFullProcessImageNameW.restype = w.BOOL


def read(handle, address: int, count: int) -> bytes:
    buffer = c.create_string_buffer(count)
    got = c.c_size_t()
    if not kernel.ReadProcessMemory(handle, address, buffer, count, c.byref(got)) or got.value != count:
        raise OSError(c.get_last_error(), 'Incomplete owned read')
    return buffer.raw


def region(handle, address: int) -> dict:
    value = MBI()
    if kernel.VirtualQueryEx(handle, address, c.byref(value), c.sizeof(value)) != c.sizeof(value):
        raise OSError(c.get_last_error(), 'Owned region query failed')
    return {'base': value.BaseAddress, 'bytes': value.RegionSize, 'state': value.State,
            'protection': value.Protect, 'type': value.Type}


def observe(exe: Path, architecture: str, output: Path) -> dict:
    observed = {'architecture': architecture, 'executable': str(exe), 'sha256': sha(exe),
                'command_line': [str(exe)], 'checks': [], 'lines': [], 'status': 'running'}
    handle = None
    child = None
    stderr = (output / f'{architecture}.stderr.log').open('w', encoding='utf-8')

    def check(name, condition):
        observed['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    try:
        child = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=stderr, text=True, encoding='ascii',
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        lines = queue.Queue()

        def output_reader():
            for line in child.stdout:
                lines.put(line)
            lines.put(None)

        reader = threading.Thread(target=output_reader, daemon=True)
        reader.start()

        def next_json():
            line = lines.get(timeout=7)
            if line is None or len(line) > 8192:
                raise AssertionError('Missing or oversized JSON line')
            observed['lines'].append(line.rstrip('\r\n'))
            return json.loads(line)

        metadata = next_json()
        observed['metadata'] = metadata
        bits, machine = (64, 0x8664) if architecture == 'x64' else (32, 0x14c)
        check('schema_arch_pid', metadata['schema'] == 'ct2trainer-owned-string-target/v1'
              and metadata['pid'] == child.pid and metadata['pointer_bits'] == bits
              and metadata['pe_machine'] == machine)
        handle = kernel.OpenProcess(0x10 | 0x400, False, child.pid)  # VM_READ + QUERY_INFORMATION only
        if not handle:
            raise OSError(c.get_last_error(), 'Could not open owned child for read-only proof')
        path_buffer = c.create_unicode_buffer(32768)
        path_size = w.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(handle, 0, path_buffer, c.byref(path_size)):
            raise OSError(c.get_last_error(), 'Owned image identity query failed')
        check('exact_child_image', Path(path_buffer.value).resolve() == exe.resolve())
        times = [w.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(c.byref(value) for value in times)):
            raise OSError(c.get_last_error(), 'Owned process creation query failed')
        observed['creation_filetime'] = times[0].dwLowDateTime | (times[0].dwHighDateTime << 32)
        image = exe.read_bytes()
        pe = struct.unpack_from('<I', image, 0x3c)[0]
        image_machine = struct.unpack_from('<H', image, pe + 4)[0]
        image_size = struct.unpack_from('<I', image, pe + 24 + 56)[0]
        remote_dos = read(handle, metadata['module_base'], 64)
        remote_pe = struct.unpack_from('<I', remote_dos, 0x3c)[0]
        remote_headers = read(handle, metadata['module_base'] + remote_pe, 88)
        check('own_pe_header_binding', image_machine == machine and image_size == metadata['module_bytes']
              and remote_dos[:2] == b'MZ' and remote_pe == pe and remote_headers[:4] == b'PE\0\0'
              and struct.unpack_from('<H', remote_headers, 4)[0] == machine
              and struct.unpack_from('<I', remote_headers, 24 + 56)[0] == image_size)

        def command(text):
            child.stdin.write(text + '\n')
            child.stdin.flush()
            return next_json()

        initial = command('status')
        observed['initial_status'] = initial
        check('initial_status_schema', initial['schema'] == 'ct2trainer-owned-string-status/v1'
              and initial['pid'] == child.pid and initial['sequence'] == 0)
        expected = {'ascii': b'old\0QRST',
                    'utf16': 'OLD🙂'.encode('utf-16-le') + b'\0\0' + bytes.fromhex('adde')
                             + b''.join(value.to_bytes(2, 'little') for value in range(0x3317, 0x3320)),
                    'fixed': b'FI\0XED!?'}
        check('distinct_buffer_addresses', len({item['address'] for item in metadata['buffers'].values()}) == 3)
        for index, name in enumerate(('ascii', 'utf16', 'fixed')):
            info, status = metadata['buffers'][name], initial['buffers'][name]
            check(name + '_rva_full_span', info['address'] == metadata['module_base'] + info['rva']
                  and info['full_address'] == metadata['module_base'] + info['full_rva']
                  and info['before_address'] == info['address'] - 8
                  and info['after_address'] == info['address'] + info['read_bytes']
                  and info['before_address'] == metadata['module_base'] + info['before_rva']
                  and info['after_address'] == metadata['module_base'] + info['after_rva']
                  and info['full_bytes'] == info['read_bytes'] + 16
                  and info['full_rva'] + info['full_bytes'] <= metadata['module_bytes'])
            raw = read(handle, info['full_address'], info['full_bytes'])
            before = bytes(range(0xa0 + index * 16, 0xa8 + index * 16))
            after = bytes(range(0xa8 + index * 16, 0xb0 + index * 16))
            check(name + '_raw_guarded_initial', raw == before + expected[name] + after
                  and bytes.fromhex(status['before']) == before
                  and bytes.fromhex(status['after']) == after
                  and bytes.fromhex(status['value']) == expected[name])
            queried = region(handle, info['address'])
            check(name + '_committed_nonexec_rw', queried == status['region']
                  and queried['state'] == 0x1000 and queried['protection'] == 4 and queried['type'] == 0x1000000
                  and queried['base'] <= info['full_address']
                  and info['full_address'] + info['full_bytes'] <= queried['base'] + queried['bytes'])
        check('utf16_visible_pair_and_invalid_tail', expected['utf16'][:10].decode('utf-16-le') == 'OLD🙂'
              and expected['utf16'][12:14] == bytes.fromhex('adde'))
        for name, protection, contents in [('readonly', 2, b'RSTUVWXY'), ('executable', 0x40, b'EFGHIJKL')]:
            info = metadata[name]
            queried = region(handle, info['address'])
            pointer = read(handle, info['pointer_address'], bits // 8)
            check(name + '_wrong_region_and_pointer_binding', queried == initial[name]['region']
                  and queried['state'] == 0x1000 and queried['protection'] == protection
                  and queried['type'] == 0x20000
                  and info['pointer_address'] == metadata['module_base'] + info['pointer_rva']
                  and int.from_bytes(pointer, 'little') == info['address']
                  and read(handle, info['address'], 8) == contents)
        prefix = command('mutate-prefix')
        check('prefix_command_sequence', prefix['sequence'] == 1)
        for name in ('ascii', 'utf16', 'fixed'):
            raw = bytes.fromhex(prefix['buffers'][name]['value'])
            unit = metadata['buffers'][name]['unit_bytes']
            check(name + '_precise_prefix_command', raw[:unit] == b'M' + b'\0' * (unit - 1)
                  and raw[unit:] == expected[name][unit:]
                  and prefix['buffers'][name]['before'] == initial['buffers'][name]['before']
                  and prefix['buffers'][name]['after'] == initial['buffers'][name]['after']
                  and read(handle, metadata['buffers'][name]['address'], len(raw)) == raw)
        tail = command('mutate-tail')
        check('tail_command_sequence', tail['sequence'] == 2)
        for name in ('ascii', 'utf16', 'fixed'):
            previous, current = (bytes.fromhex(item['buffers'][name]['value']) for item in (prefix, tail))
            unit = metadata['buffers'][name]['unit_bytes']
            check(name + '_precise_tail_command', current[:-unit] == previous[:-unit]
                  and int.from_bytes(current[-unit:], 'little') == (int.from_bytes(previous[-unit:], 'little') ^ 1)
                  and tail['buffers'][name]['before'] == initial['buffers'][name]['before']
                  and tail['buffers'][name]['after'] == initial['buffers'][name]['after']
                  and read(handle, metadata['buffers'][name]['address'], len(current)) == current)
        check('negative_regions_not_mutated', tail['readonly'] == initial['readonly']
              and tail['executable'] == initial['executable'])
        steady = command('status')
        check('no_automatic_writer', steady == tail)
        child.stdin.write('quit\n')
        child.stdin.flush()
        child.wait(timeout=7)
        check('normal_quit', child.returncode == 0)
        check('binary_unchanged', sha(exe) == observed['sha256'])
        observed['status'] = 'passed'
        observed['exit_code'] = child.returncode
        return observed
    except BaseException as error:
        observed['status'] = 'failed'
        observed['error'] = repr(error)
        raise
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=7)
        if handle:
            kernel.CloseHandle(handle)
        stderr.close()
        (output / f'{architecture}.observed.json').write_text(json.dumps(observed, indent=2), encoding='utf-8')
        (output / f'{architecture}.stdout.jsonl').write_text('\n'.join(observed['lines']) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    build_report = args.build / 'verification.json'
    build = json.loads(build_report.read_text(encoding='utf-8-sig'))
    results = []
    for item in build['results']:
        exe = Path(item['executable'])
        if sha(exe) != item['sha256']:
            raise AssertionError('Built executable changed before proof')
        results.append(observe(exe, item['architecture'], args.output))
    if any(sha(Path(item['path'])) != item['sha256'] for item in build['sources']):
        raise AssertionError('Owned fixture source changed during proof')
    report = {'schema': 'ct2trainer-owned-string-verification/v1', 'status': 'passed',
              'build_report': str(build_report.resolve()), 'build_report_sha256': sha(build_report),
              'verifier_sha256': sha(Path(__file__)), 'results': results,
              'checks_per_architecture': [len(item['checks']) for item in results],
              'scope': 'Owned local child protocol and read-only Win32 observations. No trainer mutation admission, held-event proof, injection, hooks, game or original CT execution.'}
    (args.output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'checks_per_architecture': report['checks_per_architecture'],
                      'report': str((args.output / 'verification.json').resolve())}))


if __name__ == '__main__':
    main()
