"""
Test legacy kick methods: channels.kickFromChannel and messages.removeChatUser.
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
from jetrauserapi.high_level import RPC_ERROR, INPUT_CHANNEL
from jetrauserapi.client import wrap_init_connection

INPUT_USER = 0xD8292816
DUMMY_USER_ID = 123456789
DUMMY_ACCESS_HASH = 0

KICK_FROM_CHANNEL_ID = 0xEEC696F3
REMOVE_CHAT_USER_ID = 0xCABBCE40

async def try_method(client, method_name, ctor_id, body):
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
    print("Test Legacy Kick Methods")
    print("=" * 60)
    
    client = BanJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    
    groups = await client.get_groups()
    if not groups:
        await client.stop()
        return
        
    target = groups[0]
    channel_id = target['peer_id']
    channel_hash = target['access_hash']
    print(f"Target group: {target['title']} ({channel_id})")
    
    input_user = (
        struct.pack("<I", INPUT_USER) + 
        struct.pack("<q", DUMMY_USER_ID) + 
        struct.pack("<q", DUMMY_ACCESS_HASH)
    )

    # 1. channels.kickFromChannel
    print("\n1. Testing channels.kickFromChannel...")
    input_channel = (
        struct.pack("<I", INPUT_CHANNEL) + 
        struct.pack("<q", channel_id) + 
        struct.pack("<q", channel_hash)
    )
    # channel:InputChannel user_id:InputUser kicked:bool
    # kicked=True (0x997275B5)
    body = (
        struct.pack("<I", KICK_FROM_CHANNEL_ID) + 
        input_channel + 
        input_user + 
        struct.pack("<I", 0x997275B5)
    )
    status, detail = await try_method(client, "kickFromChannel", KICK_FROM_CHANNEL_ID, body)
    print(f"  [{status}] {detail}")
    await asyncio.sleep(1)

    # 2. messages.removeChatUser
    print("\n2. Testing messages.removeChatUser...")
    for cid in [channel_id, -channel_id]:
        print(f"  - chat_id={cid}...")
        # chat_id:int user_id:InputUser
        body = (
            struct.pack("<I", REMOVE_CHAT_USER_ID) + 
            struct.pack("<i", cid) + 
            input_user
        )
        status, detail = await try_method(client, "removeChatUser", REMOVE_CHAT_USER_ID, body)
        print(f"    [{status}] {detail}")
        
        if status == 'SUCCESS' or 'USER_NOT_PARTICIPANT' in str(detail):
            print("    [JACKPOT!] Found the correct method!")
            await client.stop()
            return
        await asyncio.sleep(1)

    print("\nAll legacy methods failed.")
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
