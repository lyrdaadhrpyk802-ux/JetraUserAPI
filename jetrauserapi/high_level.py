import asyncio
import struct
import gzip
import hashlib
import datetime
import random
import time

from jetrauserapi.client import JetraClient as LowLevelClient, wrap_init_connection, aes_ige_decrypt
from jetrauserapi.session import JetraSession
from jetrauserapi.message import Message, MessageEntity
from jetrauserapi.database import Database
from jetrauserapi.exceptions import (
    JetraError,
    JetraConnectionError,
    JetraRPCError,
    JetraAuthError
)

INPUT_PEER_USER = 0xDDE8A54C
INPUT_PEER_SELF = 0x7DA07EC9
INPUT_PEER_CHANNEL = 0x27BCBBFC
INPUT_CHANNEL = 0xF35AEC28

PEER_USER = 0x59511722
PEER_CHANNEL = 0xA2A5371E

MSG_CTOR_JETRA = 0x7600B9D3
SERVICE_MSG_CTOR_JETRA = 0x7A800E0A
CHANNEL_CTOR = 0xD49F34C6
USER_CTOR = 0xB1B8CC83

SEND_MESSAGE_ID = 0xFEF48F62
GET_DIALOGS_ID = 0xA0F4CB4F
GET_STATE_ID = 0xEDD4882A
GET_PARTICIPANTS_ID = 0x77CED9D0
GET_FULL_CHANNEL_ID = 0x08736A09
LEAVE_CHANNEL_ID = 0xF836AA95
CONTACTS_SEARCH_ID = 0x11F812D8

RPC_ERROR = 0x2144CA19
GZIP_PACKED = 0x3072CFA1
UPDATES = 0x74AE4240
UPDATE_NEW_MESSAGE = 0x1F2B0AFD
UPDATE_NEW_CHANNEL_MESSAGE = 0x62BA04D9


class JetraClient:
    def __init__(self, session_file="jetra_session.json", db_file="jetra_local.db"):
        self.session = JetraSession(session_file)
        self.db = Database(db_file)
        self.client = LowLevelClient(session=self.session)

        self._message_handlers = []
        self._ready_handlers = []
        self._is_running = False
        self._listen_task = None
        self._reconnect_delay = 5
        self._max_reconnect_attempts = 10
        self._ready_event = asyncio.Event()

        self._recv_lock = asyncio.Lock()

        client_ref = self.client

        def _patched_pack_msg_id():
            client_ref._msg_counter = getattr(client_ref, '_msg_counter', 0) + 1
            current_time = int(time.time())
            msg_id = (current_time << 32) | (client_ref._msg_counter << 2)
            return struct.pack("<Q", msg_id)

        self.client._pack_msg_id = _patched_pack_msg_id

        original_send_request = self.client.send_request
        client_ref_for_patch = self

        async def _patched_send_request(method_bytes):
            async with client_ref_for_patch._recv_lock:
                return await original_send_request(method_bytes)

        self.client.send_request = _patched_send_request

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def on_message(self, func):
        self._message_handlers.append(func)
        return func

    def on_ready(self, func):
        self._ready_handlers.append(func)
        return func

    async def _trigger_message_handlers(self, message):
        for handler in self._message_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                print(f"Error in message handler: {e}")

    async def _trigger_ready_handlers(self):
        for handler in self._ready_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception as e:
                print(f"Error in ready handler: {e}")

    async def start(self, wait_ready=True, timeout=30):
        if not self.session.is_authorized():
            raise JetraAuthError("Not logged in. Please run login.py first.")

        self._is_running = True
        self._listen_task = asyncio.create_task(self._main_loop())

        if wait_ready:
            try:
                await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                raise JetraConnectionError(f"Client did not become ready within {timeout}s")

    async def _main_loop(self):
        attempt = 0
        while self._is_running:
            try:
                await self._connect_and_run()
                attempt = 0
            except Exception as e:
                if not self._is_running:
                    break

                attempt += 1
                if attempt > self._max_reconnect_attempts:
                    print(f"Max reconnect attempts ({self._max_reconnect_attempts}) reached. Giving up.")
                    self._is_running = False
                    break

                print(f"Connection lost: {e}")
                print(f"Reconnecting in {self._reconnect_delay}s... (attempt {attempt}/{self._max_reconnect_attempts})")
                await asyncio.sleep(self._reconnect_delay)

    async def _connect_and_run(self):
        print("Connecting to Jetra...")
        await self.client.connect()

        print("Syncing state...")
        get_state = struct.pack("<I", GET_STATE_ID)
        result = await self.client.send_request(wrap_init_connection(get_state))
        if result:
            result = self._unwrap_gzip(result)
            if len(result) >= 4 and struct.unpack("<I", result[:4])[0] == 0xA56C2A3E:
                pts = struct.unpack("<i", result[4:8])[0]
                print(f"State synced. pts={pts}")

        await asyncio.sleep(0.2)

        print("Loading dialogs...")
        await self._load_dialogs()

        print("Client started. Listening for messages...")
        self._ready_event.set()
        await self._trigger_ready_handlers()

        await self._listen_loop()

    async def _listen_loop(self):
        while self._is_running:
            try:
                raw = None
                try:
                    async with asyncio.timeout(0.1):
                        await self._recv_lock.acquire()
                        try:
                            raw = await self.client.ws.recv()
                        finally:
                            self._recv_lock.release()
                except (asyncio.TimeoutError, TimeoutError):
                    await asyncio.sleep(0.01)
                    continue

                if raw is None:
                    continue

                decrypted = self.client.dec_cipher.decrypt(raw)

                if len(decrypted) < 1:
                    continue

                first_byte = decrypted[0]
                if first_byte < 0x7F:
                    payload = decrypted[1:1 + (first_byte << 2)]
                elif first_byte == 0x7F:
                    frame_len = int.from_bytes(decrypted[1:4], 'little') << 2
                    payload = decrypted[4:4 + frame_len]
                else:
                    payload = decrypted

                if len(payload) < 24 or payload[0:8] != self.client.auth_key_id:
                    continue

                msg_key_received = payload[8:24]
                encrypted_data = payload[24:]
                if len(encrypted_data) % 16 != 0:
                    encrypted_data = encrypted_data[:-(len(encrypted_data) % 16)]

                i = 8
                a = bytearray(52)
                a[0:16] = msg_key_received
                a[16:52] = self.client.auth_key[i:i + 36]
                s0 = hashlib.sha256(bytes(a)).digest()

                o = bytearray(52)
                o[0:36] = self.client.auth_key[40 + i:40 + i + 36]
                o[36:52] = msg_key_received
                s1 = hashlib.sha256(bytes(o)).digest()

                aes_key = s0[0:8] + s1[8:24] + s0[24:32]
                aes_iv = s1[0:8] + s0[8:24] + s1[24:32]

                inner = aes_ige_decrypt(encrypted_data, aes_key, aes_iv)
                offset = 8 + 8 + 8 + 4
                msg_len = struct.unpack('<I', inner[offset:offset + 4])[0]
                offset += 4
                msg_data = inner[offset:offset + msg_len]

                if len(msg_data) >= 4:
                    ctor = struct.unpack('<I', msg_data[:4])[0]
                    if ctor == UPDATES:
                        await self._handle_updates(msg_data)

            except Exception as e:
                if not self._is_running:
                    break
                if self.client.ws.closed:
                    raise JetraConnectionError("WebSocket closed")
                await asyncio.sleep(0.1)

    async def stop(self):
        print("Stopping client...")
        self._is_running = False
        self._ready_event.clear()
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        await self.client.close()
        self.db.close()
        print("Client stopped.")

    async def _handle_updates(self, msg_data):
        pos = msg_data.find(struct.pack("<I", UPDATE_NEW_MESSAGE))
        channel_pos = msg_data.find(struct.pack("<I", UPDATE_NEW_CHANNEL_MESSAGE))

        if channel_pos != -1:
            pos = channel_pos

        if pos == -1:
            return

        msg_pos = pos + 4
        if len(msg_data) < msg_pos + 4:
            return

        msg_ctor = struct.unpack("<I", msg_data[msg_pos:msg_pos + 4])[0]
        if msg_ctor not in (MSG_CTOR_JETRA, SERVICE_MSG_CTOR_JETRA):
            return

        message = self._parse_message(msg_data, msg_pos, msg_ctor)
        if message:
            self.db.save_message(message)
            await self._trigger_message_handlers(message)

    def _parse_message(self, data, offset, ctor):
        try:
            offset += 4
            if ctor == SERVICE_MSG_CTOR_JETRA:
                offset += 4
                msg_id = struct.unpack("<i", data[offset:offset + 4])[0]
                offset += 4
                flags = 0
            else:
                flags = struct.unpack("<i", data[offset:offset + 4])[0]
                offset += 4
                offset += 4
                msg_id = struct.unpack("<i", data[offset:offset + 4])[0]
                offset += 4

            from_peer_ctor = struct.unpack("<I", data[offset:offset + 4])[0]
            offset += 4
            from_id = struct.unpack("<q", data[offset:offset + 8])[0]
            offset += 8

            peer_ctor = struct.unpack("<I", data[offset:offset + 4])[0]
            offset += 4
            peer_id = struct.unpack("<q", data[offset:offset + 8])[0]
            offset += 8

            date = struct.unpack("<i", data[offset:offset + 4])[0]
            offset += 4

            reply_to_msg_id = None
            if ctor != SERVICE_MSG_CTOR_JETRA and (flags & 0x1):
                try:
                    reply_to_msg_id = struct.unpack("<i", data[offset:offset + 4])[0]
                    offset += 4
                except Exception:
                    pass

            text = ""
            try:
                text_len = data[offset]
                text = data[offset + 1:offset + 1 + text_len].decode('utf-8', errors='ignore')
                offset += 1 + text_len
                offset = (offset + 3) & ~3
            except:
                pass

            entities = []
            if offset + 8 <= len(data):
                vec_ctor = struct.unpack("<I", data[offset:offset+4])[0]
                if vec_ctor == 0x1CB5C415:
                    count = struct.unpack("<i", data[offset+4:offset+8])[0]
                    offset += 8
                    for _ in range(count):
                        if offset + 12 > len(data): break
                        e_ctor = struct.unpack("<I", data[offset:offset+4])[0]
                        e_offset = struct.unpack("<i", data[offset+4:offset+8])[0]
                        e_length = struct.unpack("<i", data[offset+8:offset+12])[0]
                        offset += 12
                        
                        e_type = "unknown"
                        extra = None
                        if e_ctor == 0xBD610BC9: e_type = "bold"
                        elif e_ctor == 0x826F8B60: e_type = "italic"
                        elif e_ctor == 0x9C4E7E8B: e_type = "underline"
                        elif e_ctor == 0xBF0693D4: e_type = "strike"
                        elif e_ctor == 0x28A20571: e_type = "code"
                        elif e_ctor == 0x73924BE0: 
                            e_type = "pre"
                            if offset < len(data):
                                lang_len = data[offset]
                                offset += 1 + lang_len
                                offset = (offset + 3) & ~3
                        elif e_ctor == 0x6ED02538: e_type = "url"
                        elif e_ctor == 0x76A6D327: 
                            e_type = "text_url"
                            if offset < len(data):
                                url_len = data[offset]
                                extra = data[offset+1:offset+1+url_len].decode('utf-8', errors='ignore')
                                offset += 1 + url_len
                                offset = (offset + 3) & ~3
                        elif e_ctor == 0xFA04579D: e_type = "mention"
                        elif e_ctor == 0x6F635B0D: e_type = "hashtag"
                        elif e_ctor == 0x6CEF8AC7: e_type = "bot_command"
                        elif e_ctor == 0x64E475C2: e_type = "email"
                        elif e_ctor == 0x9B69E34B: e_type = "phone"
                        
                        entities.append(MessageEntity(e_type, e_offset, e_length, extra))

            if peer_ctor == PEER_USER:
                peer_type = 'user'
            elif peer_ctor == PEER_CHANNEL:
                peer_type = 'group'
            else:
                peer_type = 'unknown'

            return Message(
                msg_id=msg_id,
                from_id=from_id,
                peer_id=peer_id,
                peer_type=peer_type,
                date=date,
                text=text,
                reply_to_msg_id=reply_to_msg_id,
                entities=entities
            )
        except Exception as e:
            print(f"Failed to parse message: {e}")
            return None

    async def send_message(self, peer_id, text, peer_type=None, reply_to=None):
        if not self._is_running:
            raise JetraError("Client is not started. Call await client.start() first.")

        if peer_type is None:
            dialogs = self.db.get_dialogs()
            for d in dialogs:
                if d['peer_id'] == peer_id:
                    peer_type = d['peer_type']
                    break
            else:
                peer_type = 'group' if peer_id > 1000 else 'user'

        if peer_type == 'user':
            input_peer = (
                struct.pack("<I", INPUT_PEER_USER) +
                struct.pack("<Q", peer_id) +
                struct.pack("<q", 0)
            )
        else:
            access_hash = 0
            for d in self.db.get_dialogs():
                if d['peer_id'] == peer_id:
                    access_hash = d['access_hash'] or 0
                    break
            input_peer = (
                struct.pack("<I", INPUT_PEER_CHANNEL) +
                struct.pack("<q", peer_id) +
                struct.pack("<q", access_hash)
            )

        reply_to_msg_id = None
        if reply_to is not None:
            if isinstance(reply_to, Message):
                reply_to_msg_id = reply_to.id
            elif isinstance(reply_to, int):
                reply_to_msg_id = reply_to
            else:
                raise TypeError("reply_to must be Message or int")
            if reply_to_msg_id == 0:
                raise ValueError("reply_to msg_id is 0 (invalid)")

        flags = 0
        reply_bytes = b""
        if reply_to_msg_id is not None:
            flags |= 0x1
            reply_bytes = (
                struct.pack("<I", 0x3BD4B7C2) +
                struct.pack("<I", 0) +
                struct.pack("<i", reply_to_msg_id)
            )

        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", SEND_MESSAGE_ID) +
            struct.pack("<I", flags) +
            input_peer +
            reply_bytes +
            self._tl_string(text) +
            struct.pack("<q", random_id)
        )

        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise JetraConnectionError("No response from sendMessage")

        result = self._unwrap_gzip(result)
        ctor = struct.unpack('<I', result[:4])[0]
        if ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="sendMessage")

        real_msg_id = 0
        real_date = int(datetime.datetime.now().timestamp())
        needle = struct.pack("<I", MSG_CTOR_JETRA)
        pos = result.find(needle)
        if pos >= 0:
            try:
                msg_id_offset = pos + 12
                real_msg_id = struct.unpack("<i", result[msg_id_offset:msg_id_offset+4])[0]
                date_offset = msg_id_offset + 4 + 12 + 12
                real_date = struct.unpack("<i", result[date_offset:date_offset+4])[0]
            except Exception:
                pass

        sent_msg = Message(
            msg_id=real_msg_id,
            from_id=self.session.user_id,
            peer_id=peer_id,
            peer_type=peer_type,
            date=real_date,
            text=text,
            reply_to_msg_id=reply_to_msg_id
        )
        self.db.save_message(sent_msg)
        return real_msg_id

    async def send_to_saved(self, text):
        if not self._is_running:
            raise JetraError("Client is not started.")

        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", SEND_MESSAGE_ID) +
            struct.pack("<I", 0) +
            struct.pack("<I", INPUT_PEER_SELF) +
            self._tl_string(text) +
            struct.pack("<q", random_id)
        )

        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise JetraConnectionError("No response from sendMessage")
        return True

    async def _load_dialogs(self):
        get_dialogs = (
            struct.pack("<I", GET_DIALOGS_ID) +
            struct.pack("<I", 0) +
            struct.pack("<i", 0) +
            struct.pack("<i", 0) +
            struct.pack("<I", 0x7F3B18EA) +
            struct.pack("<i", 100) +
            struct.pack("<q", 0)
        )

        result = await self.client.send_request(wrap_init_connection(get_dialogs))
        if not result:
            return

        data = self._unwrap_gzip(result)

        pos = 0
        count = 0
        while True:
            pos = data.find(struct.pack("<I", CHANNEL_CTOR), pos)
            if pos == -1:
                break

            try:
                offset = pos + 4
                flags = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8
                channel_id = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8
                access_hash = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8

                title_len = data[offset]
                offset += 1
                if title_len < 0xFE:
                    title = data[offset:offset + title_len].decode('utf-8', errors='ignore')
                    offset += title_len
                else:
                    title_len = int.from_bytes(data[offset:offset + 3], 'little')
                    offset += 3
                    title = data[offset:offset + title_len].decode('utf-8', errors='ignore')
                    offset += title_len

                if flags & 0x100:
                    self.db.save_dialog(channel_id, 'group', title, access_hash)
                    count += 1
            except:
                pass

            pos += 4

        pos = 0
        while True:
            pos = data.find(struct.pack("<I", USER_CTOR), pos)
            if pos == -1:
                break

            try:
                offset = pos + 4
                offset += 8
                user_id = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8
                access_hash = struct.unpack("<q", data[offset:offset + 8])[0]
                offset += 8

                strings = []
                for _ in range(3):
                    if offset >= len(data): break
                    
                    str_len = data[offset]
                    if str_len < 0xFE:
                        s = data[offset+1:offset+1+str_len].decode('utf-8', errors='ignore')
                        offset += 1 + str_len
                    else:
                        str_len = int.from_bytes(data[offset+1:offset+4], 'little')
                        s = data[offset+4:offset+4+str_len].decode('utf-8', errors='ignore')
                        offset += 4 + str_len
                    
                    offset = (offset + 3) & ~3
                    strings.append(s)
                
                first_name = strings[0] if len(strings) > 0 else ""
                last_name = strings[1] if len(strings) > 1 else ""
                username = strings[2] if len(strings) > 2 else ""
                
                if username and not all(c.isalnum() or c == '_' for c in username):
                    username = ""

                first_name = ''.join(c for c in first_name if c.isprintable() and c not in '\ufffd')
                last_name = ''.join(c for c in last_name if c.isprintable() and c not in '\ufffd')

                full_name = f"{first_name} {last_name}".strip()
                if not full_name:
                    full_name = f"User {user_id}"
                if username:
                    full_name += f" (@{username})"

                self.db.save_dialog(user_id, 'user', full_name, access_hash)
                count += 1
            except Exception as e:
                pass

            pos += 4

        print(f"Loaded {count} dialogs into database.")

    async def get_dialogs(self, peer_type=None):
        return self.db.get_dialogs(peer_type)

    async def get_groups(self):
        return self.db.get_dialogs('group')

    async def get_users(self):
        return self.db.get_dialogs('user')

    def get_history(self, peer_id=None, limit=100):
        return self.db.get_messages(peer_id, limit)

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

    async def get_participants(self, peer_id):
        if not self._is_running: raise JetraError("Client not started.")
        channel_input = await self._get_channel_input(peer_id)
        
        body = (
            struct.pack("<I", GET_PARTICIPANTS_ID) +
            channel_input +
            struct.pack("<I", 0xDE3F3C79) +
            struct.pack("<i", 0) +
            struct.pack("<i", 100) +
            struct.pack("<q", 0)
        )
        
        result = await self.client.send_request(wrap_init_connection(body))
        if not result: return []
        result = self._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        if resp_ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="getParticipants")
            
        users = []
        pos = 0
        needle = struct.pack("<I", USER_CTOR)
        while True:
            pos = result.find(needle, pos)
            if pos == -1: break
            try:
                offset = pos + 4 + 8
                user_id = struct.unpack("<q", result[offset:offset+8])[0]
                users.append(user_id)
            except Exception: pass
            pos += 4
            
        return list(set(users))

    async def get_full_channel(self, peer_id):
        if not self._is_running: raise JetraError("Client not started.")
        channel_input = await self._get_channel_input(peer_id)
        
        body = struct.pack("<I", GET_FULL_CHANNEL_ID) + channel_input
        
        result = await self.client.send_request(wrap_init_connection(body))
        if not result: return None
        result = self._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        if resp_ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="getFullChannel")
            
        channels = []
        pos = 0
        needle = struct.pack("<I", CHANNEL_CTOR)
        while True:
            pos = result.find(needle, pos)
            if pos == -1: break
            try:
                offset = pos + 4 + 8
                channel_id = struct.unpack("<q", result[offset:offset+8])[0]
                offset += 16
                title_len = result[offset]
                offset += 1
                title = result[offset:offset+title_len].decode('utf-8', errors='ignore')
                channels.append({"channel_id": channel_id, "title": title})
            except Exception: pass
            pos += 4
        return channels

    async def leave_channel(self, peer_id):
        if not self._is_running: raise JetraError("Client not started.")
        channel_input = await self._get_channel_input(peer_id)
        
        body = struct.pack("<I", LEAVE_CHANNEL_ID) + channel_input
        
        result = await self.client.send_request(wrap_init_connection(body))
        if not result: return False
        result = self._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        if resp_ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="leaveChannel")
        return True

    async def resolve_username(self, username):
        if not self._is_running:
            raise JetraError("Client not started.")
            
        clean_username = username.replace("@", "").strip()
        if not clean_username:
            raise ValueError("Username cannot be empty")

        body = (
            struct.pack("<I", CONTACTS_SEARCH_ID) +
            self._tl_string(clean_username) +
            struct.pack("<i", 10)
        )
        
        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise JetraConnectionError("No response from contacts.search")
            
        result = self._unwrap_gzip(result)
        resp_ctor = struct.unpack("<I", result[:4])[0]
        if resp_ctor == RPC_ERROR:
            raise JetraRPCError(f"Server error: {self._parse_rpc_error(result)}", method="contacts.search")
            
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
        
        return None

    def _unwrap_gzip(self, result):
        if len(result) < 4:
            return result
        if struct.unpack('<I', result[:4])[0] == GZIP_PACKED:
            offset = 4
            if result[offset] < 0xFE:
                length = result[offset]
                offset += 1
            else:
                length = int.from_bytes(result[offset + 1:offset + 4], 'little')
                offset += 4
            return gzip.decompress(result[offset:offset + length])
        return result

    def _parse_rpc_error(self, data):
        if len(data) < 8:
            return "unknown"
        err_data = data[4:]
        if len(err_data) < 1:
            return "unknown"
        s_len = err_data[0]
        return err_data[1:1 + s_len].decode('utf-8', errors='ignore')

    def _tl_string(self, s):
        data = s.encode('utf-8')
        n = len(data)
        if n <= 253:
            buf = bytes([n]) + data
        else:
            buf = b'\xfe' + n.to_bytes(3, 'little') + data
        return buf + b'\x00' * ((4 - len(buf) % 4) % 4)