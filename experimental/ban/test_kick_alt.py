"""
Test alternative kick methods: deleteChatUser (InputPeerChat) and editAdmin.
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
INPUT_PEER_CHAT = 0x35A95CB9
DUMMY_USER_ID = 123456789
DUMMY_ACCESS_HASH = 0

DELETE_CHAT_USER_ID = 0xA2185CAB
EDIT_ADMIN_IDS = [0xE1FA6D36, 0xD33C8902, 0x566D0E82]

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
    print("Test Alternative Kick Methods")
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
    
    # 1. messages.deleteChatUser with InputPeerChat
    print("\n1. Testing messages.deleteChatUser with InputPeerChat...")
    input_peer_chat = struct.pack("<I", INPUT_PEER_CHAT) + struct.pack("<q", channel_id)
    input_user = struct.pack("<I", INPUT_USER) + struct.pack("<q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)
    
    # flags=0
    body = struct.pack("<I", DELETE_CHAT_USER_ID) + struct.pack("<I", 0) + input_peer_chat + input_user
    status, detail = await try_method(client, "deleteChatUser (InputPeerChat)", DELETE_CHAT_USER_ID, body)
    print(f"  [{status}] {detail}")

    # 2. channels.editAdmin (revoking all rights = kick)
    for ctor_id in EDIT_ADMIN_IDS:
        print(f"\n2. Testing channels.editAdmin ({hex(ctor_id)})...")
        input_channel = struct.pack("<I", INPUT_CHANNEL) + struct.pack("<q", channel_id) + struct.pack("<q", channel_hash)
        input_user = struct.pack("<I", INPUT_USER) + struct.pack("<q", DUMMY_USER_ID) + struct.pack("<q", DUMMY_ACCESS_HASH)
        admin_rights = struct.pack("<I", 0x5FB224D5) + struct.pack("<I", 0) # flags=0 (no rights)
        rank = struct.pack("<B", 0) + b"\x00\x00\x00" # empty string
        body = struct.pack("<I", ctor_id) + input_channel + input_user + admin_rights + rank
        
        status, detail = await try_method(client, "editAdmin", ctor_id, body)
        print(f"  [{status}] {detail}")
        
        if status == 'SUCCESS' or 'USER_NOT_PARTICIPANT' in str(detail):
            print("  [JACKPOT!] Found the correct method!")
            break
        await asyncio.sleep(1)

    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
