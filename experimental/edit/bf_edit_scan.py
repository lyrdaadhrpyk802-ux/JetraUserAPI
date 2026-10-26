"""
Brute-force messages.editMessage ctor ID over a small range
around sendMessage 0xFEF48F62.

Procedure:
  1. Send one message to a group, get its real msg_id.
  2. Try each ctor ID in the range, small delay between requests.
  3. On first non-NOT_IMPLEMENTED response, stop and report.

Usage:
    cd /storage/emulated/0/JetraUserAPI
    python experimental/edit/bf_edit_scan.py
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


# Range around sendMessage 0xFEF48F62
RANGE_START = 0xFEF48F60
RANGE_END = 0xFEF48F70

# Delay between requests (seconds) to avoid rate limiting
DELAY = 0.4


async def send_test_message(client, peer_id, access_hash):
    """Send a test message and return its real msg_id."""
    input_peer = (
        struct.pack("<I", INPUT_PEER_CHANNEL) +
        struct.pack("<q", peer_id) +
        struct.pack("<q", access_hash)
    )

    random_id = random.getrandbits(63)
    body = (
        struct.pack("<I", 0xFEF48F62) +     # sendMessage
        struct.pack("<I", 0) +
        input_peer +
        client._tl_string("BF-EDIT test") +
        struct.pack("<q", random_id)
    )

    result = await client.client.send_request(
        wrap_init_connection(body)
    )
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
    """
    Try one ctor ID for editMessage.
    Returns (status, response).
    """
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
        client._tl_string("BF-EDIT edited " + hex(ctor_id)) +
        struct.pack("<q", random_id)
    )

    try:
        result = await client.client.send_request(
            wrap_init_connection(body)
        )
        if not result:
            return ('NO_RESPONSE', None)

        result = client._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]

        if resp_ctor == RPC_ERROR:
            err = client._parse_rpc_error(result)
            if err == "NOT_IMPLEMENTED":
                return ('NOT_IMPLEMENTED', err)
            if err == "INPUT_REQUEST_INVALID":
                return ('INPUT_REQUEST_INVALID', err)
            return ('OTHER_ERROR:' + err, err)

        return ('SUCCESS', hex(resp_ctor))

    except Exception as e:
        return ('EXCEPTION:' + str(e), str(e))


async def main():
    print("=" * 60)
    print("Brute-force editMessage ctor ID")
    print("Range: " + hex(RANGE_START) + " -> " + hex(RANGE_END))
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
    print("Target group: " + str(target['title']) +
          " peer_id=" + str(peer_id))

    print("\n[1] Sending test message...")
    msg_id = await send_test_message(client, peer_id, access_hash)
    if not msg_id:
        print("    Could not send test message.")
        await client.stop()
        return
    print("    Got msg_id=" + str(msg_id))
    await asyncio.sleep(1)

    print("\n[2] Brute-forcing ctor IDs:")
    print("    (each line shows: ctor -> status)")
    print("    " + "-" * 56)

    success_ids = []
    interesting_ids = []

    for ctor_id in range(RANGE_START, RANGE_END + 1):
        status, detail = await try_edit(
            client, peer_id, access_hash, msg_id, ctor_id
        )

        label = format(ctor_id, '#010x')
        if status == 'SUCCESS':
            print("    " + label + "  -> SUCCESS")
            success_ids.append(ctor_id)
        elif status == 'NOT_IMPLEMENTED':
            print("    " + label + "  -> NOT_IMPLEMENTED")
        elif status == 'INPUT_REQUEST_INVALID':
            print("    " + label + "  -> INPUT_REQUEST_INVALID  <<<")
            interesting_ids.append((ctor_id, status))
        else:
            print("    " + label + "  -> " + status)
            interesting_ids.append((ctor_id, status))

        await asyncio.sleep(DELAY)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    if success_ids:
        print("  WORKING ctor ids:")
        for cid in success_ids:
            print("    " + hex(cid))
    else:
        print("  No working ctor id found in this range.")

    if interesting_ids:
        print("\n  Interesting ctor ids (not NOT_IMPLEMENTED):")
        for cid, status in interesting_ids:
            print("    " + hex(cid) + "  -> " + status)
    else:
        print("\n  All IDs returned NOT_IMPLEMENTED.")
        print("  Server likely rejects all unknown methods with "
              "NOT_IMPLEMENTED, so this brute-force method may not work.")
        print("  Next options:")
        print("    - Capture traffic from official app (mitmproxy)")
        print("    - Try wider ranges")

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
