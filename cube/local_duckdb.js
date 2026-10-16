// Driver DuckDB cho môi trường local (spec 00 §4): không giữ file DuckDB mở giữa các truy vấn.
//
// DuckDB chỉ cho một tiến trình ghi, và không cho ghi khi tiến trình khác đang mở file (kể cả chỉ đọc). Driver gốc của
// Cube giữ file mở suốt, nên dbt (tiến trình ghi) không chạy được khi Cube đang chạy. Driver này mở cơ sở dữ liệu trong
// bộ nhớ, ATTACH file ở chế độ READ_ONLY cho từng truy vấn rồi DETACH ngay. Truy vấn được xếp hàng tuần tự.
// Ở dev và prod kho là BigQuery nên không dùng driver này.

const { Readable } = require("stream");
const { DuckDBDriver } = require("@cubejs-backend/duckdb-driver");

class LocalDuckDBDriver extends DuckDBDriver {
  constructor(config = {}) {
    const filePath = config.databasePath || process.env.CUBEJS_DB_DUCKDB_DATABASE_PATH;
    super({ ...config, databasePath: ":memory:" });
    this.filePath = filePath;
    this.queue = Promise.resolve();
  }

  readOnly() {
    return true;
  }

  async withAttached(fn) {
    const run = async () => {
      const { defaultConnection } = await this.getInitiatedState();
      const path = this.filePath.replace(/\\/g, "/").replace(/'/g, "''");
      let lastErr;
      for (let i = 0; i < 20; i += 1) {
        try {
          await defaultConnection.run(`ATTACH '${path}' AS dx (READ_ONLY)`);
          lastErr = null;
          break;
        } catch (e) {
          lastErr = e; // dbt đang ghi: chờ rồi thử lại
          await new Promise((r) => setTimeout(r, 500));
        }
      }
      if (lastErr) throw lastErr;
      try {
        // Cube so cột DATE với timestamptz: phiên phải ở UTC, nếu không khoảng ngày bị lệch theo múi giờ của máy.
        await defaultConnection.run("SET TimeZone = 'UTC'");
        await defaultConnection.run("USE dx");
        return await fn();
      } finally {
        try {
          await defaultConnection.run("USE memory");
          await defaultConnection.run("DETACH dx");
        } catch (e) {
          // bỏ qua: lần sau ATTACH lại
        }
      }
    };
    const p = this.queue.then(run, run);
    this.queue = p.catch(() => undefined);
    return p;
  }

  async query(query, values = [], options) {
    return this.withAttached(() => super.query(query, values, options));
  }

  async stream(query, values) {
    const rows = await this.query(query, values);
    return { rowStream: Readable.from(rows), release: async () => undefined };
  }
}

module.exports = { LocalDuckDBDriver };
