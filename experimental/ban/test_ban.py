"""
Automatic test for ban/unban feature.
"""
import sys
import os
import asyncio

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.ban.ban_client import BanJetraClient

async def main():
    print("=" * 60)
    print("Ban User Test (Sandbox)")
    print("=" * 60)

    client = BanJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    print("Client ready.\n")

    groups = await client.get_groups()
    if not groups:
        print("No groups available.")
        await client.stop()
        return

    target = groups[0]
    peer_id = target['peer_id']
    print(f"Target group: {target['title']} (peer_id={peer_id})")

    print("\n1. Fetching participants...")
    users = await client.get_participants_with_hash(peer_id)
    if not users:
        print("   No users found.")
        await client.stop()
        return
    
    print(f"   Found {len(users)} users.")
    
    # Find a user to ban (not ourselves)
    target_user = None
    for u in users:
        if u['id'] != client.session.user_id:
            target_user = u
            break
            
    if not target_user:
        print("   No other user to ban.")
        await client.stop()
        return

    print(f"\n2. Banning user {target_user['id']} (access_hash={target_user['access_hash']})...")
    try:
        await client.edit_banned(peer_id, target_user['id'], target_user['access_hash'], ban=True)
        print("   Banned successfully! Check the group in the official app.")
    except Exception as e:
        print(f"   Failed to ban: {e}")
        await client.stop()
        return

    await asyncio.sleep(3)

    print(f"\n3. Unbanning user {target_user['id']}...")
    try:
        await client.edit_banned(peer_id, target_user['id'], target_user['access_hash'], ban=False)
        print("   Unbanned successfully! Check the group again.")
    except Exception as e:
        print(f"   Failed to unban: {e}")

    await client.stop()
    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(main())
