import unittest
from gputaskman.macos import keep_gpu_client


class IdleClientVisibilityTests(unittest.TestCase):
    def test_intel_amd_idle_client_kept(self):
        self.assertTrue(keep_gpu_client(True, 0.0, "OtherUserApp"))

    def test_intel_amd_unknown_gpu_kept(self):
        self.assertTrue(keep_gpu_client(True, None, "OtherUserApp"))

    def test_apple_idle_client_still_hidden(self):
        self.assertFalse(keep_gpu_client(False, 0.0, "OtherUserApp"))

    def test_apple_busy_client_kept(self):
        self.assertTrue(keep_gpu_client(False, 3.2, "OtherUserApp"))

    def test_compositor_retained(self):
        self.assertTrue(keep_gpu_client(False, None, "WindowServer"))


if __name__ == "__main__":
    unittest.main()
