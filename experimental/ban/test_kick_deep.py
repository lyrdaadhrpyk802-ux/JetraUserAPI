"""
Deep test for messages.deleteChatUser.
Tests flags, long chat_id, and -100 prefix.
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
from jetrauserapi.high_level import RPC_ERROR, INPUT_PEER_USER
from jetrauserapi.client import wrap_init_connection

INPUT_USER = 0xD8292816
DUMMY_USER_ID = 123456789
DUMMY_ACCESS_HASH = 0
DELETE_CHAT_USER_ID = 0xA2185CAB

async def try_delete_chat_user(client, chat_id, user_id, user_hash, flags, user_format):
    # Build InputUser
    if user_format == "input_user":
        user_bytes = (
            struct.pack("<I", INPUT_USER) +
            struct.pack("<q", user_id) +
            struct.pack("<q", user_hash)
        )
    else:
        user_bytes = (
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", user_hash)
        )
    
    # Structure: ctor, flags, chat_id(long), user_id
    body = (
        struct.pack("<I", DELETE_CHAT_USER_ID) +
        struct.pack("<I", flags) +
        struct.pack("<q", chat_id) +  # Use long for chat_id
        user_bytes
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
    print("Deep Kick Test (Dummy User)")
    print("=" * 60)
    
    client = BanJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    
    groups = await client.get_groups()
    if not groups:
        print("No groups found.")
        await client.stop()
        return
        
    target = groups[0]
    raw_id = target['peer_id']
    print(f"Target group: {target['title']} (raw_id={raw_id})\n")
    
    # Test combinations
    chat_ids = [
        raw_id,
        -raw_id,
        -1000000000000 - raw_id
    ]
    flags_list = [0, 1] # 0 = normal, 1 = revoke_history
    
    for cid in chat_ids:
        for flags in flags_list:
            for uf in ["input_user", "input_peer_user"]:
                print(f"Testing chat_id={cid}, flags={flags}, user={uf}...")
                status, detail = await try_delete_chat_user(
                    client, cid, DUMMY_USER_ID, DUMMY_ACCESS_HASH, flags, uf
                )
                
                if status == 'SUCCESS':
                    print(f"  [SUCCESS] Worked!")
                    await client.stop()
                    return
                elif status == 'RPC_ERROR':
                    if "USER_NOT_PARTICIPANT" in detail:
                        print(f"  [JACKPOT!] Structure is CORRECT. Server: {detail}")
                        await client.stop()
                        return
                    elif "INPUT_REQUEST_INVALID" in detail:
                        print(f"  [FAIL] Invalid structure")
                    else:
                        print(f"  [OTHER ERROR] {detail}")
                else:
                    print(f"  [{status}] {detail}")
                    
                await asyncio.sleep(1)

    print("\nAll combinations failed.")
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
