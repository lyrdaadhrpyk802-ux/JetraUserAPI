"""
Try all possible payload structures for messages.deleteChatUser (0xA2185CAB)
using a DUMMY user ID (safe, no real users will be kicked).
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
INPUT_PEER_CHAT = 0x35A95CB9

DUMMY_USER_ID = 123456789
DUMMY_ACCESS_HASH = 0

async def test_payload(client, channel_id, channel_hash, chat_type, user_type, flags):
    # Build chat bytes
    if chat_type == "int32":
        chat_bytes = struct.pack("<i", channel_id)
    elif chat_type == "input_channel":
        chat_bytes = struct.pack("<I", INPUT_CHANNEL) + struct.pack("<q", channel_id) + struct.pack("<q", channel_hash)
    elif chat_type == "input_peer_channel":
        chat_bytes = struct.pack("<I", INPUT_PEER_CHANNEL) + struct.pack("<q", channel_id) + struct.pack("<q", channel_hash)
    elif chat_type == "input_peer_chat":
        chat_bytes = struct.pack("<I", INPUT_PEER_CHAT) + struct.pack("<q", channel_id)

    # Build user bytes
    if user_type == "input_user":
        user_bytes = struct.pack("<I", INPUT_USER) + struct.pack("<q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)
    elif user_type == "input_peer_user":
        user_bytes = struct.pack("<I", INPUT_PEER_USER) + struct.pack("<Q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)
    elif user_type == "int64":
        user_bytes = struct.pack("<q", DUMMY_USER_ID)
    elif user_type == "int32":
        user_bytes = struct.pack("<i", DUMMY_USER_ID)

    # Structure: ctor, flags, chat, user
    body = struct.pack("<I", DELETE_CHAT_USER_ID) + struct.pack("<I", flags) + chat_bytes + user_bytes
    
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
    print("Payload Discovery for deleteChatUser (Safe)")
    print("=" * 60)
    
    client = BanJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    
    groups = await client.get_groups()
    target = groups[0]
    channel_id = target['peer_id']
    channel_hash = target['access_hash']
    print(f"Target group: {target['title']} ({channel_id})")
    print(f"Using DUMMY_USER_ID = {DUMMY_USER_ID}\n")
    
    chat_types = ["int32", "input_channel", "input_peer_channel", "input_peer_chat"]
    user_types = ["input_user", "input_peer_user", "int64", "int32"]
    flags_list = [0, 1]
    
    for ct in chat_types:
        for ut in user_types:
            for flags in flags_list:
                print(f"Testing chat={ct}, user={ut}, flags={flags}...", end=" ")
                status, detail = await test_payload(client, channel_id, channel_hash, ct, ut, flags)
                
                if status == 'SUCCESS':
                    print(f"\n[JACKPOT!] Worked! (chat={ct}, user={ut}, flags={flags})")
                    await client.stop()
                    return
                elif status == 'RPC_ERROR':
                    if "USER_NOT_PARTICIPANT" in detail:
                        print(f"\n[JACKPOT!] Structure is CORRECT! Server: {detail}")
                        print(f"--> Use chat={ct}, user={ut}, flags={flags}")
                        await client.stop()
                        return
                    elif "INPUT_REQUEST_INVALID" in detail:
                        print("FAIL (invalid)")
                    else:
                        print(f"OTHER: {detail}")
                else:
                    print(f"[{status}] {detail}")
                    
                await asyncio.sleep(0.5)

    print("\nNo structure worked. Method is likely locked.")
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
