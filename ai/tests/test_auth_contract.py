"""Adversarial access-token tests use real signatures and the real auth dependency."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import time
import unittest
import uuid

from runtime_fixture import access_claims
from fastapi.testclient import TestClient
from jose import jwt
from app.config import SECRET_KEY_BYTES
from app.main import app
from app.common.db_session import Base, engine, SessionLocal
from app.common.models import User, RoleEnum


def encode(claims, key=SECRET_KEY_BYTES, algorithm="HS256"):
    return jwt.encode(claims, key, algorithm=algorithm)


def raw_token(payload, header='{"alg":"HS256"}'):
    def segment(value):
        return base64.urlsafe_b64encode(value.encode()).rstrip(b"=").decode()
    signed = segment(header) + "." + segment(payload)
    signature = hmac.new(SECRET_KEY_BYTES, signed.encode(), hashlib.sha256).digest()
    return signed + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


class AccessTokenContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            db.add(User(id=102, name="Synthetic auth contract student", role=RoleEnum.STUDENT))
            db.commit()
        cls.client = TestClient(app)

    def request(self, token):
        return self.client.get("/users/users/me", headers={"Authorization": "Bearer " + token})

    def assert_denied(self, token):
        response = self.request(token)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Could not validate credentials"})
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    def test_valid_access_token_and_string_or_singleton_audience(self):
        for audience in ("dodream-api", ["dodream-api"]):
            with self.subTest(audience_form=type(audience).__name__):
                response = self.request(encode(access_claims("102", aud=audience)))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["id"], 102)

    def test_refresh_token_denied_on_protected_route(self):
        self.assert_denied(encode(access_claims("102", token_use="refresh")))

    def test_legacy_token_denied(self):
        self.assert_denied(encode({"sub": "102", "iss": "dodream", "exp": int(time.time()) + 60, "role": "STUDENT"}))

    def test_every_required_claim_is_required(self):
        for field in ("sub", "iss", "aud", "token_use", "jti", "role", "iat", "nbf", "exp"):
            with self.subTest(missing_claim=field):
                claims = access_claims("102")
                claims.pop(field)
                self.assert_denied(encode(claims))

    def test_wrong_signature_and_algorithms_rejected(self):
        self.assert_denied(encode(access_claims("102"), key=secrets.token_bytes(64)))
        for algorithm in ("HS384", "HS512"):
            with self.subTest(algorithm=algorithm):
                self.assert_denied(encode(access_claims("102"), algorithm=algorithm))
        self.assert_denied(raw_token(json.dumps(access_claims("102")), header='{"alg":"none"}'))

    def test_wrong_issuer_audience_and_kind_rejected(self):
        for field, values in {
            "iss": ("another-issuer", "", None, 1),
            "aud": ("another-api", [], ["dodream-api", "another-api"], ["dodream-api", "dodream-api"], None, 1),
            "token_use": ("ACCESS", "", None, 1),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_denied(encode(access_claims("102", **{field: value})))

    def test_subject_and_role_strict_types_and_ranges(self):
        for field, values in {
            "sub": (102, 0, True, "0", "-1", "+102", "0102", " 102", "102 ", "9223372036854775808", None, "abc"),
            "role": (None, "ADMIN", "student", 1, ["STUDENT"]),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_denied(encode({**access_claims("102"), field: value}))

    def test_jti_must_be_canonical_lowercase_uuid(self):
        valid = str(uuid.uuid4())
        for value in (None, "", 10, valid.upper(), valid.replace("-", ""), "not-a-uuid"):
            with self.subTest(value_type=type(value).__name__):
                self.assert_denied(encode(access_claims("102", jti=value)))

    def test_optional_name_rejects_null_blank_and_nonstring(self):
        for value in (None, "", " \t", 3, [], {}):
            with self.subTest(value_type=type(value).__name__):
                self.assert_denied(encode(access_claims("102", name=value)))
        self.assertEqual(self.request(encode(access_claims("102", name="Synthetic"))).status_code, 200)

    def test_numeric_dates_reject_coercion_and_out_of_range(self):
        for field in ("iat", "nbf", "exp"):
            for value in (str(int(time.time())), float(int(time.time())), True, None, [], {}, 0, -1, 253402300800):
                with self.subTest(field=field, value_type=type(value).__name__):
                    self.assert_denied(encode(access_claims("102", **{field: value})))
        for value in (float("nan"), float("inf"), float("-inf")):
            self.assert_denied(encode(access_claims("102", exp=value)))

    def test_expired_future_and_inconsistent_times_rejected(self):
        now = int(time.time())
        for times in (
            {"iat": now - 100, "nbf": now - 100, "exp": now - 6},
            {"iat": now + 6, "nbf": now + 6, "exp": now + 60},
            {"iat": now, "nbf": now + 6, "exp": now + 60},
            {"iat": now, "nbf": now - 1, "exp": now + 60},
            {"iat": now, "nbf": now, "exp": now},
        ):
            self.assert_denied(encode(access_claims("102", **times)))

    def test_five_second_skew_and_maximum_access_lifetime(self):
        now = int(time.time())
        for times in (
            {"iat": now + 3, "nbf": now + 3, "exp": now + 60},
            {"iat": now - 100, "nbf": now - 100, "exp": now - 2},
            {"iat": now, "nbf": now, "exp": now + 900},
        ):
            self.assertEqual(self.request(encode(access_claims("102", **times))).status_code, 200)
        self.assert_denied(encode(access_claims("102", exp=now + 901)))

    def test_compact_token_segments_must_be_unpadded_base64url(self):
        token = encode(access_claims("102"))
        header, payload, signature = token.split(".")
        padded = header + "=." + payload
        mac = hmac.new(SECRET_KEY_BYTES, padded.encode(), hashlib.sha256).digest()
        self.assert_denied(padded + "." + base64.urlsafe_b64encode(mac).rstrip(b"=").decode())
        for malformed in (" " + token, token + "\n", token + ".extra", token.replace(".", "..", 1)):
            self.assert_denied(malformed)

    def test_duplicate_json_and_nonobject_payload_rejected(self):
        payload = json.dumps(access_claims("102"), separators=(",", ":"))
        self.assert_denied(raw_token(payload.replace('"sub":"102"', '"sub":"1","sub":"102"')))
        self.assert_denied(raw_token(payload, header='{"alg":"HS512","alg":"HS256"}'))
        self.assert_denied(raw_token('[]'))

    def test_oversized_token_and_missing_bearer_denied(self):
        self.assert_denied("x" * 8193)
        # Hold signature, claims, compact encoding, and DB identity valid so this
        # specifically exercises the application limit instead of a syntax error.
        within_limit = encode(access_claims("102", name="x" * 5000))
        self.assertLessEqual(len(within_limit), 8192)
        self.assertEqual(self.request(within_limit).status_code, 200)
        oversized = encode(access_claims("102", name="x" * 9000))
        self.assertGreater(len(oversized), 8192)
        self.assert_denied(oversized)
        for headers in ({}, {"Authorization": "Basic invalid"}):
            response = self.client.get("/users/users/me", headers=headers)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"detail": "Could not validate credentials"})

    def test_nonexistent_user_still_requires_real_database_identity(self):
        self.assert_denied(encode(access_claims("9223372036854775807")))

    def test_invalid_runtime_key_algorithm_and_target_fail_startup(self):
        key_text = os.environ["JWT_SECRET_BASE64"]
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        # A non-zero padding bit decodes to the same bytes but is noncanonical.
        noncanonical_key = key_text[:-3] + alphabet[alphabet.index(key_text[-3]) + 1] + "=="
        malformed_configs = (
            {"JWT_SECRET_BASE64": None},
            {"JWT_SECRET_BASE64": ""},
            {"JWT_SECRET_BASE64": noncanonical_key},
            {"JWT_SECRET_BASE64": "not-base64"},
            {"JWT_SECRET_BASE64": base64.b64encode(secrets.token_bytes(16)).decode()},
            {"JWT_SECRET_BASE64": os.environ["JWT_SECRET_BASE64"] + "\n"},
            {"JWT_ALGORITHM": "HS512"},
            {"JWT_ISSUER": ""},
            {"JWT_ISSUER": "different-issuer"},
            {"JWT_AUDIENCE": ""},
            {"JWT_AUDIENCE": "different-audience"},
        )
        for changes in malformed_configs:
            with self.subTest(config_name=next(iter(changes))):
                env = {**os.environ, **changes}
                env = {key: value for key, value in env.items() if value is not None}
                result = subprocess.run([sys.executable, "-c", "import app.config"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
