"""S24 slice 1: network registry storage helpers."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


def network_key(validated: dict[str, Any]) -> str:
    """Derive a non-empty registry key from a validated document."""
    networks = validated.get("networks")
    name = ""
    if isinstance(networks, list) and networks and isinstance(networks[0], dict):
        raw = networks[0].get("name")
        if isinstance(raw, str):
            name = raw.strip()
    return (name or "network")[:500]


def next_version(conn: Connection, network_id: UUID) -> int:
    """Return the next immutable version number for a network."""
    current = conn.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) FROM network_versions "
            "WHERE network_id = :id"
        ),
        {"id": network_id},
    ).scalar()
    return int(current or 0) + 1


def store_network(conn: Connection, key: str, created_by: str | None) -> Any:
    """Insert one network row; return the stored row."""
    return (
        conn.execute(
            text(
                "INSERT INTO networks (key, created_by) "
                "VALUES (:key, CAST(:by AS uuid)) RETURNING *"
            ),
            {"key": key, "by": created_by},
        )
        .mappings()
        .one()
    )


def store_version(
    conn: Connection,
    network_id: UUID,
    version: int,
    xml_bytes: bytes,
    sha256: str,
    byte_count: int,
    xsd_report: dict[str, Any],
    semantic_report: dict[str, Any],
    admission_report: dict[str, Any],
    created_by: str | None,
) -> Any:
    """Insert one immutable network version; return the stored row."""
    return (
        conn.execute(
            text(
                "INSERT INTO network_versions "
                "(network_id, version, xml, sha256, byte_count, "
                " xsd_report, semantic_report, admission_report, created_by) "
                "VALUES (:nid, :v, :xml, :sha, :n, "
                " CAST(:xsd AS jsonb), CAST(:sem AS jsonb), CAST(:adm AS jsonb), "
                " CAST(:by AS uuid)) RETURNING *"
            ),
            {
                "nid": network_id,
                "v": version,
                "xml": xml_bytes,
                "sha": sha256,
                "n": byte_count,
                "xsd": json.dumps(xsd_report),
                "sem": json.dumps(semantic_report),
                "adm": json.dumps(admission_report),
                "by": created_by,
            },
        )
        .mappings()
        .one()
    )


def load_network(conn: Connection, network_id: UUID) -> Any | None:
    """Return one network row, or None when missing."""
    return (
        conn.execute(text("SELECT * FROM networks WHERE id = :id"), {"id": network_id})
        .mappings()
        .first()
    )


def load_versions(conn: Connection, network_id: UUID) -> list[Any]:
    """Return stored versions for a network, ordered by version."""
    return list(
        conn.execute(
            text(
                "SELECT * FROM network_versions WHERE network_id = :id ORDER BY version"
            ),
            {"id": network_id},
        )
        .mappings()
        .all()
    )


def load_version(conn: Connection, version_id: UUID) -> Any | None:
    """Return one stored version row, or None when missing."""
    return (
        conn.execute(
            text("SELECT * FROM network_versions WHERE id = :id"), {"id": version_id}
        )
        .mappings()
        .first()
    )
