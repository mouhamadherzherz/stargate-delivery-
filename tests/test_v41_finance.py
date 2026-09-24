import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.backup_service import create_backup, restore_backup, verify_backup


class V41FinanceTests(unittest.TestCase):
    def test_backup_manifest_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'source.db')
            restored = os.path.join(directory, 'restored.db')
            backup_dir = os.path.join(directory, 'backups')
            connection = sqlite3.connect(source)
            connection.execute('CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)')
            connection.execute("INSERT INTO items (name) VALUES ('verified')")
            connection.commit()
            connection.close()
            manifest = create_backup(source, backup_dir)
            archive = os.path.join(backup_dir, manifest['file'])
            self.assertTrue(verify_backup(archive))
            restore_backup(archive, restored)
            check = sqlite3.connect(restored)
            self.assertEqual(check.execute('SELECT name FROM items').fetchone()[0], 'verified')
            check.close()

    def test_tampered_backup_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'source.db')
            backup_dir = os.path.join(directory, 'backups')
            sqlite3.connect(source).close()
            manifest = create_backup(source, backup_dir)
            archive = os.path.join(backup_dir, manifest['file'])
            with open(archive, 'ab') as stream:
                stream.write(b'tamper')
            self.assertFalse(verify_backup(archive))


if __name__ == '__main__':
    unittest.main()
