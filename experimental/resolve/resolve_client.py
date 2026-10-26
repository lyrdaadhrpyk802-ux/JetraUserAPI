"""
ResolveJetraClient - JetraClient with resolve username support.
Tries multiple constructors and both '@username' and 'username' formats.
"""
import struct

from experimental.reply.reply_client import ReplyJetraClient
from jetrauserapi.high_level import RPC_ERROR
from jetrauserapi.client import wrap_init_connection

# Candidate constructor IDs for contacts.resolveUsername
RESOLVE_USERNAME_IDS = [
    0xF93CD45C,  # Standard Telegram
    0x725AFBBC,  # Older Telegram variant
]

# Candidate constructor IDs for contacts.search (fallback)
CONTACTS_SEARCH_IDS = [
    0x11F812D8,  # Standard Telegram
]


class ResolveJetraClient(ReplyJetraClient):
    
    async def resolve_username(self, username):
        """
        Resolve a username to a user or channel ID.
        """
        if not self._is_running:
            raise Exception("Client not started.")
            
        clean_username = username.replace("@", "").strip()
        if not clean_username:
            raise ValueError("Username cannot be empty")

        # Try formats: without @, with @
        formats = [clean_username, "@" + clean_username]
        
        for ctor_id in RESOLVE_USERNAME_IDS:
            for fmt in formats:
                try:
                    body = (
                        struct.pack("<I", ctor_id) +
                        self._tl_string(fmt)
                    )
                    
                    result = await self.client.send_request(wrap_init_connection(body))
                    if not result:
                        raise Exception("No response")
                        
                    result = self._unwrap_gzip(result)
                    resp_ctor = struct.unpack("<I", result[:4])[0]
                    
                    if resp_ctor == RPC_ERROR:
                        err = self._parse_rpc_error(result)
                        raise Exception(f"Server error: {err}")
                    
                    return self._parse_resolved_peer(result)
                        
                except Exception as e:
                    last_exception = e
                    msg = str(e)
                    if "NOT_IMPLEMENTED" in msg or "METHOD_INVALID" in msg or "INPUT_REQUEST_INVALID" in msg:
                        print(f"[INFO] resolveUsername {hex(ctor_id)} (fmt: {fmt}) -> {msg[:40]}")
                        continue
                    else:
                        raise

        # Fallback to contacts.search
        print("\n[INFO] resolveUsername failed. Trying contacts.search...")
        for ctor_id in CONTACTS_SEARCH_IDS:
            try:
                body = (
                    struct.pack("<I", ctor_id) +
                    self._tl_string(clean_username) +
                    struct.pack("<i", 10) # limit
                )
                result = await self.client.send_request(wrap_init_connection(body))
                if not result:
                    continue
                    
                result = self._unwrap_gzip(result)
                resp_ctor = struct.unpack("<I", result[:4])[0]
                if resp_ctor == RPC_ERROR:
                    err = self._parse_rpc_error(result)
                    raise Exception(f"Server error: {err}")
                    
                return self._parse_resolved_peer(result)
                
            except Exception as e:
                last_exception = e
                print(f"[INFO] contacts.search {hex(ctor_id)} -> {str(e)[:40]}")
                continue

        raise Exception(f"All resolve methods failed. Last error: {last_exception}")

    def _parse_resolved_peer(self, result):
        PEER_USER = 0x59511722
        PEER_CHANNEL = 0xA2A5371E
        
        pos_user = result.find(struct.pack("<I", PEER_USER))
        pos_channel = result.find(struct.pack("<I", PEER_CHANNEL))
        
        if pos_user != -1:
            offset = pos_user + 4
            peer_id = struct.unpack("<q", result[offset:offset+8])[0]
            return {"peer_id": peer_id, "peer_type": "user"}
        elif pos_channel != -1:
            offset = pos_channel + 4
            peer_id = struct.unpack("<q", result[offset:offset+8])[0]
            return {"peer_id": peer_id, "peer_type": "group"}
        else:
            return {"raw_hex": result.hex()}
