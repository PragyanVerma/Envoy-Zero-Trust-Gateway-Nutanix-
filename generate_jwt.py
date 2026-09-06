import jwt
import datetime
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import os

def generate_keys():
    if not os.path.exists('jwt-keys'):
        os.makedirs('jwt-keys')
        
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    public_key = private_key.public_key()
    
    with open('jwt-keys/private.pem', 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
        
    with open('jwt-keys/public.pem', 'wb') as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

def create_jwt(sub):
    with open('jwt-keys/private.pem', 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None,
            backend=default_backend()
        )
        
    payload = {
        "iss": "hackathon-issuer",
        "aud": "hackathon-audience",
        "sub": sub,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=365)
    }
    
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

if __name__ == "__main__":
    if not os.path.exists('jwt-keys/private.pem'):
        generate_keys()
        
    print("--- order-service JWT ---")
    print(create_jwt("order-service"))
    print("\n--- payments-service JWT ---")
    print(create_jwt("payments-service"))
    print("\n--- suspicious-service JWT ---")
    print(create_jwt("suspicious-service"))
