"""Private downloads must preserve arbitrary binary bytes through the JSON API."""
import base64
import json
import unittest
from unittest.mock import patch

import install


class PrivateDownloadTests(unittest.TestCase):
    def source(self):
        with patch.object(install, 'gh_get', return_value=json.dumps({'sha': 'a' * 40}).encode()):
            return install.Source(None, 'owner/repo', 'main', True)

    def test_binary_blob_is_downloaded_as_base64_json_without_text_transformation(self):
        source = self.source()
        data = b'RIFF\x00\xff\x80\x81WEBP\r\n'
        responses = [json.dumps({'sha': 'b' * 40, 'size': len(data)}).encode(),
                     json.dumps({'encoding': 'base64', 'content': base64.b64encode(data).decode(),
                                 'size': len(data)}).encode()]
        with patch.object(install, 'gh_get', side_effect=responses) as download:
            self.assertEqual(source.get('pets/test/spritesheet.webp'), data)
        self.assertEqual(download.call_args_list[0].args,
                         ('repos/owner/repo/contents/pets/test/spritesheet.webp?ref=' + 'a' * 40,))
        self.assertEqual(download.call_args_list[1].args,
                         ('repos/owner/repo/git/blobs/' + 'b' * 40,))
        self.assertGreater(download.call_args_list[1].kwargs.get('max_bytes', 0),
                           install.MAX_DOWNLOAD * 4 // 3)

    def test_blob_json_limit_allows_bounded_encoding_overhead(self):
        response = type('Response', (), {'returncode': 0, 'stdout': b'x' * 17})()
        with patch.object(install, 'MAX_DOWNLOAD', 12), patch.object(
                install.subprocess, 'run', return_value=response):
            self.assertEqual(install.gh_get('repos/owner/repo/git/blobs/' + 'b' * 40,
                                           max_bytes=24), response.stdout)

    def test_oversized_private_blob_is_rejected_before_downloading(self):
        source = self.source()
        with patch.object(install, 'gh_get', return_value=json.dumps(
                {'sha': 'b' * 40, 'size': install.MAX_DOWNLOAD + 1}).encode()) as download:
            with self.assertRaises(ValueError):
                source.get('pets/test/spritesheet.webp')
        self.assertEqual(download.call_count, 1)

    def test_invalid_base64_blob_is_rejected(self):
        source = self.source()
        responses = [json.dumps({'sha': 'b' * 40, 'size': 5}).encode(),
                     json.dumps({'encoding': 'base64', 'content': '!!!', 'size': 5}).encode()]
        with patch.object(install, 'gh_get', side_effect=responses):
            with self.assertRaises(ValueError):
                source.get('pets/test/spritesheet.webp')
