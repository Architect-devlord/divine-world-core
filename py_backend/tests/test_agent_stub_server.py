import asyncio
import time
import unittest

from agent_stub_server import StubAgent


class StubAgentTests(unittest.TestCase):
    def test_stub_agent_returns_promptly_without_debug_clients(self):
        agent = StubAgent()
        start = time.perf_counter()
        reply = asyncio.run(agent.process_chat("hello"))
        elapsed = time.perf_counter() - start

        self.assertEqual(reply, agent.canned_reply)
        self.assertLess(elapsed, 1.5)


if __name__ == "__main__":
    unittest.main()
