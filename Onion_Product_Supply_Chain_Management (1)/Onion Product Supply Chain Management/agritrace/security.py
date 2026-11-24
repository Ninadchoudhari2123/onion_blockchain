import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .blockchain import canonical_json

ROLE_PERMISSIONS = {
    # A farmer may split or merge a batch only while they are its current holder.
    "FARMER": {
        "BATCH_CREATED", "HARVESTED", "OWNERSHIP_TRANSFER",
        "BATCH_SPLIT", "BATCH_MERGED",
    },
    "COLLECTION_CENTER": {
        "RECEIVED", "QUALITY_INSPECTED", "OWNERSHIP_TRANSFER",
        "BATCH_SPLIT", "BATCH_MERGED"
    },
    "TRANSPORTER": {"PICKED_UP", "DELIVERED", "OWNERSHIP_TRANSFER"},
    "WHOLESALER": {
        "RECEIVED", "OWNERSHIP_TRANSFER", "DISPATCHED",
        "BATCH_SPLIT", "BATCH_MERGED"
    },
    "RETAILER": {"RECEIVED"},
}


def public_key_pem(public_key):
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def load_or_create_actor(actor_id, role, key_dir):
    key_dir = Path(key_dir)
    key_dir.mkdir(parents=True, exist_ok=True)
    key_file = key_dir / f"{actor_id}_private.pem"

    if key_file.exists():
        private_key = serialization.load_pem_private_key(
            key_file.read_bytes(),
            password=None,
        )
    else:
        private_key = Ed25519PrivateKey.generate()
        key_file.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    return {
        "actor_id": actor_id,
        "role": role,
        "private_key": private_key,
        "public_key": private_key.public_key(),
        "public_key_pem": public_key_pem(private_key.public_key()),
    }


def sign_transaction(transaction, private_key):
    payload = {key: value for key, value in transaction.items() if key != "signature"}
    signature = private_key.sign(canonical_json(payload).encode("utf-8"))
    signed_transaction = dict(payload)
    signed_transaction["signature"] = base64.b64encode(signature).decode("ascii")
    return signed_transaction


def verify_transaction_signature(transaction, public_key):
    if not public_key or not transaction.get("signature"):
        return False
    payload = {key: value for key, value in transaction.items() if key != "signature"}
    try:
        signature = base64.b64decode(transaction["signature"], validate=True)
        public_key.verify(signature, canonical_json(payload).encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def create_transaction(actors, actor_id, batch_id, event_type, quantity_kg,
                       from_state="", to_state="", to_actor="", details=None):
    if actor_id not in actors:
        raise ValueError("Participant not registered")
    payload = {
        "transaction_id": f"TXN-{uuid4()}",
        "batch_id": batch_id,
        "actor_id": actor_id,
        "event_type": event_type,
        "from_actor": actor_id,
        "to_actor": to_actor,
        "from_state": from_state,
        "to_state": to_state,
        "quantity_kg": float(quantity_kg),
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "record_origin": "DEMO",
    }
    return sign_transaction(payload, actors[actor_id]["private_key"])
