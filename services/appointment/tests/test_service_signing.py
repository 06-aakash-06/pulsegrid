"""Signing-key parsing reuse preserves fresh JWT identities and file rotation."""
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
from appointment_service.authorization import service_token


def test_service_tokens_remain_fresh_and_follow_key_file_rotation(tmp_path):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    path=tmp_path/'synthetic.pem'
    path.write_bytes(key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
    config=SimpleNamespace(service_private_key_path=str(path),service_kid='synthetic')
    def decode(token,public):return jwt.decode(token,public,algorithms=['RS256'],issuer='pulsegrid-service:appointment',audience='pulsegrid-internal:records')
    first=decode(service_token(config,'workflow:records-read','records'),key.public_key())
    second=decode(service_token(config,'workflow:records-read','records'),key.public_key())
    assert first['jti']!=second['jti'] and first['scopes']==['workflow:records-read']
    changed=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    path.write_bytes(changed.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
    rotated=service_token(config,'workflow:records-read','records')
    assert decode(rotated,changed.public_key())['sub']=='appointment'
    with pytest.raises(jwt.InvalidSignatureError):decode(rotated,key.public_key())
