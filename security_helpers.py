"""
security_helpers.py
Hardware ID and data obfuscation utilities.
"""

import base64
import uuid


def get_hardware_id():
    return str(uuid.getnode())


def obscure_data(data_str, salt):
    if not data_str: return ""
    if not salt: salt = "default_salt"
    salt_bytes = salt.encode('utf-8')
    data_bytes = data_str.encode('utf-8')
    obscured = bytearray()
    for i, b in enumerate(data_bytes):
        obscured.append(b ^ salt_bytes[i % len(salt_bytes)])
    return base64.b64encode(obscured).decode('utf-8')


def unobscure_data(obscured_str, salt):
    if not obscured_str: return ""
    if not salt: salt = "default_salt"
    try:
        salt_bytes = salt.encode('utf-8')
        data_bytes = base64.b64decode(obscured_str.encode('utf-8'))
        out = bytearray()
        for i, b in enumerate(data_bytes):
            out.append(b ^ salt_bytes[i % len(salt_bytes)])
        return out.decode('utf-8')
    except:
        return ""
