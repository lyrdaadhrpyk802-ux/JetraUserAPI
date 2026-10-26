"""
Test fetching full user info.
"""
import sys
import os
import asyncio

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.user_info.user_info_client import UserInfoJetraClient


async def main():
    print("=" * 60)
    print("User Info Test (Sandbox)")
    print("=" * 60)

    client = UserInfoJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    print("Client ready.\n")

    users = await client.get_users()
    if not users:
        print("No users in dialogs.")
        await client.stop()
        return

    print("Available users:")
    for i, u in enumerate(users[:10], 1):
        print(f"  {i}. {u['title']} (ID: {u['peer_id']})")

    try:
        idx = int(input("\nPick user number to fetch info: ").strip()) - 1
        user = users[idx]
    except (ValueError, IndexError):
        print("Invalid choice.")
        await client.stop()
        return

    print(f"\nFetching full info for {user['title']}...")
    try:
        info = await client.get_full_user(user['peer_id'], user['access_hash'])
        print("Result:", info)
    except Exception as e:
        print("Failed:", e)

    await client.stop()
    print("Done.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
