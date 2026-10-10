"""Owned owner-death gate. It deliberately leaves no automatic recovery claim."""
import argparse
import json
import os
import sys
from ct2trainer.native.target_broker import CallContext, Operation, OwnedFixture

parser = argparse.ArgumentParser()
parser.add_argument("--build-report", required=True)
parser.add_argument("--architecture", choices=("x86", "x64"), required=True)
parser.add_argument("--receipt-directory", required=True)
args = parser.parse_args()
fixture = OwnedFixture(args.build_report, args.architecture, args.receipt_directory)
reply = fixture.broker.submit(Operation.CDECL_ADD, (40, 2), CallContext.seconds(3), hold_start=True)
print(json.dumps({"target": fixture.target, "owner": fixture.windows.owner, "request_id": reply.request_id}))
sys.stdout.flush()
# Target buffers/code/ledger remain its own. Target notices the exact owner
# handle signal, cancels PREPARED itself and exits its owned host input loop.
os._exit(0)
