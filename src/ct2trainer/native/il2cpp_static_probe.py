"""Binary CLI adapter for the static IL2CPP parser (gate:2 evidence).

Exposes the bounded static IL2CPP analysis (WindowsPE + MetadataV29) through
a deterministic JSON report. This is the binary CLI/GUI adapter: the frozen
trainer binary (launcher.py) can invoke ``--il2cpp-static-pe`` to produce a
read-only metadata report without any live process access, game injection,
or target writes.

The report is bounded: it includes PE identity (SHA-256, bitness, image base,
section count) and a capped list of method identities from the metadata.
No game process is touched; this is purely a file-analysis tool.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .il2cpp_static import FormatError, MetadataV29, WindowsPE, MAX_PE_BYTES, MAX_METADATA_BYTES

SCHEMA = 'ct2trainer-il2cpp-static-probe/v1'
MAX_METHODS_IN_REPORT = 32


def run_probe(pe_path, metadata_path, report_path=None) -> dict:
    """Run static IL2CPP analysis on a PE file + metadata blob.

    Parameters
    ----------
    pe_path : str | Path
        Path to the PE executable (e.g. GameAssembly.dll).
    metadata_path : str | Path
        Path to the IL2CPP metadata blob (global-metadata.dat).
    report_path : str | Path | None
        If given, write the report JSON to this path (parent dirs created).

    Returns
    -------
    dict : the report structure (also written to report_path if given).

    Raises
    ------
    FormatError
        If either file is not a valid PE / metadata blob.
    ValueError
        If either file exceeds the size bound.
    OSError
        If a file cannot be read.
    """
    pe_bytes = Path(pe_path).read_bytes()
    if len(pe_bytes) > MAX_PE_BYTES:
        raise ValueError('PE file exceeds the %d byte bound' % MAX_PE_BYTES)
    meta_bytes = Path(metadata_path).read_bytes()
    if len(meta_bytes) > MAX_METADATA_BYTES:
        raise ValueError('Metadata file exceeds the %d byte bound' % MAX_METADATA_BYTES)

    pe = WindowsPE(pe_bytes)
    meta = MetadataV29(meta_bytes)

    methods = []
    for m in meta.methods[:MAX_METHODS_IN_REPORT]:
        methods.append({
            'image': m.image,
            'namespace': m.namespace,
            'class_name': m.class_name,
            'name': m.name,
            'token': '0x%08x' % m.token,
            'is_static': m.is_static,
            'parameter_count': len(m.parameters),
        })

    report = {
        'schema': SCHEMA,
        'pe': {
            'sha256': pe.sha256,
            'bitness': pe.bitness,
            'image_base': '0x%x' % pe.image_base,
            'section_count': len(pe.sections),
            'sections': [
                {'name': s.name.decode('latin-1'), 'rva': '0x%x' % s.rva,
                 'virtual_size': s.virtual_size}
                for s in pe.sections
            ],
        },
        'metadata': {
            'sha256': meta.sha256,
            'method_count': len(meta.methods),
        },
        'methods': methods,
        'process_access': False,
        'target_writes': False,
    }

    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
            encoding='utf-8')
    return report
