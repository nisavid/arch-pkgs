"""Authenticate local service peers before sending Open WebUI credentials.

Imported independently of open_webui so validation precedes application imports.
The operator owns the CA files and their parent directories; a service must never
be able to replace its client's trust anchor. No validation error contains a URL,
because the Redis URL contains its password.
"""

import os
import ssl
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class ServiceTLSConfigurationError(ValueError):
    pass


def _ca_path(name):
    value = os.environ.get(name, "")
    if not value or not Path(value).is_absolute() or not Path(value).is_file():
        raise ServiceTLSConfigurationError(f"{name} must name a readable absolute CA file")
    try:
        # Explicit cafile prevents SSL_CERT_FILE, SSL_CERT_DIR, and system roots
        # from adding unrelated authorities to this service's trust store.
        context = ssl.create_default_context(cafile=value)
    except (OSError, ssl.SSLError):
        raise ServiceTLSConfigurationError(f"{name} must contain a readable PEM certificate") from None
    return value, context


def _url(value, scheme, name):
    try:
        if not value or any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError
        parsed = urlsplit(value)
        if parsed.scheme != scheme or parsed.hostname != "127.0.0.1" or parsed.fragment:
            raise ValueError
        # Validate the port here, without allowing urllib's diagnostic to echo
        # any part of the credential-bearing input.
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
    except ValueError:
        raise ServiceTLSConfigurationError(f"{name} must use {scheme} on 127.0.0.1") from None
    return parsed


def qdrant_client_options(uri, *, prefer_grpc=False):
    if prefer_grpc:
        raise ServiceTLSConfigurationError("QDRANT_PREFER_GRPC is unsupported by the packaged TLS boundary")
    parsed = _url(uri, "https", "QDRANT_URI")
    if parsed.username is not None or parsed.password is not None or parsed.query:
        raise ServiceTLSConfigurationError("QDRANT_URI must not contain credentials or query parameters")
    _, context = _ca_path("QDRANT_CA_CERT")
    return {
        "url": uri,
        "https": True,
        "prefer_grpc": False,
        "verify": context,
        "trust_env": False,
        "follow_redirects": False,
    }


def redis_url(value):
    parsed = _url(value, "rediss", "REDIS_URL")
    ca_path, _ = _ca_path("VALKEY_CA_CERT")
    if parsed.path not in ("", "/") and not parsed.path[1:].isdigit():
        raise ServiceTLSConfigurationError("REDIS_URL must specify a numeric database")
    required = {
        "ssl_cert_reqs": "required",
        "ssl_check_hostname": "true",
        "ssl_ca_certs": ca_path,
    }
    # Query values override kwargs in every redis-py from_url caller, including
    # starsessions and Socket.IO. Permit only these known connection tunables;
    # alternate hosts, trust sources, connection classes, and SSL flags fail.
    allowed = {
        "db", "socket_timeout", "socket_connect_timeout", "health_check_interval",
        "socket_keepalive", "decode_responses", "encoding", "encoding_errors",
        "client_name", "protocol", "max_connections", "retry_on_timeout",
    }
    query = {}
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise ServiceTLSConfigurationError("REDIS_URL contains an invalid query") from None
    for key, value in pairs:
        if key in query or key not in allowed | required.keys():
            raise ServiceTLSConfigurationError("REDIS_URL contains an unsupported or duplicate query option")
        if key in required and value != required[key]:
            raise ServiceTLSConfigurationError("REDIS_URL attempts to override required TLS verification")
        query[key] = value
    query.update(required)
    return urlunsplit(parsed._replace(query=urlencode(query)))


def configure_environment():
    """Fail closed, then give every downstream Redis consumer the same TLS URL."""
    for name in ("REDIS_SENTINEL_HOSTS", "WEBSOCKET_SENTINEL_HOSTS", "WEBSOCKET_REDIS_OPTIONS"):
        if os.environ.get(name, "").strip():
            raise ServiceTLSConfigurationError(f"{name} is unsupported by the packaged TLS boundary")
    for name in ("REDIS_CLUSTER", "WEBSOCKET_REDIS_CLUSTER", "QDRANT_PREFER_GRPC"):
        if os.environ.get(name, "false").lower() != "false":
            raise ServiceTLSConfigurationError(f"{name} must be false for the packaged TLS boundary")
    qdrant_client_options(os.environ.get("QDRANT_URI", ""))
    canonical = redis_url(os.environ.get("REDIS_URL", ""))
    os.environ["REDIS_URL"] = canonical
    os.environ["WEBSOCKET_REDIS_URL"] = canonical


def configure_or_exit():
    try:
        configure_environment()
    except ServiceTLSConfigurationError as error:
        print(f"open-webui: {error}", file=sys.stderr)
        raise SystemExit(78) from None
