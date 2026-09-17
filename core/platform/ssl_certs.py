"""macOS SSL certificate patch.

The python.org installer on macOS does not bundle OpenSSL's default cert.pem,
causing CERTIFICATE_VERIFY_FAILED errors.
This is resolved by setting SSL_CERT_FILE to the certifi package path.
"""

import os

from .detect import is_macos


def ensure_ssl_certs() -> None:
    """Set SSL_CERT_FILE to certifi's path on macOS if not already set."""
    if not is_macos():
        return
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass
