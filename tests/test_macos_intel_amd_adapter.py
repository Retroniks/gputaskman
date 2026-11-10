"""Independent Intel AMD adapter discovery regression tests."""
import unittest
from unittest.mock import patch
from gputaskman.macos_intel_amd_adapter import from_displays, _vram_bytes


class IntelAmdAdapterTests(unittest.TestCase):
    def test_rx580(self):
        found = from_displays([{'sppci_model': 'AMD Radeon RX 580', 'spdisplays_vendor': 'AMD (0x1002)', 'spdisplays_vram': '8 GB'}])
        self.assertEqual(found.vendor_id, 0x1002)
        self.assertEqual(found.dedicated_vram, 8 * 1024 ** 3)
        self.assertIn('RX 580', found.name)

    def test_no_false_positive_apple(self):
        self.assertIsNone(from_displays([{'sppci_model': 'Apple M4 GPU'}]))

    def test_megabytes(self):
        self.assertEqual(_vram_bytes('8192 MB'), 8 * 1024 ** 3)

    def test_native_enumeration_uses_amd(self):
        from gputaskman.macos import enumerate_adapters
        adapter = from_displays([{'sppci_model': 'Radeon RX 580', 'spdisplays_vram': '8 GB'}])
        with patch('gputaskman.macos_intel_amd_adapter.intel_amd_adapter', return_value=adapter):
            got=enumerate_adapters()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].vendor_id, 0x1002)


if __name__ == '__main__':
    unittest.main()
