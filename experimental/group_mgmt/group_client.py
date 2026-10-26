"""
GroupJetraClient - JetraClient with group management features.
"""
import struct
import random

from experimental.reply.reply_client import ReplyJetraClient
from experimental.group_mgmt.group_parser import parse_users, parse_channels
from jetrauserapi.high_level import RPC_ERROR
from jetrauserapi.client import wrap_init_connection

INPUT_CHANNEL = 0xF35AEC28

GET_PARTICIPANTS_IDS = [0x77CED9D0]
GET_FULL_CHANNEL_IDS = [0x08736A09]
LEAVE_CHANNEL_IDS = [0xF836AA95]

class GroupJetraClient(ReplyJetraClient):
    async def _get_channel_input(self, peer_id):
        access_hash = 0
        for d in self.db.get_dialogs():
            if d['peer_id'] == peer_id:
                access_hash = d['access_hash'] or 0
                break
        return (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", peer_id) +
            struct.pack("<q", access_hash)
        )

    async def _try_method(self, method_name, ids, body_builder):
        for ctor_id in ids:
            try:
                body = body_builder(ctor_id)
                result = await self.client.send_request(wrap_init_connection(body))
                if not result: raise Exception("No response")
                
                result = self._unwrap_gzip(result)
                resp_ctor = struct.unpack("<I", result[:4])[0]

                if resp_ctor == RPC_ERROR:
                    raise Exception(self._parse_rpc_error(result))
                
                return result
            except Exception as e:
                if "NOT_IMPLEMENTED" in str(e):
                    continue
                raise
        return None

    async def get_participants(self, peer_id):
        if not self._is_running: raise Exception("Client not started.")
        channel_input = await self._get_channel_input(peer_id)
        
        def build_body(ctor_id):
            return (
                struct.pack("<I", ctor_id) + channel_input +
                struct.pack("<I", 0xDE3F3C79) + # filter
                struct.pack("<i", 0) +           # offset
                struct.pack("<i", 100) +         # limit
                struct.pack("<q", 0)             # hash
            )
            
        result = await self._try_method("getParticipants", GET_PARTICIPANTS_IDS, build_body)
        if result:
            users = parse_users(result)
            channels = parse_channels(result)
            print(f"  Parsed {len(users)} users and {len(channels)} channels.")
            for u in users:
                print(f"    - User ID: {u['user_id']}")
            return users

    async def get_full_channel(self, peer_id):
        if not self._is_running: raise Exception("Client not started.")
        channel_input = await self._get_channel_input(peer_id)
        
        def build_body(ctor_id):
            return struct.pack("<I", ctor_id) + channel_input
            
        result = await self._try_method("getFullChannel", GET_FULL_CHANNEL_IDS, build_body)
        if result:
            users = parse_users(result)
            channels = parse_channels(result)
            print(f"  Parsed full info. Found {len(channels)} channel(s).")
            for c in channels:
                print(f"    - Channel: {c['title']} (ID: {c['channel_id']})")
            return channels

    async def leave_channel(self, peer_id):
        if not self._is_running: raise Exception("Client not started.")
        channel_input = await self._get_channel_input(peer_id)
        
        def build_body(ctor_id):
            return struct.pack("<I", ctor_id) + channel_input
            
        result = await self._try_method("leaveChannel", LEAVE_CHANNEL_IDS, build_body)
        if result:
            print("  Successfully left the group!")
            return True
