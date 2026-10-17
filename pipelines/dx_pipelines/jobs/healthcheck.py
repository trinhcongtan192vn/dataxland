"""Job `healthcheck` và dọn dữ liệu hết hạn (FR-HC-02, FR-HC-04, spec 07 §5, §7).

Lượt kiểm tra là một "khách tạm" `hc_<check_id>`: cùng dbt, cùng Cube, cùng bộ máy chỉ số gói Seller.
"""

import shutil
from pathlib import Path
from typing import Any

import dagster as dg

from dx_common.config import get_settings
from dx_common.logging import get_logger
from dx_common.tenants.naming import datasets
from dx_common.timeutil import today_vn
from dx_pipelines.api_client import ApiClient
from dx_pipelines.cube import CubeAdmin
from dx_pipelines.dbt import DbtProject, repo_root
from dx_pipelines.overrides import COLUMNS as OVERRIDE_COLUMNS
from dx_pipelines.overrides import ensure_identity_map
from dx_pipelines.warehouse import get_warehouse

log = get_logger(__name__)
RETENTION_DAYS = 15  # lưới an toàn của dataset và bucket (spec 07 §3, §5)


class HealthCheckConfig(dg.Config):
    check_id: str


def run_healthcheck(
    check_id: str, api: ApiClient | None = None, dbt: Any = None, cube: Any = None, warehouse: Any = None
) -> dict[str, Any]:
    from connectors.files.source import load_files

    api = api or ApiClient()
    tid = f"hc_{check_id}"
    wh = warehouse or get_warehouse(tid, job="healthcheck")
    info = api.post(f"/v1/internal/health-checks/{check_id}/start")
    expires = info.get("expires_at", "")[:10]
    for ds in datasets(tid):
        wh.ensure_dataset(ds, {"dx_kind": "healthcheck", "expires": expires.replace("-", "")}, RETENTION_DAYS)
    # Bảng ghi đè trạng thái và identity_map luôn có (có thể trống) để staging và core nối được.
    wh.write_rows(f"{tid}_raw", "dx__status_map_override", OVERRIDE_COLUMNS, [])
    ensure_identity_map(tid, wh, f"{tid}_core")
    loaded = load_files(check_id, info["files"], info["salt"], wh, f"{tid}_raw")
    api.post(f"/v1/internal/health-checks/{check_id}/files", {"files": loaded["files"]})
    sources = loaded["sources"]
    if not sources:
        api.post(f"/v1/internal/health-checks/{check_id}/fail", {"reason": "no_valid_files"})
        return {"status": "failed", "reason": "no_valid_files"}
    vars_ = {
        "tenant_id": tid,
        "pack": "seller",
        "sources": sources,
        "cost_allocation": "by_revenue",
        "freshness_hours": 24 * 365,
        "reconcile_tolerance_pct": {"default": 100.0},
        "provisional_window_days": {"default": 14},
        "dataset_prefix": tid,
        "today": today_vn().isoformat(),
        "healthcheck": True,
    }
    dbt = dbt or DbtProject()
    target = repo_root() / "transform" / "target" / "runs" / tid
    env = {"DX_PII_SALT": info["salt"], "DX_TENANT_ID": tid}
    build = dbt.build(vars_, target, env, exclude=["tag:freshness", "tag:reconcile", "resource_type:unit_test"])
    if build.runtime_error:
        api.post(f"/v1/internal/health-checks/{check_id}/fail", {"reason": "dbt_error"})
        return {"status": "failed", "reason": "dbt_error", "log": build.stdout_tail[-1500:]}
    # Lỗi ánh xạ không chặn mà được liệt kê cho data lead (spec 07 §5 bước 3).
    mapping_issues = [
        r["unique_id"]
        for r in build.run_results.get("results", [])
        if r.get("unique_id", "").startswith("test.") and r.get("status") in ("fail", "error")
    ]
    swap = dbt.run_operation("dx_swap_marts", {}, vars_, target, env)
    if not swap.ok:
        api.post(f"/v1/internal/health-checks/{check_id}/fail", {"reason": "swap_failed"})
        return {"status": "failed", "reason": "swap_failed"}
    try:
        (cube or CubeAdmin()).refresh(tid, tid)
    except Exception as exc:  # Cube không có pre-aggregation vẫn truy vấn được
        log.warning("refresh Cube cho %s lỗi: %s", tid, type(exc).__name__)
    res = api.post(
        f"/v1/internal/health-checks/{check_id}/build",
        {"mapping_issues": mapping_issues[:50], "file_ranges": loaded["ranges"]},
    )
    return {"status": "ready_for_review", **res}


@dg.op
def healthcheck_op(context: dg.OpExecutionContext, config: HealthCheckConfig) -> dict[str, Any]:
    res = run_healthcheck(config.check_id)
    context.log.info(str({k: v for k, v in res.items() if k != "log"}))
    if res.get("status") == "failed":
        raise dg.Failure(description=f"Kiểm tra sức khỏe {config.check_id} lỗi: {res.get('reason')}")
    return res


@dg.job(description="Nạp file kiểm tra sức khỏe → dbt → Cube → dựng kết quả (spec 07 §5)")
def healthcheck() -> None:
    healthcheck_op()


def delete_files(check_id: str) -> int:
    base = get_settings().hc_bucket.rstrip("/")
    if base.startswith("gs://"):  # pragma: no cover - cần GCS
        from google.cloud import storage

        bucket_name, _, prefix = base[5:].partition("/")
        b = storage.Client().bucket(bucket_name)
        blobs = list(b.list_blobs(prefix="/".join(x for x in (prefix, check_id) if x) + "/"))
        for blob in blobs:
            blob.delete()
        return len(blobs)
    d = Path(base) / check_id
    n = len(list(d.glob("*"))) if d.exists() else 0
    shutil.rmtree(d, ignore_errors=True)
    return n


def cleanup_expired(api: ApiClient | None = None, warehouse_for: Any = None) -> dict[str, Any]:
    """FR-HC-04: lượt quá hạn và chưa chuyển đổi bị xóa dataset, file, cache; lỗi một lượt không dừng lượt khác."""
    api = api or ApiClient()
    expired = api.post("/v1/internal/health-checks/expired").get("items", [])
    done, failed = [], []
    for item in expired:
        cid = item["check_id"]
        try:
            wh = (warehouse_for or (lambda t: get_warehouse(t, job="healthcheck")))(f"hc_{cid}")
            tables = sum(wh.drop_dataset(ds) for ds in datasets(f"hc_{cid}"))
            files = delete_files(cid)
            api.post(f"/v1/internal/health-checks/{cid}/expired", {"tables": tables, "files": files})
            log.info("đã xóa kiểm tra sức khỏe", extra={"dx": {"check_id": cid, "tables": tables, "files": files}})
            done.append(cid)
        except Exception as exc:
            log.warning("xóa %s lỗi: %s", cid, type(exc).__name__)
            failed.append(cid)
    if failed:
        api.publish("healthcheck.failed", None, {"check_id": failed[0]}, "s5-healthcheck")
    return {"deleted": done, "failed": failed}


class ConvertConfig(dg.Config):
    check_id: str
    tenant_id: str


def copy_to_tenant(
    check_id: str, tenant_id: str, api: ApiClient | None = None, warehouse: Any = None
) -> dict[str, Any]:
    """Spec 07 §8 bước 2: sau khi khách mới đã bootstrap và người gửi đã đồng ý chuyển, sao chép bảng raw
    `*_file__*` sang `t_<tenant_id>_raw` để có thêm lịch sử, rồi xóa dữ liệu tạm như mục 7."""
    api = api or ApiClient()
    info = api.post(f"/v1/internal/health-checks/{check_id}/convert-info")
    if not info.get("copy_raw_allowed"):
        return {"status": "skipped", "reason": "no_consent"}
    if info.get("tenant_id") != tenant_id:
        return {"status": "skipped", "reason": "tenant_mismatch"}
    src_wh = warehouse or get_warehouse(f"hc_{check_id}", job="healthcheck")
    dst = f"t_{tenant_id}_raw"
    tables = [t for t in src_wh.list_tables(f"hc_{check_id}_raw") if "_file__" in t]
    for t in tables:
        src_wh.copy_table(f"hc_{check_id}_raw.{t}", f"{dst}.{t}")
    dropped = sum(src_wh.drop_dataset(ds) for ds in datasets(f"hc_{check_id}"))
    files = delete_files(check_id)
    api.post(f"/v1/internal/health-checks/{check_id}/purged", {"tables": dropped, "files": files, "copied": tables})
    return {"status": "copied", "tables": tables}


@dg.op
def healthcheck_convert_op(context: dg.OpExecutionContext, config: ConvertConfig) -> dict[str, Any]:
    res = copy_to_tenant(config.check_id, config.tenant_id)
    context.log.info(str(res))
    return res


@dg.job(description="Chuyển dữ liệu kiểm tra sức khỏe sang khách mới đã bootstrap (spec 07 §8); chạy tay")
def healthcheck_convert() -> None:
    healthcheck_convert_op()
