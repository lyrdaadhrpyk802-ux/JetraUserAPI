import asyncio
import struct
import gzip
import hashlib
import datetime
import random
import json
import os
import time

from jetrauserapi.client import JetraClient as LowLevelClient, wrap_init_connection, aes_ige_decrypt
from jetrauserapi.session import JetraSession
from jetrauserapi.message import Message
from jetrauserapi.database import Database


INPUT_PEER_USER = 0xDDE8A54C
INPUT_PEER_SELF = 0x7DA07EC9
INPUT_PEER_CHANNEL = 0x27BCBBFC

PEER_USER = 0x59511722
PEER_CHANNEL = 0xA2A5371E

MSG_CTOR_JETRA = 0x7600B9D3
SERVICE_MSG_CTOR_JETRA = 0x7A800E0A

SEND_MESSAGE_ID = 0xFEF48F62
GET_DIALOGS_ID = 0xA0F4CB4F
GET_STATE_ID = 0xEDD4882A

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

        # Lock for WebSocket recv() to prevent concurrency
        self._recv_lock = asyncio.Lock()

        client_ref = self.client

        def _patched_pack_msg_id():
            client_ref._msg_counter = getattr(client_ref, '_msg_counter', 0) + 1
            current_time = int(time.time())
            msg_id = (current_time << 32) | (client_ref._msg_counter << 2)
            return struct.pack("<Q", msg_id)

        self.client._pack_msg_id = _patched_pack_msg_id

        # Patch send_request to use the lock
        original_send_request = self.client.send_request
        client_ref_for_patch = self

        async def _patched_send_request(method_bytes):
            async with client_ref_for_patch._recv_lock:
                return await original_send_request(method_bytes)

        self.client.send_request = _patched_send_request

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
            raise Exception("Not logged in. Please run login.py first.")

        self._is_running = True
        self._listen_task = asyncio.create_task(self._main_loop())

        if wait_ready:
            try:
                await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                raise Exception(f"Client did not become ready within {timeout}s")

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
                # Use lock with short timeout to avoid blocking send_request
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
                    raise Exception("WebSocket closed")
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
            else:
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

            text = ""
            try:
                text_len = data[offset]
                text = data[offset + 1:offset + 1 + text_len].decode('utf-8', errors='ignore')
            except:
                pass

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
            )
        except Exception as e:
            print(f"Failed to parse message: {e}")
            return None

    async def send_message(self, peer_id, text, peer_type=None):
        if not self._is_running:
            raise Exception("Client is not started. Call await client.start() first.")

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

        random_id = random.getrandbits(63)
        body = (
            struct.pack("<I", SEND_MESSAGE_ID) +
            struct.pack("<I", 0) +
            input_peer +
            self._tl_string(text) +
            struct.pack("<q", random_id)
        )

        result = await self.client.send_request(wrap_init_connection(body))
        if not result:
            raise Exception("No response from sendMessage")

        result = self._unwrap_gzip(result)
        ctor = struct.unpack('<I', result[:4])[0]
        if ctor == RPC_ERROR:
            raise Exception(f"Server error: {self._parse_rpc_error(result)}")

        sent_msg = Message(
            msg_id=0,
            from_id=self.session.user_id,
            peer_id=peer_id,
            peer_type=peer_type,
            date=int(datetime.datetime.now().timestamp()),
            text=text,
        )
        self.db.save_message(sent_msg)
        return True

    async def send_to_saved(self, text):
        if not self._is_running:
            raise Exception("Client is not started.")

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
            raise Exception("No response from sendMessage")
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

        CHANNEL_CTOR = 0xD49F34C6
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

        USER_CTOR = 0xB1B8CC83
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

                self.db.save_dialog(user_id, 'user', f'User {user_id}', access_hash)
                count += 1
            except:
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
