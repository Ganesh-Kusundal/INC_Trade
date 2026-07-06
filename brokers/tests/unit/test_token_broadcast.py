"""Tests for token broadcast system."""

from __future__ import annotations

import gc

from brokers.adapters.dhan.token_broadcast import TokenBroadcast, TokenReceiverRef


class TestTokenBroadcast:
    def test_register_and_broadcast(self):
        broadcast = TokenBroadcast()
        received = []
        broadcast.register_receiver(lambda token: received.append(token))
        delivered = broadcast.broadcast("new-token")
        assert delivered == 1
        assert received == ["new-token"]

    def test_multiple_receivers(self):
        broadcast = TokenBroadcast()
        received1 = []
        received2 = []
        broadcast.register_receiver(lambda t: received1.append(t))
        broadcast.register_receiver(lambda t: received2.append(t))
        delivered = broadcast.broadcast("token")
        assert delivered == 2
        assert received1 == ["token"]
        assert received2 == ["token"]

    def test_idempotent_registration(self):
        broadcast = TokenBroadcast()
        received = []

        def receiver(token):
            received.append(token)

        broadcast.register_receiver(receiver)
        broadcast.register_receiver(receiver)
        assert broadcast.receiver_count == 1

    def test_unregister(self):
        broadcast = TokenBroadcast()
        received = []

        def receiver(token):
            received.append(token)

        broadcast.register_receiver(receiver)
        assert broadcast.receiver_count == 1
        removed = broadcast.unregister_receiver(receiver)
        assert removed
        assert broadcast.receiver_count == 0

    def test_broadcast_isolates_failures(self):
        broadcast = TokenBroadcast()
        good_received = []

        def bad_receiver(token):
            raise ValueError("oops")

        def good_receiver(token):
            good_received.append(token)

        broadcast.register_receiver(bad_receiver)
        broadcast.register_receiver(good_receiver)
        delivered = broadcast.broadcast("token")
        assert delivered == 1
        assert good_received == ["token"]

    def test_dead_ref_cleanup(self):
        broadcast = TokenBroadcast()

        class Receiver:
            def on_token(self, token):
                pass

        receiver_obj = Receiver()
        broadcast.register_receiver(receiver_obj.on_token)
        assert broadcast.receiver_count == 1
        del receiver_obj
        gc.collect()
        assert broadcast.receiver_count == 0

    def test_refresh_metrics(self):
        broadcast = TokenBroadcast()
        received = []
        broadcast.register_receiver(lambda t: received.append(t))
        broadcast.broadcast("token1")
        broadcast.broadcast("token2")
        metrics = broadcast.token_refresh_metrics
        assert metrics["refresh_count"] == 2
        assert metrics["receiver_count"] == 1
        assert metrics["error_count"] == 0

    def test_error_count_on_failure(self):
        broadcast = TokenBroadcast()

        def bad_receiver(token):
            raise ValueError("oops")

        broadcast.register_receiver(bad_receiver)
        broadcast.broadcast("token")
        assert broadcast.token_refresh_metrics["error_count"] == 1


class TestTokenReceiverRef:
    def test_plain_function(self):
        def receiver(token):
            pass

        ref = TokenReceiverRef(receiver)
        assert ref.deref() is receiver

    def test_equality(self):
        def receiver(token):
            pass

        ref1 = TokenReceiverRef(receiver)
        ref2 = TokenReceiverRef(receiver)
        assert ref1 == ref2

    def test_hash(self):
        def receiver(token):
            pass

        ref1 = TokenReceiverRef(receiver)
        ref2 = TokenReceiverRef(receiver)
        assert hash(ref1) == hash(ref2)
