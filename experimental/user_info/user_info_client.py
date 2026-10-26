"""
UserInfoJetraClient - JetraClient with users.getFullUser support.
"""
import struct

from experimental.group_mgmt.group_client import GroupJetraClient
from jetrauserapi.high_level import RPC_ERROR, USER_CTOR
from jetrauserapi.client import wrap_init_connection

# Candidate constructor IDs for users.getFullUser
GET_FULL_USER_IDS = [
    0xB60F5918,  # Standard Telegram
    0xCFB9D957,  # Older variant
    0xCA30A5B1,  # Another older variant
]

INPUT_USER = 0xD8292816
INPUT_PEER_USER = 0xDDE8A54C


class UserInfoJetraClient(GroupJetraClient):
    
    async def get_full_user(self, user_id, access_hash):
        """
        Fetch full info of a user (bio, username, etc).
        """
        if not self._is_running:
            raise Exception("Client not started.")

        # Try both InputUser and InputPeerUser formats
        inputs = [
            (struct.pack("<I", INPUT_USER) + struct.pack("<q", user_id) + struct.pack("<q", access_hash), "InputUser"),
            (struct.pack("<I", INPUT_PEER_USER) + struct.pack("<Q", user_id) + struct.pack("<q", access_hash), "InputPeerUser")
        ]

        last_exception = None
        for ctor_id in GET_FULL_USER_IDS:
            for input_bytes, input_name in inputs:
                try:
                    body = struct.pack("<I", ctor_id) + input_bytes
                    result = await self.client.send_request(wrap_init_connection(body))
                    if not result:
                        raise Exception("No response")

                    result = self._unwrap_gzip(result)
                    resp_ctor = struct.unpack("<I", result[:4])[0]

                    if resp_ctor == RPC_ERROR:
                        err = self._parse_rpc_error(result)
                        raise Exception(f"Server error: {err}")

                    print(f"[SUCCESS] getFullUser worked with ctor {hex(ctor_id)} and {input_name}")
                    return self._parse_user_info(result)
                    
                except Exception as e:
                    last_exception = e
                    msg = str(e)
                    if "NOT_IMPLEMENTED" in msg or "METHOD_INVALID" in msg or "INPUT_REQUEST_INVALID" in msg:
                        print(f"[INFO] getFullUser {hex(ctor_id)} ({input_name}) -> {msg[:40]} (trying next...)")
                        continue
                    else:
                        raise

        raise Exception(f"All getFullUser attempts failed. Last error: {last_exception}")

    def _parse_user_info(self, result):
        # Look for Jetra User ctor (0xB1B8CC83)
        pos = result.find(struct.pack("<I", USER_CTOR))
        if pos == -1:
            return {"raw_hex": result.hex()}

        try:
            offset = pos + 4
            # Based on high_level.py: User ctor has 8 bytes of flags
            offset += 8
            user_id = struct.unpack("<q", result[offset:offset+8])[0]
            offset += 8
            access_hash = struct.unpack("<q", result[offset:offset+8])[0]
            offset += 8

            # Extract strings: first_name, last_name, username
            strings = []
            for _ in range(3):
                if offset >= len(result):
                    break
                
                str_len = result[offset]
                offset += 1
                
                if str_len < 0xFE:
                    s = result[offset:offset+str_len].decode('utf-8', errors='ignore')
                    offset += str_len
                else:
                    str_len = int.from_bytes(result[offset:offset+3], 'little')
                    offset += 3
                    s = result[offset:offset+str_len].decode('utf-8', errors='ignore')
                    offset += str_len
                
                # Skip TL padding
                offset = (offset + 3) & ~3
                strings.append(s)

            return {
                "user_id": user_id,
                "access_hash": access_hash,
                "first_name": strings[0] if len(strings) > 0 else "",
                "last_name": strings[1] if len(strings) > 1 else "",
                "username": strings[2] if len(strings) > 2 else ""
            }
        except Exception as e:
            return {"error_parsing": str(e), "raw_hex": result.hex()}
