// Chạy Cube trên máy dev: đọc .env ở thư mục gốc, model từ semantic/cube/model, cấu hình từ cube.js.
const path = require("path");
const fs = require("fs");

const root = path.resolve(__dirname, "..");
const envFile = path.join(root, ".env");
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2];
  }
}
process.env.CUBEJS_API_SECRET = process.env.CUBEJS_API_SECRET || process.env.CUBE_API_SECRET;
process.env.CUBEJS_DB_TYPE = process.env.CUBEJS_DB_TYPE || "duckdb";
const duck = process.env.DUCKDB_PATH || path.join(root, ".local", "dx.duckdb");
process.env.CUBEJS_DB_DUCKDB_DATABASE_PATH = path.resolve(root, duck);
process.env.CUBEJS_SCHEMA_PATH = path.relative(__dirname, path.join(root, "semantic", "cube", "model"));
process.env.CUBEJS_DEV_MODE = process.env.CUBEJS_DEV_MODE || "true";
process.env.CUBEJS_SCHEDULED_REFRESH_DEFAULT = "false";
process.env.DX_API_INTERNAL_URL = process.env.DX_API_INTERNAL_URL || process.env.API_INTERNAL_URL || "http://localhost:8000";
process.env.PORT = process.env.CUBE_PORT || "4000";
if (process.platform === "win32" && process.env.CUBE_DISABLE_PREAGGS === undefined) {
  process.env.CUBE_DISABLE_PREAGGS = "1";
}
// Cube Store dev: thư mục dữ liệu dạng đường dẫn có dấu "/" (tránh lỗi ghép đường dẫn trên Windows).
const storeDir = path.join(root, ".local", "cubestore").replace(/\\/g, "/");
process.env.CUBESTORE_DATA_DIR = process.env.CUBESTORE_DATA_DIR || `${storeDir}/data`;
process.env.CUBESTORE_REMOTE_DIR = process.env.CUBESTORE_REMOTE_DIR || `${storeDir}/remote`;

const CubejsServer = require("@cubejs-backend/server");
const options = require("./cube.js");
const server = new CubejsServer(options);
server.listen().then(({ port }) => console.log(`Cube đang chạy ở http://localhost:${port}`));
