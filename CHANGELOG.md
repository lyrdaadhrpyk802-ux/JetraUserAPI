# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-10-25

### Added
- Initial release
- Login with phone number and OTP
- Send and receive text messages in private chats (PV)
- Send and receive text messages in groups
- Get list of dialogs (users and groups)
- Local SQLite database for message history
- Auto-reconnect on connection loss
- Event handlers (`on_message`, `on_ready`)
- Auto-detection of peer type (user vs group)
- 10 ready-to-run examples

### Known Limitations
- Sending media is blocked by the server
- Deleting messages is blocked by the server
- Group management is blocked by the server
- Message history from server is blocked
