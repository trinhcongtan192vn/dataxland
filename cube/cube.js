// Cấu hình runtime của Cube (spec 03 §10.1). Một deployment cho mọi khách, tách khách qua securityContext.
// Model sinh ra ở semantic/cube/model (không sửa tay).

const jwt = require("jsonwebtoken");
// Lỗi kiểu này được gateway trả đúng mã 403; lỗi thường thành 500.
const { CubejsHandlerError } = require("@cubejs-backend/api-gateway/dist/src/cubejs-handler-error");

const TENANT_RE = /^[a-z][a-z0-9_]{2,30}$/;

// dataset_prefix phải khớp đúng khách: `t_<tenant_id>` hoặc lượt kiểm tra sức khỏe `hc_<check_id>`.
function prefixMatches(tenantId, prefix) {
  if (tenantId.startsWith("hc_")) return prefix === tenantId;
  return prefix === `t_${tenantId}`;
}

function assertContext(ctx) {
  if (!ctx || !ctx.tenant_id || !ctx.dataset_prefix) {
    throw new CubejsHandlerError(403, "Forbidden", "securityContext thiếu tenant_id hoặc dataset_prefix");
  }
  if (!TENANT_RE.test(ctx.tenant_id) || !prefixMatches(ctx.tenant_id, ctx.dataset_prefix)) {
    throw new CubejsHandlerError(403, "Forbidden", "tenant_id hoặc dataset_prefix không hợp lệ");
  }
}

module.exports = {
  // Xác minh JWT HS256 do services/api ký bằng CUBE_API_SECRET.
  checkAuth: (req, auth) => {
    if (!auth) throw new CubejsHandlerError(403, "Forbidden", "Thiếu token");
    const token = auth.startsWith("Bearer ") ? auth.slice(7) : auth;
    let decoded;
    try {
      decoded = jwt.verify(token, process.env.CUBEJS_API_SECRET, { algorithms: ["HS256"] });
    } catch (e) {
      throw new CubejsHandlerError(403, "Forbidden", "Token không hợp lệ", e);
    }
    assertContext(decoded);
    req.securityContext = { tenant_id: decoded.tenant_id, dataset_prefix: decoded.dataset_prefix };
  },

  // SQL API (Metabase nội bộ, chỉ đọc) dùng tài khoản riêng và phải chọn khách qua tham số kết nối.
  checkSqlAuth: async (req, user) => {
    if (user !== process.env.CUBEJS_SQL_USER) throw new Error("Sai tài khoản SQL API");
    return { password: process.env.CUBEJS_SQL_PASSWORD, securityContext: {} };
  },

  contextToAppId: ({ securityContext }) => `CUBE_APP_${(securityContext || {}).tenant_id || "none"}`,
  contextToOrchestratorId: ({ securityContext }) => `CUBE_ORCH_${(securityContext || {}).tenant_id || "none"}`,

  // Từ chối mọi truy vấn khi securityContext.tenant_id trống (FR-MET-05).
  queryRewrite: (query, { securityContext }) => {
    assertContext(securityContext);
    return query;
  },

  // Làm mới theo lịch: danh sách khách active từ services/api (pre-aggregation cũng được làm mới khi transform.finished).
  scheduledRefreshContexts: async () => {
    const base = process.env.DX_API_INTERNAL_URL || "http://api:8000";
    try {
      const res = await fetch(`${base}/v1/internal/tenants?status=active`, {
        headers: { Authorization: `Bearer ${process.env.INTERNAL_API_TOKEN}`, "X-Service": "cube" },
      });
      if (!res.ok) return [];
      const tenants = await res.json();
      return tenants.map((t) => ({ securityContext: { tenant_id: t.tenant_id, dataset_prefix: t.dataset_prefix } }));
    } catch (e) {
      return [];
    }
  },

  // local: DuckDB (file DUCKDB_PATH, chỉ đọc). dev/prod: BigQuery với tài khoản dx-cube chỉ đọc *_marts.
  driverFactory: ({ dataSource }) => {
    if ((process.env.CUBEJS_DB_TYPE || "duckdb") === "duckdb") {
      const { LocalDuckDBDriver } = require("./local_duckdb");
      return new LocalDuckDBDriver({ databasePath: process.env.CUBEJS_DB_DUCKDB_DATABASE_PATH });
    }
    return { type: "bigquery" };
  },

  // Cube Store bản Windows lỗi đường dẫn file; khi chạy native trên Windows (CUBE_DISABLE_PREAGGS=1) nạp model nhưng
  // bỏ pre-aggregation, truy vấn đi thẳng vào DuckDB. Docker, dev, prod không đặt biến này.
  repositoryFactory: () => {
    const { FileRepository } = require("@cubejs-backend/server-core");
    const repo = new FileRepository(process.env.CUBEJS_SCHEMA_PATH || "model");
    if (process.env.CUBE_DISABLE_PREAGGS !== "1") return repo;
    return {
      localPath: () => repo.localPath(),
      dataSchemaFiles: async () =>
        (await repo.dataSchemaFiles()).map((f) => ({
          ...f,
          content: f.content.replace(/\n {2}pre_aggregations:\n(?: {2}- .*\n| {4}.*\n)*/g, "\n  pre_aggregations: []\n"),
        })),
    };
  },

  telemetry: false,
};

