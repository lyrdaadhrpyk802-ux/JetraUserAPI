"""
Debug: send one message and print the raw hex response.
"""
import sys
import os
import asyncio
import struct

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.edit.edit_client import EditJetraClient
from jetrauserapi.high_level import SEND_MESSAGE_ID, INPUT_PEER_CHANNEL, RPC_ERROR
from jetrauserapi.client import wrap_init_connection
import random


async def main():
    print("=" * 60)
    print("DEBUG: sendMessage raw response")
    print("=" * 60)

    client = EditJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    print("Ready.\n")

    # Pick first group
    groups = await client.get_groups()
    if not groups:
        print("No groups.")
        await client.stop()
        return

    target = groups[0]
    peer_id = target['peer_id']
    access_hash = target['access_hash'] or 0
    print("Target: " + str(target['title']) + " peer_id=" + str(peer_id))

    input_peer = (
        struct.pack("<I", INPUT_PEER_CHANNEL) +
        struct.pack("<q", peer_id) +
        struct.pack("<q", access_hash)
    )

    random_id = random.getrandbits(63)
    text = "DEBUG-HEX test"
    body = (
        struct.pack("<I", SEND_MESSAGE_ID) +
        struct.pack("<I", 0) +
        input_peer +
        client._tl_string(text) +
        struct.pack("<q", random_id)
    )

    print("\nSending...")
    result = await client.client.send_request(
        wrap_init_connection(body)
    )
    print("Got result, len=" + str(len(result) if result else 0))

    if not result:
        print("No result.")
        await client.stop()
        return

    print("\nBefore gzip unwrap:")
    print(result.hex())

    result2 = client._unwrap_gzip(result)
    print("\nAfter gzip unwrap, len=" + str(len(result2)))
    print(result2.hex())

    ctor = struct.unpack("<I", result2[:4])[0]
    print("\nTop-level ctor: " + hex(ctor))

    if ctor == RPC_ERROR:
        print("RPC_ERROR: " + client._parse_rpc_error(result2))
        await client.stop()
        return

    # Try to find Message ctor inside
    MSG_CTOR = 0x7600B9D3
    needle = struct.pack("<I", MSG_CTOR)
    pos = result2.find(needle)
    print("\nMessage ctor 0x7600B9D3 found at offset: " + str(pos))

    if pos >= 0:
        print("Bytes around Message ctor:")
        start = max(0, pos - 16)
        end = min(len(result2), pos + 80)
        print(result2[start:end].hex())
        print("\nOffset breakdown:")
        for i in range(start, end, 16):
            chunk = result2[i:min(i + 16, end)]
            hex_part = chunk.hex()
            ascii_part = ''.join(
                chr(b) if 32 <= b < 127 else '.'
                for b in chunk
            )
            print("  " + format(i, '04x') + "  " +
                  hex_part.ljust(32) + "  " + ascii_part)

    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
