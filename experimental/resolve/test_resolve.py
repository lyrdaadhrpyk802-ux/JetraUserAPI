"""
Interactive test for resolving usernames.
"""
import sys
import os
import asyncio

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from jetrauserapi.config import DEFAULT_SESSION_FILE, DEFAULT_DB_FILE
from experimental.resolve.resolve_client import ResolveJetraClient


async def main():
    print("=" * 60)
    print("Resolve Username Test (Sandbox)")
    print("=" * 60)

    client = ResolveJetraClient(DEFAULT_SESSION_FILE, DEFAULT_DB_FILE)
    await client.start()
    print("Client ready.\n")

    # Ask user for a username to test
    print("Enter a username to resolve (e.g., ali, telegram, etc):")
    username = input("> ").strip()

    if not username:
        print("No username provided.")
        await client.stop()
        return

    print(f"\nResolving @{username} ...")
    try:
        result = await client.resolve_username(username)
        print("Result:", result)
    except Exception as e:
        print("Failed:", e)

    await client.stop()
    print("Done.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
