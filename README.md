# JetraUserAPI

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

A Python library for interacting with **Jetra Messenger** using user accounts.

Inspired by [Telethon](https://github.com/LonamiWebs/Telethon), JetraUserAPI provides a simple and clean API for automating Jetra Messenger.

## Features

- Login with phone number and OTP
- Send and receive text messages in private chats (PV)
- Send and receive text messages in groups
- Get list of dialogs (users and groups)
- Local SQLite database for message history
- Auto-reconnect on connection loss
- Event handlers (`on_message`, `on_ready`)
- Auto-detection of peer type (user vs group)
- Clean async/await API

## Limitations

The Jetra server blocks several operations for web clients:

- Sending media (photos, videos, files)
- Deleting messages
- Group management (ban, admin)
- Message history from server

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/JetraUserAPI.git
cd JetraUserAPI
pip install -e .
