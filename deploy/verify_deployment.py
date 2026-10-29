#!/usr/bin/env python3
"""Read-only PostgreSQL deployment evidence. Never prints credentials or payloads."""
import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


def json_default(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=json_default).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("before", "after"))
    parser.add_argument("--env-file", default="/opt/restaurant-cloud/.env.runtime")
    parser.add_argument("--app-dir", default="/opt/restaurant-cloud/api")
    parser.add_argument("--evidence-dir", default="/home/ubuntu/oct30-lingchen-deploy-evidence")
    args = parser.parse_args()
    evidence = Path(args.evidence_dir)
    baseline = evidence / "before.json"
    if args.mode == "before" and baseline.exists():
        raise RuntimeError("Baseline already exists; refusing to overwrite")
    if args.mode == "after" and not baseline.is_file():
        raise RuntimeError("Baseline is missing")
    from dotenv import load_dotenv
    load_dotenv(args.env_file, override=True, interpolate=False)
    sys.path.insert(0, args.app_dir)
    from app import config, database
    from sqlalchemy import text
    if database.engine.dialect.name != "postgresql":
        raise RuntimeError("This verifier requires PostgreSQL read-only transactions")
    snapshot = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload_hash_mode": "raw_postgresql_jsonb_text_no_python_float",
        "runtime_env_sha256": hashlib.sha256(Path(args.env_file).read_bytes()).hexdigest(),
        "test_login_enabled": bool(config.TEST_LOGIN_ENABLED),
    }
    # Importing app.database/config does not import main or run application startup.
    with database.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '30s'"))
            if conn.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
                raise RuntimeError("Read-only transaction not established")
            dataset_ids = list(conn.execute(text("SELECT id FROM datasets ORDER BY id")).scalars())
            digests = {key: hashlib.sha256() for key in dataset_ids}
            counts = {key: {"total": 0, "live": 0, "deleted": 0} for key in dataset_ids}
            query = """SELECT id,dataset_id,record_type,record_key,payload::text AS payload_jsonb_text,checksum,version,
                       sequence,is_deleted,created_at,updated_at
                       FROM sync_records ORDER BY dataset_id,record_type,record_key,id"""
            for mapping in conn.execute(text(query)).mappings():
                row = dict(mapping)
                key = row["dataset_id"]
                digests.setdefault(key, hashlib.sha256()).update(encoded(row) + b"\n")
                count = counts.setdefault(key, {"total": 0, "live": 0, "deleted": 0})
                count["total"] += 1
                count["deleted" if row["is_deleted"] else "live"] += 1
            snapshot["sync_records_by_dataset"] = {
                key: {**counts[key], "sha256": digests[key].hexdigest()} for key in sorted(counts)
            }
            snapshot["entry_timings_by_dataset"] = dict(conn.execute(text(
                "SELECT dataset_id,count(*) FROM entry_timings GROUP BY dataset_id ORDER BY dataset_id"
            )).all())
            snapshot["counts"] = {
                table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in ("app_users", "datasets", "sync_records", "entry_timings", "audit_logs", "inventory_name_corrections")
            }
            # Hash server JSON text; neither payloads nor password hashes are printed.
            queries = {
                "entry_timings": "SELECT row_to_json(t)::text FROM entry_timings t ORDER BY id",
                "name_corrections": "SELECT row_to_json(t)::text FROM inventory_name_corrections t ORDER BY id",
                "users": "SELECT (to_jsonb(t) - 'updated_at')::text FROM app_users t ORDER BY id",
                "datasets": "SELECT row_to_json(t)::text FROM datasets t ORDER BY id",
                "memberships": "SELECT jsonb_build_array(user_id,dataset_id,is_default)::text FROM user_dataset_memberships ORDER BY user_id,dataset_id",
                "temporary_permissions": "SELECT row_to_json(t)::text FROM temporary_permissions t ORDER BY id",
            }
            snapshot["protected_table_hashes"] = {}
            for label, query in queries.items():
                hasher = hashlib.sha256()
                for raw in conn.execute(text(query)).scalars():
                    hasher.update(raw.encode("utf-8") + b"\n")
                snapshot["protected_table_hashes"][label] = hasher.hexdigest()
            snapshot["expired_audit_logs_366_days"] = conn.execute(text(
                "SELECT count(*) FROM audit_logs WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '366 days'"
            )).scalar_one()
    database.engine.dispose()
    if args.mode == "after":
        previous = json.loads(baseline.read_text(encoding="utf-8"))
        snapshot["comparison"] = {
            "business_records_unchanged": previous["sync_records_by_dataset"] == snapshot["sync_records_by_dataset"],
            "entry_timing_counts_unchanged": previous["entry_timings_by_dataset"] == snapshot["entry_timings_by_dataset"],
            "runtime_env_unchanged": previous["runtime_env_sha256"] == snapshot["runtime_env_sha256"],
            "test_login_setting_unchanged": previous["test_login_enabled"] == snapshot["test_login_enabled"],
            "correction_rows_unchanged": previous["counts"]["inventory_name_corrections"] == snapshot["counts"]["inventory_name_corrections"],
            "audit_rows_removed": previous["counts"]["audit_logs"] - snapshot["counts"]["audit_logs"],
            "protected_tables_unchanged": previous["protected_table_hashes"] == snapshot["protected_table_hashes"],
            "account_dataset_counts_unchanged": all(previous["counts"][key] == snapshot["counts"][key] for key in ("app_users", "datasets")),
            "audit_retention_only": 0 <= previous["counts"]["audit_logs"] - snapshot["counts"]["audit_logs"] <= previous["expired_audit_logs_366_days"],
        }
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = baseline if args.mode == "before" else evidence / "after.json"
    if output.exists():
        output = evidence / ("after-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    fd = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2, default=json_default)
        handle.write("\n")
    print(json.dumps({"evidence_file": str(output), **snapshot}, ensure_ascii=False, indent=2))
    if args.mode == "after" and not all(
        snapshot["comparison"][key] for key in (
            "business_records_unchanged", "entry_timing_counts_unchanged",
            "runtime_env_unchanged", "test_login_setting_unchanged", "correction_rows_unchanged",
            "protected_tables_unchanged", "account_dataset_counts_unchanged", "audit_retention_only",
        )
    ):
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Database exception strings can contain usernames/hosts. Do not print them.
        print(json.dumps({"error_type": type(exc).__name__, "message": "Verification failed; no database writes were performed. Check configuration, baseline and permissions."}), file=sys.stderr)
        raise SystemExit(1)
