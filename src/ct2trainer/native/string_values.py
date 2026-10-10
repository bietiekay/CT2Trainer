"""Bounded CT string codecs, independently implemented from public API/metadata.

This draft does not install a runtime/engine profile. A terminated value's write
span is only its actual encoded units plus its terminator. The declared Length
is a read/input bound, never permission to zero an entire presumed allocation.
The runtime must own fresh identity/address/range/protection, held publication,
overlap checks, raw inverse/readback and freeze/cancel before using this result.

CodePage: an absent or default (0) CodePage keeps the record's default codec
(ASCII for byte strings, UTF-16LE for wide strings; CE marks every default
string record with CodePage="0", and the 0.8 owned-fixture pins stay
byte-stable under that mapping). An explicit non-default CodePage must be an
exact integer of the pinned contract table in
``ct2trainer.native.codepage_contract`` (1250-1257, 65001); the codec is
then resolved from that table, unit size is one byte, and wide strings
refuse the combination fail-closed. Every other value is refused.

Public contract: MemoryRecord.String.Size/Unicode/Codepage and readString.
https://wiki.cheatengine.org/index.php?title=Lua:Class:MemoryRecord
https://wiki.cheatengine.org/index.php?title=Lua:readString
"""
from dataclasses import dataclass
import json
import re

from .codepage_contract import UnsupportedCodePage, codec_for, supported_codepages

MAX_BYTES=65536
SCHEMA='ct2trainer-string-profile/v1'

class StringValueError(ValueError):pass

def _flag(properties,key,default=False):
    value=properties.get(key,default)
    if type(value) is bool:return value
    if type(value) is int and value in (0,1):return bool(value)
    if type(value) is str and len(value)<=8 and value.strip(' \t\r\n') in ('0','1'):
        return value.strip(' \t\r\n')=='1'
    raise StringValueError(key+' must be an explicit Boolean flag')

def _codepage(properties):
    """Resolve the optional CT CodePage attribute against the pinned contract.

    Absent, False or 0 normalizes to False: the record keeps its default
    codec (ASCII for byte strings, UTF-16LE for wide strings). CE marks
    every default string record with CodePage="0", so this mapping keeps the
    0.8 owned-fixture pins byte-stable. An explicit non-default value must
    be an exact integer of the pinned contract table; every other value is
    refused fail-closed.
    """
    value=properties.get('CodePage',False)
    if value is None or value is False:return False
    if type(value) is str:
        text=value.strip(' \t\r\n')
        if len(text)<=8 and text.isdigit():value=int(text)
        else:raise StringValueError('Codepage must be an exact integer from the pinned CodePage contract')
    if type(value) is not int:
        raise StringValueError('Codepage must be an exact integer from the pinned CodePage contract')
    if value==0:return False
    try:
        codec_for(value)
    except UnsupportedCodePage as error:
        raise StringValueError(
            'Codepage %d is not in the pinned CodePage contract (%s); refused fail-closed'%(
                value,'/'.join(str(codepage) for codepage in supported_codepages()))) from error
    return value

def prepare(properties):
    if type(properties) is not dict:raise StringValueError('String metadata must be an object')
    value=properties.get('Length')
    if type(value) is str and len(value)<=10 and re.fullmatch('[0-9]+',value.strip()):value=int(value)
    if type(value) is not int or not 0<=value<=MAX_BYTES:raise StringValueError('Length outside bounded explicit units')
    unicode=_flag(properties,'Unicode')
    codepage=_codepage(properties)
    terminated=_flag(properties,'ZeroTerminate',True)
    if codepage and unicode:
        raise StringValueError('Codepage cannot be combined with Unicode; wide strings use UTF-16')
    if codepage:
        unit=1
        encoding=codec_for(codepage)
    else:
        unit=2 if unicode else 1
        encoding='utf-16-le' if unicode else 'ascii'
    size=value*unit
    if size>MAX_BYTES:raise StringValueError('String byte bound exceeded')
    return {'schema':SCHEMA,'kind':'string','properties':{'Length':value,'Unicode':unicode,
        'CodePage':codepage,'ZeroTerminate':terminated},'size':size,'unit_bytes':unit,
        'encoding':encoding,'actionable':size>0,
        'display':'literal_text','write_span':'actual_literal_and_terminator' if terminated else 'exact_fixed_units'}

def validate(profile):
    if type(profile) is not dict or profile.get('schema')!=SCHEMA:raise StringValueError('Invalid string profile')
    expected=prepare(profile.get('properties'))
    try:
        if json.dumps(profile,sort_keys=True,allow_nan=False)!=json.dumps(expected,sort_keys=True,allow_nan=False):
            raise StringValueError('Forged or extra string metadata')
    except (TypeError,ValueError,OverflowError,RecursionError) as error:raise StringValueError('Invalid string metadata') from error

def _active(profile):
    validate(profile)
    if not profile['actionable']:raise StringValueError('Zero Length is nonactionable navigation')

@dataclass(frozen=True)
class LiteralWrite:
    replacement:bytes
    read_bound:int
    unit_bytes:int

def parse(profile,text):
    _active(profile)
    if type(text) is not str or len(text)>MAX_BYTES:raise StringValueError('String literal outside transport bounds')
    terminated=profile['properties']['ZeroTerminate']
    if terminated and '\0' in text:raise StringValueError('Embedded terminator is ambiguous in a terminated literal')
    try:raw=text.encode(profile['encoding'],errors='strict')
    except UnicodeError as error:raise StringValueError('Literal cannot be encoded by this profile') from error
    if terminated:
        raw+=bytes(profile['unit_bytes'])
        if len(raw)>profile['size']:raise StringValueError('Literal plus terminator exceeds Length')
    elif len(raw)!=profile['size']:raise StringValueError('Fixed string must contain exactly Length encoded units')
    return LiteralWrite(raw,profile['size'],profile['unit_bytes'])

def format_value(profile,raw):
    _active(profile)
    if type(raw) is not bytes or len(raw)!=profile['size']:raise StringValueError('Read snapshot must match exact bounded span')
    if profile['properties']['ZeroTerminate']:
        unit=profile['unit_bytes']
        for offset in range(0,len(raw),unit):
            if raw[offset:offset+unit]==bytes(unit):
                raw=raw[:offset];break
    try:return raw.decode(profile['encoding'],errors='strict')
    except UnicodeError as error:raise StringValueError('Read string cannot be decoded by this profile') from error

def desired_matches(profile,desired,current):
    _active(profile)
    if (type(desired) is not LiteralWrite
            or type(desired.read_bound) is not int or type(desired.unit_bytes) is not int
            or desired.read_bound!=profile['size'] or desired.unit_bytes!=profile['unit_bytes']):
        raise StringValueError('String desire is not profile-bound')
    if type(current) is not bytes or len(current)!=profile['size']:raise StringValueError('Incomplete current string span')
    # Reconstruct the desired literal, rather than trusting a public dataclass.
    raw=desired.replacement
    if type(raw) is not bytes or not 0<len(raw)<=profile['size'] or len(raw)%profile['unit_bytes']:
        raise StringValueError('Malformed desired bytes')
    if profile['properties']['ZeroTerminate']:
        if not raw.endswith(bytes(profile['unit_bytes'])):raise StringValueError('Missing desired terminator')
        text=raw[:-profile['unit_bytes']]
    else:text=raw
    try:literal=text.decode(profile['encoding'],errors='strict')
    except UnicodeError as error:raise StringValueError('Malformed desired encoding') from error
    if parse(profile,literal)!=desired:raise StringValueError('Desired bytes do not describe a canonical literal')
    return current[:len(raw)]==raw
