"""
Test messages.deleteChatUser with STANDARD Telegram InputUser (0xF21158C6).
Uses a DUMMY_USER_ID (safe).
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
from jetrauserapi.high_level import RPC_ERROR, INPUT_PEER_CHANNEL
from jetrauserapi.client import wrap_init_connection

DELETE_CHAT_USER_ID = 0xA2185CAB
INPUT_USER_STD = 0xF21158C6
INPUT_USER_EMPTY = 0xB98886CF

DUMMY_USER_ID = 123456789
DUMMY_ACCESS_HASH = 0

async def test_payload(client, channel_id, channel_hash, payload_type):
    if payload_type == "int32_int_user":
        # chat_id:int32, user_id:InputUser
        chat_bytes = struct.pack("<i", channel_id)
        user_bytes = struct.pack("<I", INPUT_USER_STD) + struct.pack("<q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)
    elif payload_type == "long_int_user":
        # chat_id:long, user_id:InputUser
        chat_bytes = struct.pack("<q", channel_id)
        user_bytes = struct.pack("<I", INPUT_USER_STD) + struct.pack("<q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)
    elif payload_type == "int32_empty_user":
        # chat_id:int32, user_id:InputUserEmpty
        chat_bytes = struct.pack("<i", channel_id)
        user_bytes = struct.pack("<I", INPUT_USER_EMPTY)
    elif payload_type == "peer_channel_int_user":
        # chat:InputPeerChannel, user_id:InputUser
        chat_bytes = struct.pack("<I", INPUT_PEER_CHANNEL) + struct.pack("<q", channel_id) + struct.pack("<q", channel_hash)
        user_bytes = struct.pack("<I", INPUT_USER_STD) + struct.pack("<q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)

    # Structure: ctor, flags=0, chat, user
    body = struct.pack("<I", DELETE_CHAT_USER_ID) + struct.pack("<I", 0) + chat_bytes + user_bytes
    
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
    print("Standard InputUser Kick Test (Safe)")
    print("=" * 60)
    
    client = BanJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    
    groups = await client.get_groups()
    target = groups[0]
    channel_id = target['peer_id']
    channel_hash = target['access_hash']
    print(f"Target group: {target['title']} ({channel_id})")
    print(f"Using DUMMY_USER_ID = {DUMMY_USER_ID}\n")
    
    payload_types = [
        "int32_int_user",
        "long_int_user",
        "int32_empty_user",
        "peer_channel_int_user"
    ]
    
    for pt in payload_types:
        print(f"Testing payload={pt}...", end=" ")
        status, detail = await test_payload(client, channel_id, channel_hash, pt)
        
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
                print("FAIL (invalid)")
            else:
                print(f"OTHER: {detail}")
        else:
            print(f"[{status}] {detail}")
            
        await asyncio.sleep(1)

    print("\nStandard InputUser failed too.")
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
