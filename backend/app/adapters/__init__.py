"""Broker-payload adapters.

Everything in this package converts raw broker JSON into typed internal
objects. Route code must never read broker field names directly — that is how
D1 and D2 (see docs/BRIEF-BACKEND-V2.md) both shipped under a green suite.
"""
