"""
Matrix test for messages.deleteChatUser.
Tries all combinations of chat_id and user_id formats.
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
    RPC_ERROR, INPUT_PEER_CHANNEL, INPUT_CHANNEL, INPUT_PEER_USER
)
from jetrauserapi.client import wrap_init_connection

DELETE_CHAT_USER_ID = 0xA2185CAB

async def try_kick(client, channel_id, channel_hash, user_id, user_hash, chat_type, user_type):
    # Build chat bytes
    if chat_type == "int32":
        chat_bytes = struct.pack("<i", channel_id)
    elif chat_type == "int64":
        chat_bytes = struct.pack("<q", channel_id)
    elif chat_type == "input_channel":
        chat_bytes = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", channel_hash)
        )
    elif chat_type == "input_peer_channel":
        chat_bytes = (
            struct.pack("<I", INPUT_PEER_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", channel_hash)
        )

    # Build user bytes
    if user_type == "input_user":
        user_bytes = (
            struct.pack("<I", 0xD8292816) + # InputUser
            struct.pack("<q", user_id) +
            struct.pack("<q", user_hash)
        )
    elif user_type == "input_peer_user":
        user_bytes = (
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", user_hash)
        )
    elif user_type == "int64":
        user_bytes = struct.pack("<q", user_id)
    elif user_type == "int32":
        user_bytes = struct.pack("<i", user_id)

    # messages.deleteChatUser#a2185cab flags:# revoke_history:flags.0?true chat_id:int user_id:InputUser
    body = (
        struct.pack("<I", DELETE_CHAT_USER_ID) +
        struct.pack("<I", 0) + # flags
        chat_bytes +
        user_bytes
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
    print("Matrix Test for messages.deleteChatUser")
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
    
    chat_types = ["int32", "int64", "input_channel", "input_peer_channel"]
    user_types = ["input_user", "input_peer_user", "int64", "int32"]
    
    for ct in chat_types:
        for ut in user_types:
            print(f"Testing chat={ct}, user={ut}...")
            status, detail = await try_kick(
                client, channel_id, channel_hash, test_user['id'], test_user['access_hash'], ct, ut
            )
            
            if status == 'SUCCESS':
                print(f"  [SUCCESS] Kicked successfully with chat={ct}, user={ut}!")
                await client.stop()
                return
            elif status == 'ERROR':
                if detail == "INPUT_REQUEST_INVALID":
                    pass # Expected for wrong combos, keep trying
                else:
                    print(f"  [INTERESTING] {detail}")
            else:
                print(f"  [{status}] {detail}")
                
            await asyncio.sleep(0.5)

    print("\nAll combinations failed.")
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
