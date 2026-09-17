"""Hailo GenAI chat route registration facade."""

from hailo_chat_routes_conversations import register_conversation_routes
from hailo_chat_routes_send import register_send_routes


def register_chat_routes(bp):
    register_conversation_routes(bp)
    register_send_routes(bp)
