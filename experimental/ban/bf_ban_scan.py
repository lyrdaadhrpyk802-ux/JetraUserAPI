"""
Fast Brute-force channels.editBanned ctor ID.
Scans a focused range around standard Telegram ID with ZERO delay.
Handles FLOOD_WAIT automatically.
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
    INPUT_CHANNEL, INPUT_PEER_USER, RPC_ERROR
)
from jetrauserapi.client import wrap_init_connection

# Focused range around standard Telegram editBanned (0x96E1A901)
RANGE_START = 0x96E19000
RANGE_END = 0x96E1C000

async def try_edit_banned(client, channel_id, channel_hash, user_id, user_hash, ctor_id):
    channel_input = (
        struct.pack("<I", INPUT_CHANNEL) +
        struct.pack("<q", channel_id) +
        struct.pack("<q", channel_hash)
    )
    participant_input = (
        struct.pack("<I", INPUT_PEER_USER) +
        struct.pack("<Q", user_id) +
        struct.pack("<q", user_hash)
    )
    
    # ChatBannedRights (unban, so flags=0)
    banned_rights = (
        struct.pack("<I", 0x9F120418) +
        struct.pack("<I", 0) +
        struct.pack("<i", 0)
    )
    
    body = (
        struct.pack("<I", ctor_id) +
        channel_input +
        participant_input +
        banned_rights
    )
    
    try:
        result = await client.client.send_request(wrap_init_connection(body))
        if not result:
            return ('NO_RESPONSE', None)
        
        result = client._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        
        if resp_ctor == RPC_ERROR:
            err = client._parse_rpc_error(result)
            if "NOT_IMPLEMENTED" in err:
                return ('NOT_IMPLEMENTED', err)
            if "FLOOD_WAIT" in err:
                # Extract seconds and wait
                try:
                    wait = int(err.split("_")[-1])
                    print(f"  [FLOOD_WAIT] Sleeping for {wait}s...")
                    await asyncio.sleep(wait + 1)
                except:
                    await asyncio.sleep(5)
                return ('FLOOD_WAIT', err)
            return ('OTHER_ERROR:' + err, err)
            
        return ('SUCCESS', hex(resp_ctor))
    except Exception as e:
        return ('EXCEPTION', str(e))

async def main():
    print("=" * 60)
    print("Fast Brute-Force editBanned (Unban Mode)")
    print(f"Range: {hex(RANGE_START)} -> {hex(RANGE_END)}")
    print("Delay: 0s (network-bound)")
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
    
    print("Fetching a test user...")
    users = await client.get_participants_with_hash(channel_id)
    if not users:
        print("No users found in group.")
        await client.stop()
        return
        
    test_user = users[0]
    print(f"Using user {test_user['id']} for testing.\n")
    
    total = RANGE_END - RANGE_START
    count = 0
    start_time = asyncio.get_event_loop().time()
    
    for ctor_id in range(RANGE_START, RANGE_END):
        count += 1
        if count % 500 == 0:
            elapsed = asyncio.get_event_loop().time() - start_time
            speed = count / elapsed if elapsed > 0 else 0
            print(f"  Progress: {count}/{total} ({hex(ctor_id)}) - {speed:.1f} req/s")
            
        status, detail = await try_edit_banned(
            client, channel_id, channel_hash,
            test_user['id'], test_user['access_hash'],
            ctor_id
        )
        
        label = format(ctor_id, '#010x')
        
        if status == 'SUCCESS':
            print(f"\n[FOUND] {label} -> SUCCESS\n")
            break
        elif status == 'NOT_IMPLEMENTED':
            pass # Keep scanning
        elif status == 'FLOOD_WAIT':
            pass # Handled inside try_edit_banned
        else:
            print(f"\n[INTERESTING] {label} -> {status} : {detail}\n")
            # Don't break, keep scanning to see if there are more interesting ones
        
    print("\nScan complete.")
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
