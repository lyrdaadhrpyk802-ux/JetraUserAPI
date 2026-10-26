# Experimental Sandbox

This folder is for new features in development.
Features here do NOT touch the main jetrauserapi library.

## Workflow

1. Develop new feature as a subclass or wrapper here.
2. Test it thoroughly with the test scripts.
3. Once 100 percent stable, merge into jetrauserapi.
4. Delete the feature folder from experimental.

## Structure

    experimental/
        reply/
            __init__.py
            reply_client.py
            test_reply.py

## How to Test

From the project root:

    cd /storage/emulated/0/JetraUserAPI
    python experimental/reply/test_reply.py

## How to Merge Into Main Library

After 100 percent success:

1. Copy methods from experimental/reply/reply_client.py
   into jetrauserapi/high_level.py.
2. Replace the existing send_message with the new one.
3. Remove the ReplyJetraClient subclass wrapper.
4. Delete experimental/reply/ folder.
5. Bump version in setup.py and pyproject.toml.
6. Add entry to CHANGELOG.md.
7. rm -rf dist/ build/ *.egg-info/
8. python -m build
9. twine upload dist/*
10. git add . && git commit -m "Add reply support" && git push
