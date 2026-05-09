"""Telegram handler modules.

conversation.py    — wizard flow (/start → mode → links → /done → /yes)
dispatch_flow.py   — shared gate-protected dispatch helper (gated_dispatch)
shortcuts.py       — /q one-shot quick dispatch
retry.py           — /retry replay last dispatch
callbacks.py       — inline-button callback handlers (quick:*, retry:*, confirm:*, mode:*)
help.py            — /help
status.py          — /status (quota + lock state)
version.py         — /version (bot metadata)
error.py           — global error boundary
"""
