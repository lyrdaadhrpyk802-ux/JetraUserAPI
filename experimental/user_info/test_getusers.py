"""
Test users.getUsers fallback.
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
from experimental.user_info.user_info_client import UserInfoJetraClient
from jetrauserapi.high_level import RPC_ERROR, USER_CTOR
from jetrauserapi.client import wrap_init_connection

async def main():
    client = UserInfoJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()

    users = await client.get_users()
    if not users:
        print("No users.")
        await client.stop()
        return

    user = users[3] # Pick the 4th user for testing
    user_id = user['peer_id']
    access_hash = user['access_hash']
    print(f"\nTesting users.getUsers for {user_id}...")

    # users.getUsers takes a vector of InputUser
    input_user = (
        struct.pack("<I", 0xD8292816) + # InputUser
        struct.pack("<q", user_id) +
        struct.pack("<q", access_hash)
    )
    vector = (
        struct.pack("<I", 0x1CB5C415) + # Vector
        struct.pack("<i", 1) +          # count
        input_user
    )

    body = (
        struct.pack("<I", 0x0D91A548) + # users.getUsers
        vector
    )

    try:
        result = await client.client.send_request(wrap_init_connection(body))
        result = client._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        
        if resp_ctor == RPC_ERROR:
            print(f"Server error: {client._parse_rpc_error(result)}")
        else:
            print("Success! Parsing user object...")
            print(client._parse_user_info(result))
    except Exception as e:
        print(f"Failed: {e}")

    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
