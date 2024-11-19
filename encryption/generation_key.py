# key_generator.py
import os
 
def generate_key():
    key = os.urandom(16)  # Generate a 16-byte key for AES-128
    print(f"Generated Key: {key.hex()}")  # Print the key in hexadecimal format for copying
    return key
 
if __name__ == "__main__":
    generate_key()