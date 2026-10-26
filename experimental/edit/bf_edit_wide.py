"""
Wide brute-force scan for messages.editMessage ctor ID.

Scans a 4096-ID block around sendMessage (0xFEF48F62).
Adds a small delay to avoid rate limits.

Usage:
    cd /storage/emulated/0/JetraUserAPI
    python experimental/edit/bf_edit_wide.py
"""
import sys
import os
import asyncio
import struct
import random

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.edit.edit_client import EditJetraClient
from experimental.edit.send_parser import parse_sent_message
from jetrauserapi.high_level import (
    INPUT_PEER_CHANNEL,
    RPC_ERROR,
)
from jetrauserapi.client import wrap_init_connection


# We scan around 0xFEF48F62 (sendMessage)
RANGE_START = 0xFEF48000
RANGE_END   = 0xFEF49000
DELAY = 0.1  # 100ms delay between requests


async def send_test_message(client, peer_id, access_hash):
    input_peer = (
        struct.pack("<I", INPUT_PEER_CHANNEL) +
        struct.pack("<q", peer_id) +
        struct.pack("<q", access_hash)
    )

    random_id = random.getrandbits(63)
    body = (
        struct.pack("<I", 0xFEF48F62) +  # sendMessage
        struct.pack("<I", 0) +
        input_peer +
        client._tl_string("WIDE-SCAN test") +
        struct.pack("<q", random_id)
    )

    result = await client.client.send_request(wrap_init_connection(body))
    if not result:
        return None

    result = client._unwrap_gzip(result)
    ctor = struct.unpack("<I", result[:4])[0]
    if ctor == RPC_ERROR:
        print("  sendMessage failed: " + client._parse_rpc_error(result))
        return None

    parsed = parse_sent_message(result)
    if parsed:
        return parsed['msg_id']
    return None


async def try_edit(client, peer_id, access_hash, msg_id, ctor_id):
    input_peer = (
        struct.pack("<I", INPUT_PEER_CHANNEL) +
        struct.pack("<q", peer_id) +
        struct.pack("<q", access_hash)
    )

    flags = 0x1
    random_id = random.getrandbits(63)
    body = (
        struct.pack("<I", ctor_id) +
        struct.pack("<I", flags) +
        input_peer +
        struct.pack("<i", msg_id) +
        client._tl_string("WIDE-SCAN " + hex(ctor_id)) +
        struct.pack("<q", random_id)
    )

    try:
        result = await client.client.send_request(wrap_init_connection(body))
        if not result:
            return ('NO_RESPONSE', None)

        result = client._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]

        if resp_ctor == RPC_ERROR:
            err = client._parse_rpc_error(result)
            if err == "NOT_IMPLEMENTED":
                return ('NOT_IMPLEMENTED', err)
            return ('OTHER_ERROR:' + err, err)

        return ('SUCCESS', hex(resp_ctor))

    except Exception as e:
        return ('EXCEPTION:' + str(e), str(e))


async def main():
    print("=" * 60)
    print("Wide Brute-Force editMessage")
    print("Range: " + hex(RANGE_START) + " -> " + hex(RANGE_END))
    print("Delay: " + str(DELAY) + "s")
    print("This may take about 7-8 minutes.")
    print("=" * 60)

    client = EditJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    print("Client ready.\n")

    groups = await client.get_groups()
    if not groups:
        print("No groups available.")
        await client.stop()
        return

    target = groups[0]
    peer_id = target['peer_id']
    access_hash = target['access_hash'] or 0
    print("Target group: " + str(target['title']) + " (peer_id=" + str(peer_id) + ")")

    print("\n[1] Sending test message...")
    msg_id = await send_test_message(client, peer_id, access_hash)
    if not msg_id:
        print("    Could not send test message.")
        await client.stop()
        return
    print("    Got msg_id=" + str(msg_id))
    await asyncio.sleep(1)

    print("\n[2] Scanning ctor IDs...")
    
    success_ids = []
    interesting_ids = []
    
    total = RANGE_END - RANGE_START
    count = 0

    for ctor_id in range(RANGE_START, RANGE_END):
        count += 1
        if count % 100 == 0:
            print("    Progress: " + str(count) + "/" + str(total) + "...")

        status, detail = await try_edit(client, peer_id, access_hash, msg_id, ctor_id)

        if status == 'SUCCESS':
            print("\n    [FOUND] " + hex(ctor_id) + " -> SUCCESS\n")
            success_ids.append(ctor_id)
            break # Stop on first success
        elif status == 'NOT_IMPLEMENTED':
            pass # Normal, keep going silently
        else:
            # We found something that is NOT "NOT_IMPLEMENTED" (e.g. INPUT_REQUEST_INVALID)
            print("\n    [INTERESTING] " + hex(ctor_id) + " -> " + status + "\n")
            interesting_ids.append((ctor_id, status))
            # Don't break, but log it

        await asyncio.sleep(DELAY)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    if success_ids:
        print("  WORKING ctor id: " + hex(success_ids[0]))
        print("  You can now stop and use this ID.")
    else:
        print("  No SUCCESS ctor id found.")

    if interesting_ids:
        print("\n  Interesting ctor ids (Not NOT_IMPLEMENTED):")
        for cid, status in interesting_ids:
            print("    " + hex(cid) + "  -> " + status)
        print("\n  If you see INPUT_REQUEST_INVALID, we found the method")
        print("  but the arguments are wrong.")
    else:
        print("\n  All IDs returned NOT_IMPLEMENTED.")

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
