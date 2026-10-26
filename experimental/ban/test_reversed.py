"""
Test reversed field order and mixed structures for messages.deleteChatUser.
Using DUMMY_USER_ID = 123456789 (safe).
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

DELETE_CHAT_USER_ID = 0xA2185CAB
INPUT_USER = 0xD8292816

DUMMY_USER_ID = 123456789
DUMMY_ACCESS_HASH = 0

async def try_payload(client, channel_id, channel_hash, order, chat_type, user_type):
    # Build components
    if chat_type == "int32":
        chat_bytes = struct.pack("<i", channel_id)
    elif chat_type == "int64":
        chat_bytes = struct.pack("<q", channel_id)
    elif chat_type == "input_channel":
        chat_bytes = struct.pack("<I", INPUT_CHANNEL) + struct.pack("<q", channel_id) + struct.pack("<q", channel_hash)
    elif chat_type == "input_peer_channel":
        chat_bytes = struct.pack("<I", INPUT_PEER_CHANNEL) + struct.pack("<q", channel_id) + struct.pack("<q", channel_hash)
    elif chat_type == "input_peer_chat":
        chat_bytes = struct.pack("<I", 0x35A95CB9) + struct.pack("<q", channel_id)

    if user_type == "input_user":
        user_bytes = struct.pack("<I", INPUT_USER) + struct.pack("<q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)
    elif user_type == "input_peer_user":
        user_bytes = struct.pack("<I", INPUT_PEER_USER) + struct.pack("<Q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)
    elif user_type == "int64":
        user_bytes = struct.pack("<q", DUMMY_USER_ID)
    elif user_type == "int32":
        user_bytes = struct.pack("<i", DUMMY_USER_ID)

    # Build payload based on order
    if order == "chat_first":
        payload = chat_bytes + user_bytes
    else: # user_first
        payload = user_bytes + chat_bytes

    # Structure: ctor, flags, [payload]
    body = struct.pack("<I", DELETE_CHAT_USER_ID) + struct.pack("<I", 0) + payload
    
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
    print("Reversed Payload Test (Safe)")
    print("=" * 60)
    
    client = BanJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    
    groups = await client.get_groups()
    target = groups[0]
    channel_id = target['peer_id']
    channel_hash = target['access_hash']
    print(f"Target group: {target['title']} ({channel_id})\n")
    
    orders = ["chat_first", "user_first"]
    chat_types = ["int32", "int64", "input_channel", "input_peer_channel", "input_peer_chat"]
    user_types = ["input_user", "input_peer_user", "int64", "int32"]
    
    for order in orders:
        for ct in chat_types:
            for ut in user_types:
                # Skip duplicate tested combos (chat_first with standard types)
                if order == "chat_first" and ct == "int32" and ut == "input_user":
                    continue # Already failed
                
                print(f"Testing order={order}, chat={ct}, user={ut}...", end=" ")
                status, detail = await try_payload(client, channel_id, channel_hash, order, ct, ut)
                
                if status == 'SUCCESS':
                    print(f"\n[JACKPOT!] Worked!")
                    await client.stop()
                    return
                elif status == 'RPC_ERROR':
                    if "USER_NOT_PARTICIPANT" in detail:
                        print(f"\n[JACKPOT!] Structure is CORRECT! Server: {detail}")
                        await client.stop()
                        return
                    elif "INPUT_REQUEST_INVALID" in detail:
                        print("FAIL")
                    else:
                        print(f"OTHER: {detail}")
                else:
                    print(f"[{status}]")
                    
                await asyncio.sleep(0.4)

    print("\nAll reversed orders failed too.")
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
