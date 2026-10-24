import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import package_portable as packaging


class PackagingTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'dist'/'Projectunio-Portable-Windows-x64'
        names=packaging.FILES+['runtime/ffmpeg.exe','runtime/ffprobe.exe','runtime/FFmpeg-LICENSE.txt','runtime/python/python.exe','runtime/python/pythonw.exe','runtime/python/LICENSE.txt']
        for name in names:
            target=source/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(b'fixture')
        (root/'PORTABLE-LIRE-MOI.txt').write_text('Portable sans installeur',encoding='utf-8')
        for name in ('recovery/private.json','logs/private.log','runtime/python/__pycache__/ignored.pyc'):
            target=source/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_text('private')
        return source

    def test_zip_is_versioned_clean_and_has_matching_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=self.fixture(root)
            with patch.object(packaging,'ROOT',root),patch.object(packaging,'SOURCE',source):target=packaging.package('0.1.0')
            self.assertEqual(target.name,'Projectunio-0.1.0-Portable-Windows-x64.zip')
            with zipfile.ZipFile(target) as archive:
                names=archive.namelist(); self.assertIn('Projectunio-Portable/Projectunio.exe',names)
                self.assertFalse(any('private' in name or '__pycache__' in name for name in names)); self.assertIsNone(archive.testzip())
            checksum=target.with_suffix('.zip.sha256').read_text().split()[0]
            self.assertEqual(checksum,hashlib.sha256(target.read_bytes()).hexdigest())

    def test_missing_runtime_preserves_previous_distribution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=self.fixture(root); target=root/'dist'/'Projectunio-0.1.0-Portable-Windows-x64.zip'; target.write_bytes(b'previous')
            (source/'runtime'/'ffprobe.exe').unlink()
            with patch.object(packaging,'ROOT',root),patch.object(packaging,'SOURCE',source):
                with self.assertRaises(FileNotFoundError):packaging.package('0.1.0')
            self.assertEqual(target.read_bytes(),b'previous')

    def test_version_cannot_escape_distribution_folder(self):
        for version in ('../other','C:/other','0.1.0/../../other'):
            with self.subTest(version=version),self.assertRaises(ValueError):packaging.package(version)


if __name__=='__main__':unittest.main()
