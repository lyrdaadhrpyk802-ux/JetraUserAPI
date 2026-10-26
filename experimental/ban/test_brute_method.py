"""
Targeted Brute-force for deleteChatUser method ID.
Scans 256 IDs around the standard 0xA2185CAB.
For each ID, tries 3 most likely payloads.
Uses DUMMY_USER_ID (safe).
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
from experimental.ban.ban_client import BanJetraClient
from jetrauserapi.high_level import (
    RPC_ERROR, INPUT_CHANNEL, INPUT_PEER_CHANNEL, INPUT_PEER_USER
)
from jetrauserapi.client import wrap_init_connection

INPUT_USER = 0xD8292816
DUMMY_USER_ID = 123456789
DUMMY_ACCESS_HASH = 0

# Scan around standard deleteChatUser ID
RANGE_START = 0xA2185C00
RANGE_END   = 0xA2185D00

async def test_method_id(client, ctor_id, channel_id, channel_hash, variant):
    if variant == "int32":
        chat_bytes = struct.pack("<i", channel_id)
    elif variant == "input_peer_channel":
        chat_bytes = struct.pack("<I", INPUT_PEER_CHANNEL) + struct.pack("<q", channel_id) + struct.pack("<q", channel_hash)
    elif variant == "input_channel":
        chat_bytes = struct.pack("<I", INPUT_CHANNEL) + struct.pack("<q", channel_id) + struct.pack("<q", channel_hash)

    user_bytes = struct.pack("<I", INPUT_USER) + struct.pack("<q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)

    # Structure: ctor, flags=0, chat, user
    body = struct.pack("<I", ctor_id) + struct.pack("<I", 0) + chat_bytes + user_bytes
    
    try:
        result = await client.client.send_request(wrap_init_connection(body))
        if not result: return ('NO_RESPONSE', None)
        result = client._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        
        if resp_ctor == RPC_ERROR:
            return ('RPC_ERROR', client._parse_rpc_error(result))
            
        return ('SUCCESS', hex(resp_ctor))
    except Exception as e:
        return ('EXCEPTION', str(e))

async def main():
    print("=" * 60)
    print("Targeted Brute-force deleteChatUser")
    print(f"Range: {hex(RANGE_START)} -> {hex(RANGE_END)}")
    print("=" * 60)
    
    client = BanJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    
    groups = await client.get_groups()
    target = groups[0]
    channel_id = target['peer_id']
    channel_hash = target['access_hash']
    print(f"Target group: {target['title']} ({channel_id})")
    print(f"Using DUMMY_USER_ID = {DUMMY_USER_ID}\n")
    
    variants = ["int32", "input_peer_channel", "input_channel"]
    
    for ctor_id in range(RANGE_START, RANGE_END):
        label = format(ctor_id, '#010x')
        
        for v in variants:
            status, detail = await test_method_id(client, ctor_id, channel_id, channel_hash, v)
            
            if status == 'SUCCESS':
                print(f"\n[JACKPOT!] Worked! ctor={label}, variant={v}")
                await client.stop()
                return
            elif status == 'RPC_ERROR':
                if "USER_NOT_PARTICIPANT" in detail:
                    print(f"\n[JACKPOT!] Method ID found! ctor={label}, variant={v} -> {detail}")
                    await client.stop()
                    return
                elif "INPUT_REQUEST_INVALID" in detail:
                    # Usually means correct method ID but wrong payload
                    if v == "int32":
                        print(f"[INFO] {label} recognized as method! (Invalid payload though)")
                else:
                    print(f"[OTHER] {label} ({v}): {detail}")
            
            await asyncio.sleep(0.1)

    print("\nScan complete. No luck.")
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())