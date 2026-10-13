"""
Unit Tests for MLLP Transport Framing & Buffer Unwrapping
"""

import unittest
from engine.mllp import wrap_mllp, unwrap_mllp, MLLPProtocol

class TestMLLPTransport(unittest.TestCase):
    def test_wrap_mllp(self):
        payload = "MSH|^~\\&|TEST|FAC|||20260902||ADT^A01|123|P|2.3\r"
        wrapped = wrap_mllp(payload)

        self.assertTrue(wrapped.startswith(MLLPProtocol.START_BLOCK))
        self.assertTrue(wrapped.endswith(MLLPProtocol.TRAILER))
        self.assertEqual(wrapped[1:-2].decode("utf-8"), payload)

    def test_unwrap_single_complete_frame(self):
        payload = "MSH|^~\\&|APP|FAC|||20260902||ADT^A01|001|P|2.3\r"
        packet = wrap_mllp(payload)
        messages, remaining = unwrap_mllp(packet)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0], payload)
        self.assertEqual(remaining, b"")

    def test_unwrap_multiple_frames_in_single_buffer(self):
        msg1 = "MSH|^~\\&|APP|FAC|||20260902||ADT^A01|001|P|2.3\r"
        msg2 = "MSH|^~\\&|APP|FAC|||20260902||ORM^O01|002|P|2.3\r"
        combined_packet = wrap_mllp(msg1) + wrap_mllp(msg2)

        messages, remaining = unwrap_mllp(combined_packet)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], msg1)
        self.assertEqual(messages[1], msg2)
        self.assertEqual(remaining, b"")

    def test_unwrap_partial_fragmented_frame(self):
        payload = "MSH|^~\\&|APP|FAC|||20260902||ADT^A01|001|P|2.3\r"
        full_packet = wrap_mllp(payload)

        chunk1 = full_packet[:15]
        chunk2 = full_packet[15:]

        msgs1, rem1 = unwrap_mllp(chunk1)
        self.assertEqual(len(msgs1), 0)
        self.assertEqual(rem1, chunk1)

        msgs2, rem2 = unwrap_mllp(rem1 + chunk2)
        self.assertEqual(len(msgs2), 1)
        self.assertEqual(msgs2[0], payload)
        self.assertEqual(rem2, b"")

if __name__ == "__main__":
    unittest.main()
