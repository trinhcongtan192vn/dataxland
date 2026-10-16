"""Code location Dagster của DataxLand (spec 04 §3.1)."""

from __future__ import annotations

import dagster as dg

from dx_common.logging import configure_logging
from dx_pipelines.jobs.fixed import (
    SCHEDULES,
    decision_reminders,
    events_cleanup,
    fx_daily,
    healthcheck_cleanup,
    sync_tenants,
)
from dx_pipelines.jobs.healthcheck import healthcheck
from dx_pipelines.jobs.tenant_pipeline import tenant_pipeline
from dx_pipelines.jobs.weekly_report import weekly_report
from dx_pipelines.sensors.events import events_sensor
from dx_pipelines.sensors.tenants import tenant_partitions, tenant_schedule

configure_logging()

defs = dg.Definitions(
    jobs=[
        tenant_pipeline,
        weekly_report,
        healthcheck,
        fx_daily,
        sync_tenants,
        healthcheck_cleanup,
        decision_reminders,
        events_cleanup,
    ],
    schedules=SCHEDULES,
    sensors=[tenant_partitions, tenant_schedule, events_sensor],
)
