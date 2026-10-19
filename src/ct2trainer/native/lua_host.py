"""Independent CE-facing adapters over MIT Lupa's upstream Lua 5.3 runtime.

The language implementation is upstream Lua, never CE's patched DLL. Host calls
are bounded broker requests. This restricted environment is a compatibility
profile, not a claim that embedding Lua is an operating-system security sandbox.
"""
from __future__ import annotations
from .custom_types import CustomTypeError
from .restoration_budget import restoration_entry

from contextlib import contextmanager
from .lua_work_budget import WorkLimits, work_slice, broker_checkpoint

import re
import struct
import threading
import time
import weakref
from typing import Any


_helper_install_context = threading.local()
_syntax_check_context = threading.local()
MAX_HELPER_INSTALL_DEPTH = 4
MAX_SYNTAX_CHECK_DEPTH = 4
MAX_TRANSPORT_NODES = 262144
MAX_TRANSPORT_BYTES = 4 * 1024 * 1024
MAX_TRANSPORT_ITEMS = 65536
MAX_TRANSPORT_DEPTH = 8
_TRANSPORT_CHECKPOINT_INTERVAL = 256


class LuaHostError(RuntimeError):
    pass


def _host_error(exc: Exception) -> LuaHostError:
    """Bounded host error that keeps a codec abort payload, when present.

    A CustomTypeError becomes a named, JSON-capable abort (code + reason +
    stable payload) instead of a Python traceback string. The codec is pure,
    so the abort must not trigger follow-up writes or marker cleanup.
    """
    if isinstance(exc, CustomTypeError):
        error = LuaHostError(f'{exc.code}: {exc.reason}')
        error.abort_payload = exc.to_abort().to_dict()
        return error
    error = LuaHostError(str(exc))
    payload = getattr(exc, 'abort_payload', None)
    if payload is not None:
        error.abort_payload = payload
    return error


class _TransportBudget:
    """Bound the expanded Python work separately from Lua's allocator.

    Shared tables are charged on every traversal: a small Lua DAG must not
    expand into an unbounded Python tree. The byte limit measures payload,
    while the node limit separately bounds object/container overhead. These
    are finite transport limits, not a claim about exact process RSS.
    """

    def __init__(self, host: 'LuaHost'):
        self.host = host
        self.nodes = 0
        self.bytes = 0
        host._checkpoint()

    def charge(self, value: Any) -> None:
        self.nodes += 1
        if self.nodes > MAX_TRANSPORT_NODES:
            raise LuaHostError('Lua transport expanded node limit exceeded')
        remaining = MAX_TRANSPORT_BYTES - self.bytes
        if type(value) is str:
            # Reject large strings before creating their UTF-8 byte copy.
            if len(value) > remaining:
                raise LuaHostError('Lua transport payload byte limit exceeded')
            try:
                size = len(value.encode('utf-8'))
            except UnicodeError as exc:
                raise LuaHostError('Lua transport text must be valid UTF-8') from exc
        elif type(value) is int:
            size = max(8, (value.bit_length() + 7) // 8)
        elif value is None or type(value) in (bool, float):
            size = 8
        else:
            size = 16
        self.bytes += size
        if self.bytes > MAX_TRANSPORT_BYTES:
            raise LuaHostError('Lua transport payload byte limit exceeded')
        if self.nodes % _TRANSPORT_CHECKPOINT_INTERVAL == 0:
            self.host._checkpoint()

    def finish(self) -> None:
        # Short conversions also recheck identity/cancellation before a broker
        # request, Lua resumption or disposable result can escape.
        self.host._checkpoint()


class LuaMemoryPool:
    """Trusted aggregate allocator budget for host-managed Lua operations.

    Every runtime uses Lupa's tracked allocator. ``total=True`` includes its
    standard-library base allocation, unlike the per-host script allowance.
    Cancelled states remain charged while any host, Lua value or runtime is
    retained; private bound callbacks keep their weakly registered host alive.
    Direct Python access to a runtime is trusted and must not execute Lua outside
    its host. Lua scripts cannot access this pool or change allocator ceilings.
    """

    MAX_MEMORY = 64 * 1024 * 1024
    MAX_STATES = 64
    # Pinned Lupa initializes fixed upstream libraries before setting max_memory.
    # Require this remaining startup allowance before creating any interpreter;
    # immediately apply a total allocator cap before our bootstrap/source runs.
    _STARTUP_ALLOWANCE = 1024 * 1024
    # Keep a small aggregate margin for finite private cancellation housekeeping.
    _HOUSEKEEPING_ALLOWANCE = 64 * 1024

    def __init__(self, *, max_memory: int = MAX_MEMORY, max_states: int = MAX_STATES):
        if type(max_memory) is not int or not self._STARTUP_ALLOWANCE <= max_memory <= self.MAX_MEMORY:
            raise ValueError('Lua aggregate memory budget is outside 1..64 MiB')
        if type(max_states) is not int or not 1 <= max_states <= self.MAX_STATES:
            raise ValueError('Lua state budget is outside 1..64')
        self.max_memory, self.max_states = max_memory, max_states
        self._lock = threading.RLock()
        self._hosts: weakref.WeakValueDictionary[int, LuaHost] = weakref.WeakValueDictionary()

    @property
    def state_count(self) -> int:
        with self._lock:
            return len(self._hosts)

    @property
    def memory_used(self) -> int:
        with self._lock:
            return sum(host.lua.get_memory_used(total=True) for host in list(self._hosts.values()))

    def _before_create(self) -> None:
        if len(self._hosts) >= self.max_states:
            raise LuaHostError('Lua aggregate state limit exceeded')
        if self.max_memory - self.memory_used < self._STARTUP_ALLOWANCE:
            raise LuaHostError('Lua aggregate memory budget has insufficient startup allowance')

    def _register(self, host: 'LuaHost') -> None:
        self._hosts[id(host)] = host
        if host._base_memory > self._STARTUP_ALLOWANCE:
            raise LuaHostError('Pinned Lua runtime exceeded its reserved startup allowance')
        self._refresh_limits()

    def _refresh_limits(self, *, housekeeping: 'LuaHost | None' = None) -> None:
        hosts = list(self._hosts.values())
        usage = [(host, host.lua.get_memory_used(total=True)) for host in hosts]
        used = sum(size for _, size in usage)
        if used > self.max_memory:
            raise LuaHostError('Lua aggregate allocator budget was exceeded')
        for host, size in usage:
            internal = host is housekeeping
            remaining = self.max_memory - used + size
            if not internal:
                remaining -= self._HOUSEKEEPING_ALLOWANCE
            ceiling = host._base_memory + host.memory_limit
            if internal:
                ceiling += self._HOUSEKEEPING_ALLOWANCE
            # Zero means unlimited in Lupa. A positive ceiling below current
            # usage prevents new allocations while still permitting releases.
            host.lua.set_max_memory(max(1, min(ceiling, remaining)), total=True)


BOOTSTRAP = r'''
local broker, checkpoint = ...
local checking, current_record_id=false,nil
local clockhook = function() checkpoint() end
local sethook, getinfo, gethook = debug.sethook, debug.getinfo, debug.gethook
local pairs, tostring, error = pairs, tostring, error
local lua_setmetatable, lua_rawget, lua_type = setmetatable, rawget, type
-- Lua53 marks tables for finalization only when setting a metatable whose raw
-- __gc field is non-nil. Even false/0 placeholders can later become callbacks.
-- Reject that registration on every setter call; later edits to a previously
-- unmarked table do not mark it (Lua53 manual section 2.5.1). No marked object,
-- raw setter, debug API or foreign userdata is exposed to script code.
-- Finalizers otherwise execute during Lua GC/close outside our slice hooks.
local function profile_setmetatable(object, metatable)
  if lua_type(metatable)=='table' and lua_rawget(metatable,'__gc')~=nil then
    error('Lua finalizer metatables are outside the host profile',2)
  end
  return lua_setmetatable(object,metatable)
end
setmetatable=profile_setmetatable
-- Compatibility constructors also use the private checked setter if a script
-- replaces the public global. Ordinary metatable identity/mutation is retained.
local setmetatable=profile_setmetatable
local cocreate, coresume, coyield, costatus = coroutine.create, coroutine.resume, coroutine.yield, coroutine.status
local unpack, pack = table.unpack, table.pack
local rawpcall, rawxpcall = pcall, xpcall
-- A script may catch ordinary errors, but cannot consume cancellation or the
-- current slice's budget error and continue indefinitely inside pcall.
function pcall(...)
  local result=pack(rawpcall(...))
  checkpoint()
  return unpack(result,1,result.n)
end
function xpcall(...)
  local result=pack(rawxpcall(...))
  checkpoint()
  return unpack(result,1,result.n)
end
local function call(name, ...)
  checkpoint()
  return broker(name, ...)
end
local function proxy(kind, id)
  return setmetatable({}, {
    __index=function(_, key)
      if key=='destroy' then return function() return call('destroy',kind,id) end end
      if kind=='record' then return call('record.get',id,key) end
      if kind=='addresslist' then
        if key=='getMemoryRecordByID' or key=='getMemoryRecordByDescription' then
          return function(value)
            local identifier=call('addresslist.'..key,value)
            return identifier and proxy('record',identifier) or nil
          end
        end
        if key=='Count' then return call('addresslist.Count') end
        if key=='MemoryRecord' then
          return setmetatable({}, {__index=function(_, index)
            return proxy('record',call('addresslist.at',index))
          end})
        end
      end
      error('Unsupported '..kind..' property: '..tostring(key),2)
    end,
    __newindex=function(_, key, value)
      if kind~='record' then error('Read-only compatibility object',2) end
      return call('record.set',id,key,value)
    end,
    __metatable='CT2Trainer compatibility object'
  })
end
-- These symbolic constants cover this profile's exact byte-array scan API.
-- Numeric CE enum ordinals are not inferred from implementation sources.
soExactValue='soExactValue'; rtRounded='rtRounded'
-- Published MemoryRecord value-type constants, from API documentation.
vtByte=0; vtWord=1; vtDword=2; vtQword=3; vtSingle=4; vtDouble=5
vtString=6; vtUnicodeString=7; vtByteArray=8; vtBinary=9; vtAll=10
vtAutoAssembler=11; vtPointer=12; vtCustom=13; vtGrouped=14; vtByteArrays=15
fsmNotAligned=0; fsmAligned=1; fsmLastDigits=2
local scans, scan_count=setmetatable({}, {__mode='k'}),0
function createMemScan(progressbar)
  if progressbar~=nil then error('Scan progress controls are outside this profile',2) end
  if scan_count>=128 then error('Memory scan object limit exceeded',2) end
  local data={dead=false,complete=false,addresses=nil,only_one=false}
  local object
  object=setmetatable({}, {
    __index=function(_,key)
      if data.dead then error('Memory scan is destroyed',2) end
      if key=='firstScan' then return function(...)
        data.complete=false; data.addresses=nil
        data.addresses=call('scan.firstScan',...)
        data.complete=true
      end end
      if key=='waitTillDone' then return function()
        if not data.complete then error('Memory scan has not completed',2) end
      end end
      if key=='destroy' then return function() data.dead=true; data.addresses=nil; scan_count=scan_count-1 end end
      -- CE TMemScan contract: Result is the single found address as an
      -- integer (nil otherwise); it answers the first result when the
      -- OnlyOneResult flag asked for a single-result scan.
      if key=='Result' then
        local addresses=data.addresses
        if not addresses then return nil end
        if #addresses==1 or (data.only_one and #addresses>0) then
          return tonumber(addresses[1],16)
        end
        return nil
      end
      if key=='OnlyOneResult' then return data.only_one end
      error('Unsupported memory scan property: '..tostring(key),2)
    end,
    __newindex=function(_,key,value)
      if key=='OnlyOneResult' then
        if data.dead then error('Memory scan is destroyed',2) end
        data.only_one=value~=nil and value~=false
        return
      end
      error('Memory scan property is outside this profile',2)
    end,
    __metatable='CT2Trainer memory scan'
  })
  scans[object]=data; scan_count=scan_count+1
  return object
end
function createFoundList(scan)
  local data=scans[scan]
  if not data or data.dead then error('Found list requires a live memory scan',2) end
  local dead,initialized=false,false
  local function check()
    if dead then error('Found list is destroyed',2) end
    if data.dead then error('Found list memory scan is destroyed',2) end
    if not initialized then error('Found list is not initialized',2) end
  end
  return setmetatable({}, {
    __index=function(_,key)
      if key=='destroy' then return function() dead=true end end
      if key=='initialize' then return function()
        if dead or data.dead or not data.complete then error('Found list requires a completed memory scan',2) end
        initialized=true
      end end
      check()
      if key=='Count' then return #data.addresses end
      if key=='Address' then return setmetatable({}, {__index=function(_,index)
        check()
        if type(index)~='number' or index%1~=0 or index<0 then error('Invalid found list index',2) end
        return data.addresses[index+1]
      end}) end
      -- CE FoundList contract (0-based rows): getCount() reports the row
      -- count; getAddress(i) answers the 8-digit uppercase hexadecimal
      -- address, the zero address for an out-of-bounds row.
      if key=='getCount' then return function()
        check()
        return #data.addresses
      end end
      if key=='getAddress' then return function(index)
        check()
        if index==nil then return nil end
        if type(index)~='number' or index%1~=0 then error('Invalid found list index',2) end
        if index<0 or index>=#data.addresses then return '00000000' end
        return string.format('%08X',tonumber(data.addresses[index+1],16))
      end end
      error('Unsupported found list property: '..tostring(key),2)
    end,
    __newindex=function() error('Found lists are read-only',2) end,
    __metatable='CT2Trainer found list'
  })
end
-- CE string-list utility (TStrings surface). Bounded in-memory list: file
-- I/O and foreign object data are outside the profile. Indices follow the
-- CE 0-based ordinal (item 0 is the first entry); add() returns the new
-- ordinal. Case-sensitive lookups are opt-in, matching the CE default.
local stringlists, stringlist_count, stringlist_item_limit={},0,65536
local function stringlist_new()
  if stringlist_count>=256 then error('String list object limit exceeded',2) end
  local data={items={},case_sensitive=false,updates=0}
  local function ordinal(index)
    if type(index)~='number' or index%1~=0 or index<0 or index>=#data.items then
      error('String list index out of range',2)
    end
    return index
  end
  local function item_of(value)
    if type(value)~='string' and type(value)~='number' then
      error('String list items require text',2)
    end
    return tostring(value)
  end
  local function find_item(value)
    local text=item_of(value)
    for i=0,#data.items-1 do
      local item=data.items[i+1]
      if (data.case_sensitive and item==text)
         or (not data.case_sensitive and item:lower()==text:lower()) then
        return i
      end
    end
    return -1
  end
  local function append(value)
    if #data.items>=stringlist_item_limit then error('String list item limit exceeded',2) end
    data.items[#data.items+1]=item_of(value)
    return #data.items-1
  end
  local object
  object=setmetatable({}, {
    __index=function(_,key)
      if type(key)=='number' then return data.items[ordinal(key)+1] end
      if key=='add' then return function(value,extra)
        if extra~=nil and extra~=0 then error('String list object data is outside this profile',2) end
        return append(value)
      end end
      if key=='addText' then return function(value)
        append(value)
      end end
      if key=='clear' then return function() data.items={} end end
      if key=='delete' then return function(index)
        table.remove(data.items,ordinal(index)+1)
      end end
      if key=='getCount' then return function() return #data.items end end
      if key=='Count' then return #data.items end
      if key=='getString' then return function(index)
        return data.items[ordinal(index)+1]
      end end
      if key=='setString' then return function(index,value)
        data.items[ordinal(index)+1]=item_of(value)
      end end
      if key=='String' then return setmetatable({}, {
        __index=function(_,index) return data.items[ordinal(index)+1] end,
        __newindex=function(_,index,value) data.items[ordinal(index)+1]=item_of(value) end
      }) end
      if key=='indexOf' then return function(value)
        return find_item(value)
      end end
      if key=='insert' then return function(index,value)
        if type(index)~='number' or index%1~=0 or index<0 or index>#data.items then
          error('String list index out of range',2)
        end
        if #data.items>=stringlist_item_limit then error('String list item limit exceeded',2) end
        table.insert(data.items,index+1,item_of(value))
      end end
      if key=='remove' then return function(value)
        local found=find_item(value)
        if found>=0 then table.remove(data.items,found+1) end
      end end
      if key=='beginUpdate' then return function() data.updates=data.updates+1 end end
      if key=='endUpdate' then return function()
        if data.updates==0 then error('String list update is not open',2) end
        data.updates=data.updates-1
      end end
      if key=='CaseSensitive' then return data.case_sensitive end
      if key=='getCaseSensitive' then return function() return data.case_sensitive end end
      if key=='setCaseSensitive' then return function(value)
        data.case_sensitive=value~=nil and value~=false
      end end
      if key=='loadFromFile' or key=='saveToFile' then
        error('String list file access is outside this profile',2)
      end
      if key=='getData' or key=='setData' then
        error('String list object data is outside this profile',2)
      end
      error('Unsupported string list property: '..tostring(key),2)
    end,
    __newindex=function(_,key,value)
      if type(key)=='number' then
        data.items[ordinal(key)+1]=item_of(value)
        return
      end
      if key=='CaseSensitive' then
        data.case_sensitive=value~=nil and value~=false
        return
      end
      error('String list property is outside this profile',2)
    end,
    __metatable='CT2Trainer string list'
  })
  stringlists[object]=data; stringlist_count=stringlist_count+1
  return object
end
function createStringlist()
  return stringlist_new()
end
function createStringList()
  return createStringlist()
end
local functions={
  'getAddress','getAddressSafe','getModuleSize','readInteger','readSmallInteger',
  'readQword','readFloat','readDouble','readPointer','readString',
  'writeInteger','writeSmallInteger','writeQword','writeFloat','writeDouble',
  'writeString','registerSymbol','unregisterSymbol','getAddressOfSymbol',
  'getAddressOfSymbolSafe','getProcHandle','getOpenProcessID','isKeyPressed',
  'getXBox360ControllerState','showMessage','print','executeCodeEx','fullAccess',
  'speedhack_setSpeed','speedhack_getSpeed','attachProcess','detachProcess',
  'LaunchMonoDataCollector','mono_enumDomains','mono_findMethod','mono_invoke_method'
}
for _, name in ipairs(functions) do
  _G[name]=function(...) return call(name,...) end
end
function readBytes(address,count,asTable)
  local bytes=call('readBytes',address,count)
  if asTable then return bytes end
  return unpack(bytes,1,#bytes)
end
function writeBytes(address,...)
  local values=pack(...)
  if values.n==1 and type(values[1])=='table' then values=values[1]
  else values.n=nil end
  return call('writeBytes',address,values)
end
function getAddressList() return proxy('addresslist',0) end
function autoAssemble(source,targetSelf,disableInfo)
  if targetSelf then error('Local process assembly is outside this profile',2) end
  local result=call('autoAssemble',source,disableInfo)
  if type(result)=='table' and type(result.ok)=='boolean' then
    return result.ok,result.disableInfo
  end
  return result
end
-- Owned trainer-engine facade: a closed surface, never the raw controller.
local function engine_menu_item(name)
  return setmetatable({}, {
    __index=function(_,key)
      if key=='doClick' then return function() call('luaEngine.menuClick',name) end end
      error('Unsupported menu item property: '..tostring(key),2)
    end,
    __newindex=function() error('Menu items are read-only',2) end,
    __metatable='CT2Trainer menu item'
  })
end
function getLuaEngine()
  local data=call('luaEngine.snapshot')
  return setmetatable({}, {
    __index=function(_,key)
      if key=='close' then return function() call('luaEngine.close') end end
      if key=='attached' then return data.attached end
      if key=='processName' then return data.process end
      if key=='clickMenuItem' then return function(name) call('luaEngine.menuClick',name) end end
      if type(key)=='string' and key:match('^MenuItem%d+$') then return engine_menu_item(key) end
      error('Unsupported trainer engine property: '..tostring(key),2)
    end,
    __newindex=function() error('Trainer engine is read-only',2) end,
    __metatable='CT2Trainer engine facade'
  })
end
-- Compatibility spelling: the pinned corpus calls GetLuaEngine() with a
-- capital G (35/35 usages, Borderlands3); both spellings are owned aliases.
function GetLuaEngine()
  return getLuaEngine()
end
function AOBScan(pattern,protection,alignmentType,alignmentParameter)
  local addresses=call('AOBScan',pattern,protection,alignmentType,alignmentParameter)
  if not addresses or #addresses==0 then return nil end
  local alive=true
  return setmetatable({}, {
    __index=function(_,key)
      if not alive then error('Scan result is destroyed',2) end
      if key=='Count' then return #addresses end
      if key=='destroy' then return function() alive=false end end
      if type(key)=='number' and key>=0 and key%1==0 then return addresses[key+1] end
      error('Unsupported scan result property',2)
    end,
    __newindex=function() error('Scan results are read-only',2) end,
    __metatable='CT2Trainer scan result'
  })
end
-- Timers are driven by the owner's serialized scheduler, never an unowned OS thread.
local timers, nextid={},0
local workers, workerid, worker_count, current_worker={},0,0,nil
local function owned_context(recordid,callback,...)
  local previous_record,previous_memrec=current_record_id,memrec
  current_record_id=recordid
  memrec=recordid and proxy('record',recordid) or nil
  local results=pack(rawpcall(callback,...))
  current_record_id=previous_record; memrec=previous_memrec
  if not results[1] then error(tostring(results[2]),0) end
  return unpack(results,2,results.n)
end
local function retire_worker(data)
  if not data.dead then
    data.dead=true; workers[data.id]=nil; worker_count=worker_count-1
  end
end
function createThread(callback,...)
  if checking then checkpoint('scheduler-write'); error('Syntax checking cannot create workers',2) end
  if type(callback)~='function' then error('Worker callback must be a Lua function',2) end
  if worker_count>=128 then error('Worker count limit exceeded',2) end
  workerid=workerid+1
  local data,args={id=workerid,dead=false,wait=0,recordid=current_record_id},pack(...)
  local object=setmetatable({}, {
    __index=function(_,key)
      if key=='terminate' then return function()
        if checking then checkpoint('scheduler-write'); error('Syntax checking cannot terminate workers',2) end
        retire_worker(data)
      end end
      if key=='Terminated' then return data.dead end
      error('Unsupported worker property: '..tostring(key),2)
    end,
    __newindex=function() error('Worker properties are read-only',2) end,
    __metatable='CT2Trainer owned worker'
  })
  data.object=object
  data.thread=cocreate(function() return callback(object,unpack(args,1,args.n)) end)
  workers[data.id]=data; worker_count=worker_count+1
  return object
end
function sleep(milliseconds)
  if not current_worker then error('sleep requires an owned cooperative worker',2) end
  if type(milliseconds)~='number' or milliseconds%1~=0 or milliseconds<0 or milliseconds>60000 then
    error('Worker sleep must be 0..60000 milliseconds',2)
  end
  checkpoint()
  return coyield(milliseconds)
end
function createTimer(owner,enabled)
  if checking then checkpoint('scheduler-write'); error('Syntax checking cannot create live timers',2) end
  if owner~=nil then error('Native UI timer owners are unsupported',2) end
  nextid=nextid+1
  local id=nextid
  local data={Enabled=enabled~=false,Interval=1000,OnTimer=nil,elapsed=0,dead=false,recordid=current_record_id}
  local object
  object=setmetatable({}, {
    __index=function(_,key)
      if key=='destroy' then return function()
        if checking then checkpoint('scheduler-write'); error('Syntax checking cannot destroy live timers',2) end
        data.dead=true; timers[id]=nil
      end end
      if data.dead then error('Timer is destroyed',2) end
      if key=='Enabled' or key=='Interval' or key=='OnTimer' then return data[key] end
      error('Unsupported timer property',2)
    end,
    __newindex=function(_,key,value)
      if checking then checkpoint('scheduler-write'); error('Syntax checking cannot change live timers',2) end
      if data.dead then error('Timer is destroyed',2) end
      if key=='Enabled' and type(value)=='boolean' then data[key]=value
      elseif key=='Interval' and type(value)=='number' and value>=1 and value<=60000 and value%1==0 then data[key]=value
      elseif key=='OnTimer' and (type(value)=='function' or value==nil) then data[key]=value
      else error('Invalid timer property',2) end
    end,
    __metatable='CT2Trainer timer'
  })
  data.object=object
  timers[id]=data
  return object
end
local function tick(milliseconds)
  local pending={}
  for id,data in pairs(timers) do pending[#pending+1]={id,data} end
  table.sort(pending,function(a,b) return a[1]<b[1] end)
  for _,item in ipairs(pending) do
    local id,data=item[1],item[2]
    if timers[id]==data and not data.dead and data.Enabled then
      data.elapsed=data.elapsed+milliseconds
      if data.elapsed>=data.Interval and data.OnTimer then
        data.elapsed=data.elapsed%data.Interval
        owned_context(data.recordid,data.OnTimer,data.object)
      end
    end
  end
  local jobs={}
  for id,data in pairs(workers) do jobs[#jobs+1]={id,data} end
  table.sort(jobs,function(a,b) return a[1]<b[1] end)
  for _,job in ipairs(jobs) do
    local id,data=job[1],job[2]
    if workers[id]==data and not data.dead then
      data.wait=math.max(0,data.wait-milliseconds)
      if data.wait==0 then
        current_worker=data
        sethook(data.thread,clockhook,'',1000)
        local ok,delay=owned_context(data.recordid,coresume,data.thread)
        sethook(data.thread)
        current_worker=nil
        if not ok then retire_worker(data); error(tostring(delay),0) end
        checkpoint()
        if costatus(data.thread)=='dead' then retire_worker(data)
        elseif not data.dead then data.wait=delay end
      end
    end
  end
end
local function cancel_resources()
  for _,data in pairs(timers) do data.dead=true end
  timers={}
  for _,data in pairs(workers) do data.dead=true end
  workers={}; worker_count=0; current_worker=nil
  for _,data in pairs(scans) do data.dead=true; data.addresses=nil end
  scan_count=0; current_record_id=nil; memrec=nil
  for _,data in pairs(stringlists) do data.items={} end
  stringlist_count=0; stringlists={}
end
local function cancel()
  -- This may be entered recursively from a Python broker while a user chunk
  -- or worker is suspended. Cleanup is trusted and finite; the suspended
  -- frame must regain its hook so cancellation still stops its next loop.
  local hook,mask,count=gethook()
  sethook()
  local ok,err=rawpcall(cancel_resources)
  if hook then sethook(hook,mask,count) end
  if not ok then error(tostring(err),0) end
end
local function run(source,ischeck,recordid)
  checking=ischeck
  syntaxcheck=ischeck
  current_record_id=recordid
  memrec=recordid and proxy('record',recordid) or nil
  local chunk,err=load(source,'CT2Trainer table Lua','t',_G)
  if not chunk then checking=false; syntaxcheck=false; current_record_id=nil; memrec=nil; error(err,0) end
  sethook(clockhook,'',1000)
  local result=pack(rawpcall(chunk))
  sethook()
  checking=false; syntaxcheck=false; current_record_id=nil; memrec=nil
  if not result[1] then error(tostring(result[2]),0) end
  return unpack(result,2,result.n)
end
local function pulse(milliseconds)
  sethook(clockhook,'',1000)
  local ok,err=rawpcall(tick,milliseconds)
  sethook()
  current_worker=nil; current_record_id=nil; memrec=nil
  if not ok then error(tostring(err),0) end
end
-- Remove loading, filesystem, shell, foreign native modules and Python introspection.
python=nil; package=nil; require=nil; io=nil; os=nil; debug=nil
dofile=nil; loadfile=nil; _G.load=nil; collectgarbage=nil; coroutine=nil
-- run keeps its loader in a private upvalue supplied below by the host.
return run,pulse,cancel
'''


class _ReadOnlyBroker:
    """A disposable checker cannot reach mutation handlers or UI callbacks."""

    _READS = {
        'getAddress', 'getAddressSafe', 'getModuleSize',
        'getAddressOfSymbol', 'getAddressOfSymbolSafe', 'luaEngine.snapshot',
        'getProcHandle', 'getOpenProcessID', 'readInteger',
        'readSmallInteger', 'readQword', 'readFloat', 'readDouble',
        'readPointer', 'readString', 'readBytes', 'AOBScan', 'scan.firstScan',
        'fullAccess',
        'addresslist.Count', 'addresslist.at', 'addresslist.getMemoryRecordByID',
        'addresslist.getMemoryRecordByDescription', 'record.get',
        'isKeyPressed', 'getXBox360ControllerState', 'speedhack_getSpeed',
    }

    def __init__(self, parent: 'LuaHost', *, allow_assembler: bool = True):
        self.parent = parent
        self.generation = parent.generation
        self.allow_assembler = allow_assembler

    def call(self, name: str, arguments: tuple, *, generation: int,
             syntaxcheck: bool) -> Any:
        if self.parent.cancelled or generation != self.generation:
            raise LuaHostError('Lua syntax checking was cancelled or became stale')
        if name in {'print', 'showMessage'}:
            return None
        dry_assembler = (self.allow_assembler and name == 'autoAssemble' and
                         getattr(self.parent.broker, 'syntaxcheck_assembler', False) is True)
        if name not in self._READS and not dry_assembler:
            raise LuaHostError('Syntax checking cannot call mutation API: ' + str(name))
        return self.parent.broker.call(name, arguments, generation=self.generation,
                                       syntaxcheck=True)


class LuaHost:
    """Lua53 state, finite execution slices and generation-bound broker calls.

    ``broker.call(name, arguments)`` returns primitives/lists/dicts only. It owns
    authorization, target identity, transaction receipts and cancellation. The
    Lua environment is never given an engine object or native process handle.
    Each activation can own a separate host through ``owner_record_id`` and
    ``generation``; cancellation then retires only its timers/workers. Scheduler
    callbacks receive their creation record's ``memrec`` context. Syntax checks
    always use disposable states and cannot import live functions or globals.
    Script finalizer metatables are rejected at every registration; ordinary
    metatables remain mutable. Explicit owned lifecycle replaces GC callbacks,
    which upstream Lua can run outside an execution slice during state disposal.
    """

    def __init__(self, broker: Any, *, memory_limit: int = 16 * 1024 * 1024,
                 timeout: float = 0.25, instruction_limit: int = 1_000_000,
                 owner_record_id: int | None = None, generation: int = 0,
                 memory_pool: LuaMemoryPool | None = None,
                 _check_only: bool = False, _cancel_source: 'LuaHost | None' = None,
                 broker_call_timeout: float = 15.0, broker_timeout: float = 30.0,
                 broker_call_limit: int = 4096, wall_timeout: float | None = None,
                 _clock=None):
        if not 1024 * 1024 <= memory_limit <= 256 * 1024 * 1024:
            raise ValueError('Lua memory budget is outside its bounds')
        if not 0.001 <= timeout <= 10 or not 1000 <= instruction_limit <= 10_000_000:
            raise ValueError('Lua execution budget is outside its bounds')
        if (owner_record_id is not None and
                (type(owner_record_id) is not int or not 0 <= owner_record_id <= 0x7FFFFFFFFFFFFFFF)):
            raise ValueError('Lua activation owner must be a nonnegative record ID')
        if type(generation) is not int or not 0 <= generation <= 0x7FFFFFFFFFFFFFFF:
            raise ValueError('Lua activation generation must be a nonnegative integer')
        if memory_pool is not None and not isinstance(memory_pool, LuaMemoryPool):
            raise ValueError('Lua memory pool must be a trusted LuaMemoryPool')
        try:
            from lupa.lua53 import LuaRuntime
        except ImportError as exc:
            raise LuaHostError('Install the pinned MIT Lupa dependency with its Lua 5.3 module') from exc
        self.broker, self.timeout, self.instruction_limit = broker, timeout, instruction_limit
        self.work_limits = WorkLimits(timeout, instruction_limit, broker_call_timeout,
                                      broker_timeout, broker_call_limit,
                                      timeout + broker_timeout if wall_timeout is None else wall_timeout)
        if _clock is not None and not callable(_clock):
            raise ValueError('Work clock must be a trusted callable')
        self._clock = _clock if _clock is not None else lambda: time.monotonic()
        self._work = None
        self.memory_limit, self.owner_record_id = memory_limit, owner_record_id
        self.generation = generation
        self._check_only, self._cancel_source = _check_only, _cancel_source
        self.cancelled = False
        self._cancel_finished = False
        self._lock = threading.RLock()
        self.memory_pool = memory_pool
        self._pool_lock = memory_pool._lock if memory_pool is not None else threading.RLock()
        self._deadline = 0.0
        self._instructions = 0
        self._checking = False
        self._running = False
        self._pending_custom_abort = None
        self._trusted_housekeeping = False
        self._installing_helpers = False
        self._helper_violation = False
        self._bootstrap_sources: tuple[str, ...] = ()
        # Shared lock always precedes the host lock, including startup and
        # reentrant cancellation from a different host's broker callback.
        with self._pool_lock, self._lock:
            if memory_pool is not None:
                memory_pool._before_create()
            self.lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False,
                                  register_builtins=False, attribute_filter=self._deny_attribute,
                                  max_memory=memory_limit)
            self._base_memory = self.lua.get_memory_used(total=True) - self.lua.get_memory_used()
            if memory_pool is not None:
                memory_pool._register(self)
            try:
                # Capture the standard loader before removing global dynamic loading.
                bootstrap = BOOTSTRAP.replace('local unpack, pack = table.unpack, table.pack',
                                              'local unpack, pack, load = table.unpack, table.pack, load')
                self._run, self._pulse, self._cancel = self.lua.execute(bootstrap, self._call, self._checkpoint)
                from .input_state import VIRTUAL_KEYS
                for name,value in VIRTUAL_KEYS.items():
                    self.lua.globals()[name]=value
            except Exception as exc:
                raise LuaHostError('Lua state initialization failed: '+str(exc)) from exc
            finally:
                if memory_pool is not None:
                    memory_pool._refresh_limits()

    @staticmethod
    def _deny_attribute(obj: Any, name: Any, setting: bool) -> None:
        raise LuaHostError('Python object attributes are outside the Lua compatibility profile')

    def _checkpoint(self, reason: str | None = None) -> None:
        # The first Lua instructions entering cancel can cross an existing
        # user hook quantum before its private sethook() executes. Do not
        # charge or abort those internal instructions, nor the restoration.
        # No user callback or broker call is made by this housekeeping path.
        if self._trusted_housekeeping:
            return
        self._instructions += 1000
        if self.cancelled or self._cancel_source is not None and self._cancel_source.cancelled:
            raise LuaHostError('Lua activation was cancelled')
        self._guard_generation()
        if reason == 'scheduler-write' and self._installing_helpers:
            self._helper_violation = True
        if self._helper_violation:
            raise LuaHostError('Lua helper bootstrap attempted a forbidden mutation or scheduler')
        if self._work is None:
            raise LuaHostError('Lua checkpoint requires an owned execution slice')
        self._work.check(instructions=1000)

    def _to_lua(self, value: Any, depth: int = 0, *, _budget: _TransportBudget | None = None) -> Any:
        own_budget = _budget is None
        budget = _budget if _budget is not None else _TransportBudget(self)
        budget.charge(value)
        if value is None or type(value) in (bool, int, float, str):
            result = value
        elif depth >= MAX_TRANSPORT_DEPTH or type(value) not in (tuple, list, dict):
            raise LuaHostError('A broker attempted to expose an unapproved or unbounded Python object')
        elif len(value) > MAX_TRANSPORT_ITEMS:
            raise LuaHostError('Oversized Lua broker data container')
        elif type(value) in (tuple, list):
            result = self.lua.table_from([self._to_lua(v, depth + 1, _budget=budget) for v in value])
        else:
            converted = {}
            for key, item in value.items():
                if type(key) not in (str, int):
                    raise LuaHostError('Invalid Lua broker data key')
                budget.charge(key)
                converted[key] = self._to_lua(item, depth + 1, _budget=budget)
            result = self.lua.table_from(converted)
        if own_budget:
            budget.finish()
        return result

    def _from_lua(self, value: Any, depth: int = 0, *, _budget: _TransportBudget | None = None) -> Any:
        from lupa.lua53 import lua_type
        own_budget = _budget is None
        budget = _budget if _budget is not None else _TransportBudget(self)
        budget.charge(value)
        if value is None or type(value) in (bool, int, float, str):
            result = value
        elif depth >= MAX_TRANSPORT_DEPTH or lua_type(value) != 'table':
            raise LuaHostError('Only bounded data may cross the Lua broker boundary')
        else:
            converted = {}
            array = True
            maximum = 0
            # Do not materialize an unchecked list of raw Lua pairs. Convert
            # each item once, charging repeated references and string keys.
            for key, item in value.items():
                if len(converted) >= MAX_TRANSPORT_ITEMS:
                    raise LuaHostError('Oversized Lua broker data container')
                if type(key) not in (str, int):
                    raise LuaHostError('Invalid Lua broker data key')
                budget.charge(key)
                converted[key] = self._from_lua(item, depth + 1, _budget=budget)
                if type(key) is int and key > 0:
                    maximum = max(maximum, key)
                else:
                    array = False
            result = ([converted[index] for index in range(1, maximum + 1)]
                      if array and maximum == len(converted) else converted)
        if own_budget:
            budget.finish()
        return result

    def _call(self, name: str, *arguments: Any) -> Any:
        if not self._running:
            raise LuaHostError('Lua calls require an active execution slice')
        self._checkpoint()
        if (self._installing_helpers and name not in _ReadOnlyBroker._READS
                and name not in {'print', 'showMessage'}):
            # Record the forbidden API attempt before converting its arguments.
            # An invalid argument caught with Lua pcall must not turn a denied
            # mutation into an apparently usable helper bootstrap.
            self._helper_violation = True
            raise LuaHostError('Lua helper bootstrap cannot call mutation API: ' + str(name))
        if len(arguments) > MAX_TRANSPORT_ITEMS:
            raise LuaHostError('Oversized Lua broker argument container')
        incoming = _TransportBudget(self)
        incoming.charge(arguments)
        args = tuple(self._from_lua(v, _budget=incoming) for v in arguments)
        incoming.finish()
        # Only trusted dispatch is excluded from Lua elapsed time.
        # Both transport directions retain the ordinary execution quota.
        with self._work.dispatch():
            try:
                if self._installing_helpers:
                    result = _ReadOnlyBroker(self, allow_assembler=False).call(
                        name, args, generation=self.generation, syntaxcheck=True)
                else:
                    result = self.broker.call(name, args, generation=self.generation, syntaxcheck=self._checking)
            except CustomTypeError as exc:
                # Convert before the exception crosses the Lua boundary, where
                # its type identity is lost. The pending slot carries the stable
                # abort payload back to the owning slice.
                self._pending_custom_abort = exc.to_abort().to_dict()
                raise _host_error(exc) from exc
        return self._to_lua(result)

    @contextmanager
    def _work_frame(self):
        previous = self._work
        with work_slice(self.work_limits, self._guard_generation, self._clock) as budget:
            self._work = budget
            self._instructions = 0
            try:
                yield
            finally:
                self._work = previous

    @restoration_entry
    def _slice(self, operation: Any, *arguments: Any, syntaxcheck: bool = False) -> Any:
        with self._pool_lock, self._lock:
            if self.cancelled or self._running:
                raise LuaHostError('Lua activation is cancelled or reentrant')
            self._guard_generation()
            if self.memory_pool is not None:
                self.memory_pool._refresh_limits()
            self._checking = syntaxcheck
            self._running = True
            try:
                with self._work_frame():
                    result = operation(*arguments)
                    self._guard_generation()
                    if self._helper_violation:
                        raise LuaHostError('Lua helper bootstrap attempted a forbidden mutation or scheduler')
                    self._work.check()
                    return result
            except CustomTypeError as exc:
                # Named, JSON-capable abort instead of a Python traceback string.
                # The codec is pure: no partial state, no follow-up writes and no
                # marker cleanup may be triggered by this abort.
                abort = LuaHostError(f'{exc.code}: {exc.reason}')
                abort.abort_payload = exc.to_abort().to_dict()
                raise abort from exc
            except Exception as exc:
                error = LuaHostError(str(exc))
                # Lupa discards the exception object at the Lua boundary; the
                # pending slot carries the stable abort payload to this slice.
                if self._pending_custom_abort is not None:
                    error.abort_payload = self._pending_custom_abort
                raise error from exc
            finally:
                self._pending_custom_abort = None
                self._running = False
                self._checking = False
                if self.memory_pool is not None:
                    self.memory_pool._refresh_limits()

    @contextmanager
    def controller_work(self):
        """One source-derived activation/checking envelope, Python callers only."""
        self._guard_generation()
        try:
            with self._work_frame():
                with self._work.controller():
                    yield self._work
        except Exception as exc:
            # _host_error keeps a codec abort payload attached, when present.
            raise _host_error(exc) from exc

    def _guard_generation(self) -> None:
        host, seen = self, set()
        while host is not None:
            if id(host) in seen or len(seen) > MAX_SYNTAX_CHECK_DEPTH:
                raise LuaHostError('Lua cancellation source recursion exceeds its bound')
            seen.add(id(host))
            if host.cancelled:
                raise LuaHostError('Lua activation was cancelled')
            generation = getattr(host.broker, 'generation', host.generation)
            if type(generation) is not int or generation != host.generation:
                raise LuaHostError('Stale Lua session generation')
            host = host._cancel_source

    @property
    def helper_sources(self) -> tuple[str, ...]:
        """Immutable explicit source provenance, never exposed to Lua scripts."""
        return self._bootstrap_sources

    def install_helpers(self, source: str) -> None:
        """Install one explicit source directly into this private activation.

        All target mutation and scheduler creation is denied, including attempts
        caught with Lua pcall. Helpers and ordinary local state can persist. Any
        failed attempt cancels the host; source is recorded only after success.
        Disposable checks replay this exact source in their own private state.
        """
        depth = getattr(_helper_install_context, 'depth', 0)
        with self._pool_lock, self._lock:
            try:
                from .lua_bootstrap import prepare_lua_bootstrap
                source = prepare_lua_bootstrap(source)['source']
                if self.cancelled or self._running or self._installing_helpers:
                    raise LuaHostError('Lua helper installation is cancelled or reentrant')
                self._guard_generation()
                if self._bootstrap_sources:
                    raise LuaHostError('Lua helper bootstrap permits one explicit source per activation')
                if depth >= MAX_HELPER_INSTALL_DEPTH:
                    raise LuaHostError('Lua helper installation nesting exceeds its bound')
                _helper_install_context.depth = depth + 1
                self._installing_helpers = True
                self._slice(self._run, source, True, self._record_context(None), syntaxcheck=True)
                self._bootstrap_sources = (source,)
            except Exception as exc:
                try:
                    self.cancel()
                except Exception as cleanup:
                    raise LuaHostError(str(exc) + '; helper cancellation cleanup failed: ' + str(cleanup)) from exc
                raise LuaHostError(str(exc)) from exc
            finally:
                self._installing_helpers = False
                _helper_install_context.depth = depth

    def execute(self, source: str, *, syntaxcheck: bool = False, record_id: int | None = None) -> Any:
        if not isinstance(source, str) or len(source.encode('utf-8')) > 1024 * 1024:
            raise LuaHostError('Lua source exceeds the 1 MiB bound')
        record_id = self._record_context(record_id)
        if syntaxcheck and not self._check_only:
            return self._disposable_check(lambda checker: checker.execute(source, record_id=record_id))
        checking = syntaxcheck or self._check_only
        return self._slice(self._run, source, checking, record_id, syntaxcheck=checking)

    def _record_context(self, record_id: int | None) -> int | None:
        if record_id is not None and (type(record_id) is not int or not 0 <= record_id <= 0x7FFFFFFFFFFFFFFF):
            raise LuaHostError('Lua record context must be a nonnegative record ID')
        if self.owner_record_id is not None:
            if record_id is not None and record_id != self.owner_record_id:
                raise LuaHostError('Lua record context differs from its activation owner')
            return self.owner_record_id
        return record_id

    def _checked_result(self, value: Any, depth: int = 0, *, _budget: _TransportBudget | None = None) -> Any:
        # No Lua table/function/userdata from the disposable interpreter may
        # escape into a live activation. Return detached bounded data only.
        own_budget = _budget is None
        budget = _budget if _budget is not None else _TransportBudget(self)
        if type(value) in (tuple, list):
            budget.charge(value)
            if depth >= MAX_TRANSPORT_DEPTH or len(value) > MAX_TRANSPORT_ITEMS:
                raise LuaHostError('Oversized or unbounded Lua checker result container')
            items = [self._checked_result(item, depth + 1, _budget=budget) for item in value]
            result = tuple(items) if type(value) is tuple else items
        else:
            result = self._from_lua(value, depth, _budget=budget)
        if own_budget:
            budget.finish()
        return result

    def _disposable_check(self, operation: Any) -> Any:
        depth = getattr(_syntax_check_context, 'depth', 0)
        with self._pool_lock, self._lock:
            if self.cancelled or self._running:
                raise LuaHostError('Lua activation is cancelled or reentrant')
            self._guard_generation()
            if self._check_only or depth >= MAX_SYNTAX_CHECK_DEPTH:
                raise LuaHostError('Nested disposable Lua checking exceeds its profile bound')
            _syntax_check_context.depth = depth + 1
            self._running = True
            checker = None
            try:
                with self._work_frame():
                    with self._work.controller():
                        checker = LuaHost(_ReadOnlyBroker(self), memory_limit=self.memory_limit,
                                          timeout=self.timeout, instruction_limit=self.instruction_limit,
                                          owner_record_id=self.owner_record_id, generation=self.generation,
                                          memory_pool=self.memory_pool,
                                          _check_only=True, _cancel_source=self,
                                          broker_call_timeout=self.work_limits.broker_call_seconds,
                                          broker_timeout=self.work_limits.broker_seconds,
                                          broker_call_limit=self.work_limits.broker_calls,
                                          wall_timeout=self.work_limits.wall_seconds, _clock=self._clock)
                        for source in self._bootstrap_sources:
                            checker.install_helpers(source)
                        # Direct nth scans/linking are trusted work too; any
                        # checker.execute call enters a charged Lua frame.
                        checker._work = self._work
                        value = operation(checker)
                    result = checker._checked_result(value)
                    self._work.check()
                    return result
            except Exception as exc:
                raise _host_error(exc) from exc
            finally:
                try:
                    if checker is not None:
                        checker.cancel()
                finally:
                    self._running = False
                    _syntax_check_context.depth = depth
                    if self.memory_pool is not None:
                        self.memory_pool._refresh_limits()

    def check_sources(self, sources: list[str] | tuple[str, ...], *,
                      record_id: int | None = None) -> list[Any]:
        """Check explicit bootstrap/record sources in one disposable interpreter.

        Sources can share checker-local definitions. Explicit installed helper
        sources are replayed first; mutable live globals/functions are never
        copied, and returned values are detached data.
        """
        if (not isinstance(sources, (tuple, list)) or not 1 <= len(sources) <= 64
                or any(not isinstance(source, str) for source in sources)
                or sum(len(source.encode('utf-8')) for source in sources) > 4 * 1024 * 1024):
            raise LuaHostError('Syntax-check sources must be a bounded sequence of text')
        record_id = self._record_context(record_id)
        return self._disposable_check(lambda checker: [checker.execute(source, record_id=record_id)
                                                       for source in sources])

    def expand_assembler(self, source: str, *, phase: str = 'enable',
                         syntaxcheck: bool = False, record_id: int | None = None) -> str:
        if not isinstance(source, str) or len(source.encode('utf-8')) > 1024 * 1024:
            raise LuaHostError('Lua assembler source exceeds its 1 MiB bound')
        with self.controller_work():
            return self._expand_assembler_body(source, phase=phase, syntaxcheck=syntaxcheck, record_id=record_id)

    def _expand_assembler_body(self, source: str, *, phase: str = 'enable',
                               syntaxcheck: bool = False, record_id: int | None = None) -> str:
        """Execute explicit Lua sections, inserting their returned AA text.

        This identifies language delimiters; it never translates Lua syntax.
        A delimiter must occupy its own line. Only Lua in the preamble and the
        selected phase runs. Inactive phase Lua is omitted; its expansion must
        be requested separately when that phase is needed by the controller.
        """
        if phase not in {'enable','disable'}:
            raise LuaHostError('Assembler Lua phase must be enable or disable')
        record_id = self._record_context(record_id)
        if syntaxcheck and not self._check_only:
            return self._disposable_check(lambda checker: checker.expand_assembler(
                source, phase=phase, syntaxcheck=True, record_id=record_id))
        result, lua_lines, current_phase, execute_block = [], None, None, True
        for line in source.splitlines():
            section = re.fullmatch(r'\s*\[(ENABLE|DISABLE)\]\s*',line,re.I) if lua_lines is None else None
            if section:
                current_phase=section.group(1).lower()
                result.append(line)
                continue
            marker = re.fullmatch(r'\s*\{\$(lua|asm)\}\s*', line, re.I)
            if marker:
                mode = marker.group(1).lower()
                if mode == 'lua':
                    if lua_lines is not None:
                        raise LuaHostError('Nested Lua assembler sections')
                    lua_lines = []
                    execute_block=current_phase is None or current_phase==phase
                elif lua_lines is not None:
                    value = self.execute('\n'.join(lua_lines), syntaxcheck=syntaxcheck, record_id=record_id) if execute_block else None
                    if value is not None:
                        if not isinstance(value, str):
                            raise LuaHostError('A Lua assembler section must return text or nil')
                        result.append(value)
                    lua_lines = None
                else:
                    raise LuaHostError('ASM delimiter without a Lua section')
            elif lua_lines is not None:
                lua_lines.append(line)
            else:
                result.append(line)
        if lua_lines is not None:
            raise LuaHostError('Unterminated Lua assembler section')
        return '\n'.join(result)

    def tick(self, milliseconds: int) -> None:
        if type(milliseconds) is not int or not 0 <= milliseconds <= 60000:
            raise LuaHostError('Invalid scheduler elapsed time')
        self._slice(self._pulse, milliseconds)

    def cancel(self) -> None:
        # Set the flag before waiting for the runtime lock, so an active hook sees it.
        self.cancelled = True
        with self._pool_lock, self._lock:
            if self._cancel_finished:
                return
            self.generation += 1
            self._trusted_housekeeping = True
            try:
                if self.memory_pool is not None:
                    self.memory_pool._refresh_limits(housekeeping=self)
                self._cancel()
                self._cancel_finished = True
            finally:
                self._trusted_housekeeping = False
                if self.memory_pool is not None:
                    self.memory_pool._refresh_limits()


class EngineLuaBroker:
    """CE-shaped reads/record operations routed through TrainerEngine.

    Raw script memory writes and symbols require an activation-owned handler,
    supplied by the hook controller. They cannot silently bypass its journal.
    """

    def __init__(self, engine: Any, mutation_handler: Any = None, assembler_handler: Any = None,
                 message_handler: Any = None, input_handler: Any = None,
                 shutdown_handler: Any = None, menu_actions: Any = None):
        self.engine = engine
        self.mutation_handler, self.assembler_handler = mutation_handler, assembler_handler
        if input_handler is None:
            from .input_state import Win32InputState
            input_handler=Win32InputState()
        self.message_handler, self.input_handler = message_handler, input_handler
        # Owned routes for the getLuaEngine() facade: the owner (UI/headless
        # test) registers the shutdown and menu actions; without them the
        # corresponding calls refuse fail-closed.
        self.shutdown_handler = shutdown_handler
        self.menu_actions = dict((name.casefold(), action)
                                 for name, action in (menu_actions or {}).items())
        self.generation = 0
        self.identity = engine.memory.identity if engine.memory is not None else None

    def invalidate(self) -> None:
        self.generation += 1

    def call(self, name: str, arguments: tuple, *, generation: int, syntaxcheck: bool) -> Any:
        broker_checkpoint()
        e = self.engine
        if generation != self.generation:
            raise LuaHostError('Stale Lua session generation')
        e._guard()
        if e.memory.identity != self.identity:
            raise LuaHostError('Lua target identity changed; create a fresh activation')
        memory = e.memory
        def address(value: Any) -> int:
            if type(value) is int:
                memory._range(value, 1)
                return value
            from .address_expression import resolve_expression
            return resolve_expression(value,memory,e.symbols,process_name=e.plan['process_name'],pointer_size=memory.pointer_size)
        if name in {'getAddress', 'getAddressSafe'}:
            try:
                return address(arguments[0])
            except Exception:
                if name == 'getAddressSafe':
                    return None
                raise
        if name == 'getModuleSize':
            return memory.module(arguments[0])[1]
        if name in {'getAddressOfSymbol', 'getAddressOfSymbolSafe'}:
            # The engine registry is keyed casefolded; the lookup is a pure
            # read of the current generation's symbol state.
            if len(arguments) != 1:
                raise LuaHostError('Symbol lookup takes exactly one name')
            symbol = arguments[0]
            if type(symbol) is not str or not symbol:
                raise LuaHostError('Symbol name must be non-empty text')
            address = e.symbols.get(symbol.casefold())
            if address is None:
                if name == 'getAddressOfSymbolSafe':
                    return None
                raise LuaHostError('Symbol is not registered: ' + symbol)
            return address
        if name == 'luaEngine.snapshot':
            if arguments:
                raise LuaHostError('Engine snapshot takes no arguments')
            return {
                'attached': memory is not None,
                'process': e.plan['process_name'],
            }
        if name in {'luaEngine.close', 'luaEngine.menuClick'}:
            if syntaxcheck:
                raise LuaHostError('Trainer engine action requires a live activation')
            if name == 'luaEngine.close':
                if self.shutdown_handler is None:
                    raise LuaHostError('Engine close requires an owned shutdown route')
                self.shutdown_handler()
                return None
            if len(arguments) != 1 or type(arguments[0]) is not str or not arguments[0]:
                raise LuaHostError('Menu item name must be non-empty text')
            action = self.menu_actions.get(arguments[0].casefold())
            if action is None:
                raise LuaHostError('Menu item is not registered: ' + arguments[0])
            return action()
        if name == 'executeCodeEx':
            # Typed one-shot target call: CE shape (handle, reserved, function,
            # words). The engine owns the call-broker binding lifecycle and
            # every refusal surfaces as a named error, never a silent nil.
            if syntaxcheck:
                raise LuaHostError('Typed target calls cannot be syntax-checked')
            return self.engine.typed_call(arguments)
        if name in {'getProcHandle', 'getOpenProcessID'}:
            # Read-only access to the owned session target. Creating further
            # process handles (OpenProcess) stays outside the profile.
            if arguments:
                raise LuaHostError('Process API takes no arguments')
            if name == 'getProcHandle':
                return int(memory.process_handle)
            return int(memory.pid)
        if name in {'attachProcess', 'detachProcess'}:
            # lua_debugger_api surface: the engine owns at most one
            # debugger session per attached target, created lazily
            # through the injected binding. The default route refuses
            # visibly fail-closed until the owned Windows debug attach
            # route exists (AP-11); the tested DebugEventCoordinator
            # stays the scoped quiescence owner.
            if name == 'attachProcess':
                if len(arguments) != 1 or type(arguments[0]) is not int:
                    raise LuaHostError(
                        'attachProcess takes exactly one integer PID')
                if syntaxcheck:
                    raise LuaHostError(
                        'Debugger attach requires a live activation')
                self.engine.debugger_attach(arguments[0])
                return None
            if arguments:
                raise LuaHostError('detachProcess takes no arguments')
            if syntaxcheck:
                raise LuaHostError(
                    'Debugger detach requires a live activation')
            self.engine.debugger_detach()
            return None
        if name == 'LaunchMonoDataCollector':
            # lua_managed_runtime surface: the engine owns at most one
            # managed-runtime session per attached target, created lazily
            # through the injected binding. The default route (no factory)
            # refuses visibly fail-closed; the tested Mono stack
            # (mono_broker/mono_runtime) stays the typed stage model.
            if arguments:
                raise LuaHostError('LaunchMonoDataCollector takes no arguments')
            if syntaxcheck:
                raise LuaHostError(
                    'Managed runtime launch requires a live activation')
            self.engine.managed_attach()
            return 1
        if name == 'mono_enumDomains':
            if arguments:
                raise LuaHostError('mono_enumDomains takes no arguments')
            if syntaxcheck:
                raise LuaHostError(
                    'Managed domain enumeration requires a live activation')
            return self.engine.managed_domains()
        if name == 'mono_findMethod':
            if (len(arguments) != 3
                    or any(type(a) is not str or not a for a in arguments)):
                raise LuaHostError(
                    'mono_findMethod takes exactly three non-empty text arguments')
            if syntaxcheck:
                raise LuaHostError(
                    'Managed method lookup requires a live activation')
            return self.engine.managed_find_method(arguments[0], arguments[1],
                                                   arguments[2])
        if name == 'mono_invoke_method':
            if len(arguments) != 4:
                raise LuaHostError(
                    'mono_invoke_method takes exactly four arguments '
                    '(domain, method, isStatic, args)')
            domain, method, is_static, args = arguments
            if type(domain) is int:
                domain_id = domain
            elif type(domain) is dict and type(domain.get('id')) is int:
                domain_id = domain['id']
            else:
                raise LuaHostError(
                    'mono_invoke_method domain must be a domain entry '
                    'or integer id')
            if type(method) is not int:
                raise LuaHostError(
                    'mono_invoke_method method must be an integer token')
            if type(is_static) is not bool and (
                    type(is_static) is not int or is_static not in (0, 1)):
                raise LuaHostError(
                    'mono_invoke_method isStatic must be boolean or 0/1')
            if (not isinstance(args, list)
                    or not all(type(item) is dict and type(item.get('type')) is str
                               and 'value' in item for item in args)):
                raise LuaHostError(
                    'mono_invoke_method args must be a list of '
                    "{'type', 'value'} entries")
            if syntaxcheck:
                raise LuaHostError(
                    'Managed invocation requires a live activation')
            self.engine.managed_invoke(
                domain_id, method, is_static,
                tuple((item['type'], item['value']) for item in args))
            return None
        formats = {'Integer':'I','SmallInteger':'H','Qword':'q','Float':'f','Double':'d',
                   'Pointer':'Q' if memory.pointer_size == 8 else 'I'}
        for suffix, code in formats.items():
            if name == 'read'+suffix:
                if suffix in {'Integer','SmallInteger'} and len(arguments)>1:
                    if type(arguments[1]) is not bool:
                        raise LuaHostError('Integer signed flag must be boolean')
                    if arguments[1]: code=code.lower()
                return struct.unpack('<'+code, memory.read(address(arguments[0]),struct.calcsize(code)))[0]
            if name == 'write'+suffix:
                if suffix == 'Pointer':
                    break
                if suffix in {'Integer','SmallInteger','Qword'}:
                    size=struct.calcsize(code); value=arguments[1]
                    if type(value) is not int or not -(1<<(size*8-1))<=value<(1<<(size*8)):
                        raise LuaHostError('Integer write is outside its byte width')
                    return self._mutate(address(arguments[0]),(value&((1<<(size*8))-1)).to_bytes(size,'little'),syntaxcheck)
                return self._mutate(address(arguments[0]),struct.pack('<'+code,arguments[1]),syntaxcheck)
        if name in {'readString','writeString'}:
            wide=arguments[2] if len(arguments)>2 else False
            if type(wide) is not bool: raise LuaHostError('String wide flag must be boolean')
            import sys
            encoding='utf-16-le' if wide else ('mbcs' if sys.platform=='win32' else 'cp1252')
            if name=='writeString':
                if not isinstance(arguments[1],str): raise LuaHostError('writeString text must be a string')
                raw=arguments[1].encode(encoding)
                if not 1<=len(raw)<=65536: raise LuaHostError('String write byte count is outside its bound')
                return self._mutate(address(arguments[0]),raw,syntaxcheck)
            count=arguments[1]
            if type(count) is not int or not 1<=count<=32768:
                raise LuaHostError('readString character count is outside 1..32768')
            start=address(arguments[0]); unit=2 if wide else 1; raw=bytearray()
            for index in range(count):
                if index % 64 == 0: broker_checkpoint()
                char=memory.read(start+index*unit,unit)
                if char==bytes(unit): break
                raw.extend(char)
            return raw.decode(encoding)
        if name == 'readBytes':
            count=arguments[1]
            if type(count) is not int or not 1 <= count <= 65536:
                raise LuaHostError('readBytes count is outside 1..65536')
            return list(memory.read(address(arguments[0]),count))
        if name == 'writeBytes':
            values=arguments[1]
            if not isinstance(values,list) or not values or len(values)>65536 or any(type(v) is not int or not 0<=v<=255 for v in values):
                raise LuaHostError('writeBytes requires bounded byte values')
            return self._mutate(address(arguments[0]),bytes(values),syntaxcheck)
        if name == 'fullAccess':
            # CE contract: page protection upgrade reported as a plain
            # boolean. The profile's memory is always writable, so a valid
            # bounded range answers true; a failing range check answers
            # false instead of raising (VirtualProtectEx failure in CE).
            if len(arguments)!=2:
                raise LuaHostError('fullAccess requires exactly two arguments (address, size)')
            size=arguments[1]
            if type(size) is not int or not 1<=size<=4*1024*1024:
                raise LuaHostError('fullAccess size is outside 1..4 MiB')
            start=arguments[0]
            if type(start) is not int:
                start=address(start)
            try:
                memory._range(start,size)
            except Exception:
                return False
            return True
        if name == 'AOBScan':
            if not 1<=len(arguments)<=4: raise LuaHostError('AOBScan requires a pattern and up to three options')
            pattern=arguments[0]
            if isinstance(pattern,str): pattern=pattern.replace('*','?')
            options=list(arguments[1:])+[None]*3
            matches=memory.scan_matches(pattern,protection=options[0] or '',alignment_type=options[1] or 0,alignment_parameter=options[2])
            return [format(value,'X') for value in matches]
        if name == 'scan.firstScan':
            if len(arguments)!=14:
                raise LuaHostError('firstScan requires the documented fourteen arguments')
            option,kind,rounding,pattern,second,start,end,protection,alignment,param,ishex,notbinary,unicode,casesensitive=arguments
            if isinstance(pattern,str): pattern=pattern.replace('*','?')
            # CE maps a nil rounding argument through lua_tointeger to 0
            # (rtRounded); accept the nil and the rounded constant, and keep
            # the exact byte-array option gate fail-closed.
            if rounding not in (None,0,'rtRounded'):
                raise LuaHostError('Unsupported scan rounding type: '+str(rounding))
            if (option,kind)!=('soExactValue',8):
                raise LuaHostError('This scan profile supports exact byte arrays with symbolic API constants')
            if second is not None or ishex is not True or any(v is not False for v in (notbinary,unicode,casesensitive)):
                raise LuaHostError('Unsupported exact byte-array scan options')
            start=address(start)
            if type(end) is int:
                if not start<=end<(1<<(memory.pointer_size*8)):
                    raise LuaHostError('Scan stop address is outside the target pointer width')
            else:
                end=address(end)
            # The CE-facing stop is inclusive; the backend range is half-open.
            end+=1
            matches=memory.scan_matches(pattern,start=start,end=end,protection=protection,alignment_type=alignment,alignment_parameter=param)
            return [format(value,'X') for value in matches]
        if name == 'addresslist.Count':
            return len(e.entries)
        if name == 'addresslist.at':
            index=arguments[0]
            if type(index) is not int or not 0<=index<len(e.entries):
                raise LuaHostError('MemoryRecord index is out of bounds')
            return list(e.entries)[index]
        if name.startswith('addresslist.getMemoryRecordBy'):
            value=arguments[0]
            matches=[i for i,entry in e.entries.items() if (i==value if name.endswith('ID') else entry['label']==value)]
            if not matches:
                return None
            if len(matches)!=1:
                raise LuaHostError('MemoryRecord lookup is ambiguous')
            return matches[0]
        if name == 'record.get':
            identifier,key=arguments
            entry=e.entries[identifier]
            if key in {'ID','Description','Address'}:
                return {'ID':identifier,'Description':entry['label'],'Address':entry.get('source_address',entry.get('address',''))}[key]
            if key=='Type':
                if entry['kind']=='script': return 11
                values={'Byte':0,'2 Bytes':1,'4 Bytes':2,'8 Bytes':3,'Float':4,'Double':5,
                        'String':6,'Array of byte':8,'Binary':9,'Custom':13}
                kind=entry.get('variable_type')
                if kind not in values: raise LuaHostError('MemoryRecord has no admitted value-type enum')
                return values[kind]
            if key=='Active':
                self._confirm_patches()
                if identifier in e.frozen:
                    addr,raw=e.frozen[identifier]
                    matched = (e._frozen_matches(identifier,addr,raw) if callable(getattr(e,'_frozen_matches',None))
                               else memory.read(addr,len(raw))==raw)
                    if not matched:
                        raise LuaHostError('Frozen MemoryRecord value changed before confirmation')
                return identifier in e.applied or identifier in e.frozen
            if key=='Value': return e.read_value(identifier)
            if key=='Count': return sum(x.get('parent_id')==identifier for x in e.entries.values())
            raise LuaHostError('Unsupported MemoryRecord property: '+str(key))
        if name == 'record.set':
            identifier,key,value=arguments
            if syntaxcheck:
                raise LuaHostError('Syntax checking cannot mutate MemoryRecords')
            if key=='Active' and type(value) is bool:
                entry=e.entries[identifier]
                return e.toggle(identifier,value) if entry['kind']=='script' else e.set_freeze(identifier,value)
            if key=='Value': return e.set_value(identifier,str(value))
            raise LuaHostError('Unsupported MemoryRecord mutation: '+str(key))
        if name == 'autoAssemble':
            if self.assembler_handler is None:
                raise LuaHostError('This activation has no native assembler broker')
            self._confirm_patches()
            return self.assembler_handler(*arguments,syntaxcheck=syntaxcheck)
        if name in {'registerSymbol','unregisterSymbol'}:
            if syntaxcheck or self.mutation_handler is None:
                raise LuaHostError('Symbol mutation requires an owned live activation')
            self._confirm_patches()
            return self.mutation_handler(name,arguments)
        if name in {'print','showMessage'}:
            text=' '.join(str(v) for v in arguments)
            if len(text)>10000: raise LuaHostError('Message exceeds its bound')
            if self.message_handler: self.message_handler(text)
            return None
        if name in {'isKeyPressed','getXBox360ControllerState'} and self.input_handler:
            return self.input_handler(name,arguments)
        if name in {'speedhack_setSpeed', 'speedhack_getSpeed'}:
            # N-16 corpus speed surface: the engine owns one tested Clock v2
            # binding per confirmed attach. Refusals are named (binding
            # exceptions) and effect-free; a missing binding is a visible
            # refusal, never a silent pass-through.
            from .clock_binding import ClockNotAttached
            clock = e.clock
            if clock is None:
                raise ClockNotAttached('Clock speed control requires an attached target session')
            if name == 'speedhack_getSpeed':
                if arguments:
                    raise LuaHostError('speedhack_getSpeed takes no arguments')
                return clock.get_speed()
            if len(arguments) != 1:
                raise LuaHostError('speedhack_setSpeed takes exactly one multiplier')
            if syntaxcheck:
                raise LuaHostError('Speed control requires a live activation')
            return clock.set_speed(arguments[0])
        raise LuaHostError('Unsupported CE Lua API: '+name)

    def _mutate(self, address: int, data: bytes, syntaxcheck: bool) -> bool:
        if syntaxcheck or self.mutation_handler is None:
            raise LuaHostError('Memory mutation requires an owned live activation')
        self._confirm_patches()
        return self.mutation_handler('write',(address,data))

    def _confirm_patches(self) -> None:
        try:
            self.engine._check_patches()
        except Exception as exc:
            self.engine._block(exc)
            raise LuaHostError('Controller patch confirmation failed: '+str(exc)) from exc


class TableLuaBroker:
    """Per-table bootstrap scope broker (WP-41): read-only by classification.

    Wraps the standard ``EngineLuaBroker`` dispatch (built without any
    mutation/assembler/message handlers) and applies the table-Lua read
    allowlist extracted from that dispatch: admitted read names are
    forwarded to the wrapped broker, every other call is refused with its
    exact WP-41 named reason, recorded in encounter order (bounded), and
    answered with nil so the table source keeps running its read-only
    code. The scope is generation-zero and retires through
    ``invalidate()`` with the wrapped dispatch.
    """

    def __init__(self, engine: Any):
        from .lua_bootstrap import (MAX_TABLE_LUA_REASONS,
                                    TABLE_LUA_READ_ONLY_NAMES,
                                    table_lua_refusal_reason)
        self.inner = EngineLuaBroker(engine)
        self._reads = TABLE_LUA_READ_ONLY_NAMES
        self._refusal_reason = table_lua_refusal_reason
        self._max_reasons = MAX_TABLE_LUA_REASONS
        self.reasons: list[str] = []

    @property
    def generation(self) -> int:
        return self.inner.generation

    def invalidate(self) -> None:
        self.inner.invalidate()

    def call(self, name: str, arguments: tuple, *, generation: int,
             syntaxcheck: bool) -> Any:
        if name in self._reads:
            return self.inner.call(name, arguments,
                                   generation=self.inner.generation,
                                   syntaxcheck=syntaxcheck)
        reason = self._refusal_reason(name)
        if len(self.reasons) < self._max_reasons:
            self.reasons.append(reason)
        return None
