import json
import os
import pickle

from django.conf import settings
from django.test import TestCase

from pipeline.secure import SecureString, encrypt_string, get_fernet


class SecureStringTest(TestCase):

    def setUp(self):
        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        get_fernet.cache_clear()

    def tearDown(self):
        get_fernet.cache_clear()

    def test_encrypt_decrypt_round_trip(self):
        enc = encrypt_string("sk-test-key-12345678")
        ss = SecureString(enc)
        self.assertEqual(ss.decrypt(), "sk-test-key-12345678")

    def test_str_returns_mask(self):
        ss = SecureString(encrypt_string("secret"))
        self.assertEqual(str(ss), "••••••••")

    def test_repr_returns_mask(self):
        ss = SecureString(encrypt_string("secret"))
        self.assertEqual(repr(ss), "SecureString(••••)")

    def test_reduce_raises(self):
        ss = SecureString(encrypt_string("secret"))
        with self.assertRaises(TypeError):
            pickle.dumps(ss)

    def test_reduce_ex_raises(self):
        ss = SecureString(encrypt_string("secret"))
        with self.assertRaises(TypeError):
            ss.__reduce_ex__(2)

    def test_json_dumps_raises(self):
        ss = SecureString(encrypt_string("secret"))
        with self.assertRaises(TypeError):
            json.dumps(ss)

    def test_bool_true(self):
        ss = SecureString(encrypt_string("secret"))
        self.assertTrue(bool(ss))

    def test_bool_false_for_empty_bytes(self):
        ss = SecureString(b"")
        self.assertFalse(bool(ss))

    def test_len_raises(self):
        ss = SecureString(encrypt_string("secret"))
        with self.assertRaises(TypeError):
            len(ss)

    def test_eq_same_encrypted_bytes(self):
        enc = encrypt_string("secret")
        self.assertEqual(SecureString(enc), SecureString(enc))

    def test_eq_plaintext_raises(self):
        ss = SecureString(encrypt_string("secret"))
        with self.assertRaises(TypeError):
            ss == "secret"

    def test_hash_consistent(self):
        enc = encrypt_string("secret")
        self.assertEqual(hash(SecureString(enc)), hash(SecureString(enc)))

    def test_stack_trace_hides_key(self):
        ss = SecureString(encrypt_string("sk-super-secret-key-123"))
        try:
            raise ValueError(f"failed with key={ss!r}")
        except ValueError as e:
            self.assertIn("SecureString(••••)", str(e))
            self.assertNotIn("sk-super-secret", str(e))
