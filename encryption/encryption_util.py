from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.hazmat.backends import default_backend
import os
import base64
 
# Hardcoded encryption key (shared across all nodes, ensure 32 bytes for AES-256)
HARD_CODED_KEY = b"52eb0370b712e93c8bc1771579b1cbe7"  # Replace with your secure 32-byte key
 
def encrypt_message(plain_text):
    """
    Encrypts a plain text message using AES-256 in CBC mode.
    """
    iv = os.urandom(16)  # Generate a random IV
    cipher = Cipher(algorithms.AES(HARD_CODED_KEY), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = PKCS7(algorithms.AES.block_size).padder()
 
    padded_data = padder.update(plain_text.encode()) + padder.finalize()
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
 
    # Concatenate IV with encrypted data and encode in base64
    return base64.b64encode(iv + encrypted_data).decode()
 
def decrypt_message(encrypted_text):
    """
    Decrypts a base64 encoded encrypted message using AES-256 in CBC mode.
    """
    encrypted_data = base64.b64decode(encrypted_text)
    iv = encrypted_data[:16]  # Extract the IV
    cipher = Cipher(algorithms.AES(HARD_CODED_KEY), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    unpadder = PKCS7(algorithms.AES.block_size).unpadder()
 
    decrypted_padded_data = decryptor.update(encrypted_data[16:]) + decryptor.finalize()
    decrypted_data = unpadder.update(decrypted_padded_data) + unpadder.finalize()
 
    return decrypted_data.decode()
