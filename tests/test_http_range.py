import unittest

from app.services.http_range import parse_single_byte_range


class HttpRangeTests(unittest.TestCase):
    def test_open_ended_and_bounded_ranges(self):
        self.assertEqual(parse_single_byte_range("bytes=0-", 1000), (0, 999))
        self.assertEqual(parse_single_byte_range("bytes=10-19", 1000), (10, 19))

    def test_suffix_and_clamped_end_ranges(self):
        self.assertEqual(parse_single_byte_range("bytes=-100", 1000), (900, 999))
        self.assertEqual(parse_single_byte_range("bytes=900-2000", 1000), (900, 999))

    def test_invalid_or_multiple_ranges_are_rejected(self):
        for value in (
            "items=0-10",
            "bytes=1000-",
            "bytes=20-10",
            "bytes=0-1,4-5",
        ):
            with self.assertRaises(ValueError):
                parse_single_byte_range(value, 1000)


if __name__ == "__main__":
    unittest.main()
