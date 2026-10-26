"""
Smart test for kick methods using a dummy user ID (no one gets hurt).
Tries different chat_id formats (positive, negative, -100 prefix).
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
from jetrauserapi.high_level import RPC_ERROR
from jetrauserapi.client import wrap_init_connection

# Define constants directly
INPUT_USER = 0xD8292816

DUMMY_USER_ID = 123456789
DUMMY_ACCESS_HASH = 0
DELETE_CHAT_USER_ID = 0xA2185CAB

async def try_delete_chat_user(client, chat_id, user_id, user_hash):
    # Build InputUser for dummy user
    input_user = (
        struct.pack("<I", INPUT_USER) +
        struct.pack("<q", user_id) +
        struct.pack("<q", user_hash)
    )
    
    # Structure: ctor, flags, chat_id(int32), user_id(InputUser)
    body = (
        struct.pack("<I", DELETE_CHAT_USER_ID) +
        struct.pack("<I", 0) + # flags=0
        struct.pack("<i", chat_id) +
        input_user
    )
    
    try:
        result = await client.client.send_request(wrap_init_connection(body))
        if not result: return ('NO_RESPONSE', None)
        
        result = client._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        
        if resp_ctor == RPC_ERROR:
            err = client._parse_rpc_error(result)
            return ('RPC_ERROR', err)
            
        return ('SUCCESS', hex(resp_ctor))
    except Exception as e:
        return ('EXCEPTION', str(e))

async def main():
    print("=" * 60)
    print("Smart Kick Test (Dummy User)")
    print("=" * 60)
    
    client = BanJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    
    groups = await client.get_groups()
    if not groups:
        print("No groups found.")
        await client.stop()
        return
        
    target = groups[0]
    channel_id = target['peer_id']
    print(f"Target group: {target['title']} (raw_id={channel_id})")
    print(f"Using DUMMY_USER_ID = {DUMMY_USER_ID} (safe, no one will be kicked)\n")
    
    # Test different chat_id formats
    chat_ids_to_test = [
        channel_id,          # Positive (e.g., 2017)
        -channel_id,         # Negative (e.g., -2017)
        -1000000000000 - channel_id, # Telegram supergroup format
    ]
    
    for cid in chat_ids_to_test:
        print(f"Testing chat_id = {cid}...")
        status, detail = await try_delete_chat_user(
            client, cid, DUMMY_USER_ID, DUMMY_ACCESS_HASH
        )
        
        if status == 'SUCCESS':
            print(f"  [SUCCESS] Worked with chat_id={cid}!")
            break
        elif status == 'RPC_ERROR':
            if "USER_NOT_PARTICIPANT" in detail:
                print(f"  [JACKPOT!] Structure is CORRECT. Server says: {detail}")
                print(f"  We just need to use a real user ID to kick them.")
                break
            elif "INPUT_REQUEST_INVALID" in detail:
                print(f"  [FAIL] Invalid structure (chat_id={cid})")
            else:
                print(f"  [OTHER ERROR] {detail}")
        else:
            print(f"  [{status}] {detail}")
            
        await asyncio.sleep(1)

    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
