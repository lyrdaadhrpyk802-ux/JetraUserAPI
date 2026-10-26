"""
Test group management features.
"""
import sys
import os
import asyncio

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.group_mgmt.group_client import GroupJetraClient


async def show_dialogs(client, peer_type=None, limit=20):
    dialogs = await client.get_dialogs(peer_type)
    if not dialogs:
        print("  (no dialogs)")
        return []
    print("\n  #    Type    peer_id          title")
    print("  " + "-" * 60)
    for i, d in enumerate(dialogs[:limit], 1):
        title = (d['title'] or '')[:35]
        print("  {:<4} {:<7} {:<16} {}".format(
            i, d['peer_type'], d['peer_id'], title
        ))
    return dialogs[:limit]


async def test_participants(client):
    print("\n--- Get Participants ---")
    groups = await show_dialogs(client, "group")
    if not groups: return
    
    try:
        idx = int(input("\nPick group number: ").strip()) - 1
        d = groups[idx]
    except (ValueError, IndexError):
        print("Invalid."); return

    peer_id = d['peer_id']
    print(f"\nFetching participants for {d['title']} ({peer_id})...")
    try:
        result = await client.get_participants(peer_id)
        if result:
            print("Done. Check output above for details.")
    except Exception as e:
        print(f"Failed: {e}")


async def test_full_channel(client):
    print("\n--- Get Full Channel Info ---")
    groups = await show_dialogs(client, "group")
    if not groups: return
    
    try:
        idx = int(input("\nPick group number: ").strip()) - 1
        d = groups[idx]
    except (ValueError, IndexError):
        print("Invalid."); return

    peer_id = d['peer_id']
    print(f"\nFetching full info for {d['title']} ({peer_id})...")
    try:
        result = await client.get_full_channel(peer_id)
        if result:
            print("Done. Check output above for details.")
    except Exception as e:
        print(f"Failed: {e}")


async def test_leave_channel(client):
    print("\n--- Leave Channel (WARNING) ---")
    print("This will try to make you leave the group.")
    groups = await show_dialogs(client, "group")
    if not groups: return
    
    try:
        idx = int(input("\nPick group number: ").strip()) - 1
        d = groups[idx]
    except (ValueError, IndexError):
        print("Invalid."); return

    peer_id = d['peer_id']
    confirm = input(f"Are you sure you want to leave '{d['title']}'? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled."); return

    print(f"\nLeaving {d['title']} ({peer_id})...")
    try:
        await client.leave_channel(peer_id)
    except Exception as e:
        print(f"Failed: {e}")


async def main():
    print("=" * 60)
    print("Group Management Test (Sandbox)")
    print("=" * 60)

    client = GroupJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    print("Client ready.\n")

    while True:
        print("\n--- Menu ---")
        print("1. Get participants list")
        print("2. Get full group info")
        print("3. Leave a group")
        print("4. Quit")
        choice = input("Choose [1-4]: ").strip()

        if choice == "1":
            await test_participants(client)
        elif choice == "2":
            await test_full_channel(client)
        elif choice == "3":
            await test_leave_channel(client)
        elif choice == "4":
            break
        else:
            print("Invalid choice.")

    print("\nStopping client...")
    await client.stop()
    print("Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
