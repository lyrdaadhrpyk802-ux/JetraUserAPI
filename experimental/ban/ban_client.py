"""
BanJetraClient - JetraClient with ban/unban user support.
"""
import struct

from experimental.group_mgmt.group_client import GroupJetraClient
from jetrauserapi.high_level import (
    INPUT_PEER_USER,
    INPUT_CHANNEL,
    RPC_ERROR,
    USER_CTOR
)
from jetrauserapi.client import wrap_init_connection

# Candidate IDs for channels.editBanned
EDIT_BANNED_IDS = [
    0x96E1A901,  # Standard Telegram
    0xDF3A3B1F,  # Older variant
    0x0FF1A8D9,  # Guess
]


class BanJetraClient(GroupJetraClient):

    async def get_participants_with_hash(self, channel_id):
        """
        Fetch participants with their access_hash, needed for banning.
        """
        channel_input = await self._get_channel_input(channel_id)
        
        body = (
            struct.pack("<I", 0x77CED9D0) + # getParticipants
            channel_input +
            struct.pack("<I", 0xDE3F3C79) + # filter
            struct.pack("<i", 0) +           # offset
            struct.pack("<i", 100) +         # limit
            struct.pack("<q", 0)             # hash
        )
        
        result = await self.client.send_request(wrap_init_connection(body))
        if not result: return []
        result = self._unwrap_gzip(result)
        
        users = []
        pos = 0
        needle = struct.pack("<I", USER_CTOR)
        while True:
            pos = result.find(needle, pos)
            if pos == -1: break
            try:
                offset = pos + 4 + 8
                user_id = struct.unpack("<q", result[offset:offset+8])[0]
                offset += 8
                access_hash = struct.unpack("<q", result[offset:offset+8])[0]
                if not any(u['id'] == user_id for u in users):
                    users.append({"id": user_id, "access_hash": access_hash})
            except Exception: pass
            pos += 4
        return users

    async def edit_banned(self, channel_id, user_id, user_access_hash=0, ban=True):
        """
        Ban or unban a user in a channel/group.
        """
        if not self._is_running:
            raise Exception("Client not started.")

        # Build InputChannel
        access_hash = 0
        for d in self.db.get_dialogs():
            if d['peer_id'] == channel_id:
                access_hash = d['access_hash'] or 0
                break
        channel_input = (
            struct.pack("<I", INPUT_CHANNEL) +
            struct.pack("<q", channel_id) +
            struct.pack("<q", access_hash)
        )

        # Build InputPeerUser
        participant_input = (
            struct.pack("<I", INPUT_PEER_USER) +
            struct.pack("<Q", user_id) +
            struct.pack("<q", user_access_hash)
        )

        # Build ChatBannedRights (0x9F120418)
        # If ban=True, set view_messages (bit 0) = 1 (kick/ban).
        # If ban=False, set everything to 0 (unban).
        if ban:
            rights_flags = 1 # view_messages
            until_date = 0
        else:
            rights_flags = 0
            until_date = 0

        banned_rights = (
            struct.pack("<I", 0x9F120418) +
            struct.pack("<I", rights_flags) +
            struct.pack("<i", until_date)
        )

        last_exception = None
        for ctor_id in EDIT_BANNED_IDS:
            try:
                body = (
                    struct.pack("<I", ctor_id) +
                    channel_input +
                    participant_input +
                    banned_rights
                )
                result = await self.client.send_request(wrap_init_connection(body))
                if not result:
                    raise Exception("No response")
                
                result = self._unwrap_gzip(result)
                resp_ctor = struct.unpack("<I", result[:4])[0]
                
                if resp_ctor == RPC_ERROR:
                    err = self._parse_rpc_error(result)
                    raise Exception(f"Server error: {err}")
                
                print(f"[SUCCESS] editBanned worked with ctor {hex(ctor_id)} (ban={ban})")
                return True
                
            except Exception as e:
                last_exception = e
                msg = str(e)
                if "NOT_IMPLEMENTED" in msg or "METHOD_INVALID" in msg or "INPUT_REQUEST_INVALID" in msg:
                    print(f"[INFO] editBanned {hex(ctor_id)} -> {msg[:40]} (trying next...)")
                    continue
                else:
                    raise

        raise Exception(f"All editBanned attempts failed. Last error: {last_exception}")
