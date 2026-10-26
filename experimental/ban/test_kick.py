"""
Test alternative kick methods: messages.deleteChatUser
Fixing binary layout (int32 vs int64 vs InputPeer).
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
    RPC_ERROR, INPUT_PEER_CHANNEL, INPUT_CHANNEL
)
from jetrauserapi.client import wrap_init_connection

DELETE_CHAT_USER_ID = 0xA2185CAB

async def try_kick(client, channel_id, channel_hash, user_id, user_hash, variant):
    input_user = (
        struct.pack("<I", 0xD8292816) + # InputUser
        struct.pack("<q", user_id) +
        struct.pack("<q", user_hash)
    )
    
    if variant == "int32":
        chat_bytes = struct.pack("<i", channel_id)
    elif variant == "int64":
        chat_bytes = struct.pack("<q", channel_id)
    elif variant == "input_peer":
        chat_bytes = (
            struct.pack("<I", INPUT_PEER_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", channel_hash)
        )
    
    # messages.deleteChatUser#a2185cab flags:# revoke_history:flags.0?true chat_id:int user_id:InputUser
    body = (
        struct.pack("<I", DELETE_CHAT_USER_ID) +
        struct.pack("<I", 0) + # flags
        chat_bytes +
        input_user
    )
    
    try:
        result = await client.client.send_request(wrap_init_connection(body))
        if not result: return ('NO_RESPONSE', None)
        
        result = client._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        
        if resp_ctor == RPC_ERROR:
            err = client._parse_rpc_error(result)
            return ('ERROR', err)
            
        return ('SUCCESS', hex(resp_ctor))
    except Exception as e:
        return ('EXCEPTION', str(e))

async def main():
    print("=" * 60)
    print("Smart Kick Test (Variants)")
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
    channel_hash = target['access_hash']
    print(f"Target group: {target['title']} ({channel_id})")
    
    users = await client.get_participants_with_hash(channel_id)
    test_user = None
    for u in users:
        if u['id'] != client.session.user_id:
            test_user = u
            break
            
    if not test_user:
        print("No other user to kick.")
        await client.stop()
        return

    print(f"Attempting to kick user {test_user['id']}...\n")
    
    variants = ["int32", "int64", "input_peer"]
    
    for v in variants:
        print(f"Testing variant: {v}...")
        status, detail = await try_kick(
            client, channel_id, channel_hash, test_user['id'], test_user['access_hash'], v
        )
        
        if status == 'SUCCESS':
            print(f"  [SUCCESS] Kicked successfully with variant {v}!")
            break
        else:
            print(f"  [{status}] {detail}")
            
        await asyncio.sleep(1)

    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())