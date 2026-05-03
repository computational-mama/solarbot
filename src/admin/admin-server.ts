import http from "http";
import fs from "fs";
import path from "path";
import { execFile } from "child_process";
import { knowledgeDir } from "../utils/dir";

const ENV_PATH = path.resolve(__dirname, "../..", ".env");
const WEB_PATH = path.resolve(__dirname, "../..", "web", "admin", "index.html");
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || "";

function authed(req: http.IncomingMessage): boolean {
  if (!ADMIN_TOKEN) return true;
  const auth = req.headers["authorization"] || "";
  return auth === `Bearer ${ADMIN_TOKEN}`;
}

function json(res: http.ServerResponse, status: number, body: object) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function readEnv(): Record<string, string> {
  if (!fs.existsSync(ENV_PATH)) return {};
  const lines = fs.readFileSync(ENV_PATH, "utf8").split("\n");
  const out: Record<string, string> = {};
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    out[trimmed.slice(0, eq)] = trimmed.slice(eq + 1);
  }
  return out;
}

function writeEnv(vars: Record<string, string>) {
  const content = Object.entries(vars)
    .map(([k, v]) => `${k}=${v}`)
    .join("\n") + "\n";
  fs.writeFileSync(ENV_PATH, content, "utf8");
}

function parseMultipart(
  req: http.IncomingMessage,
  callback: (err: Error | null, filename?: string, data?: Buffer) => void
) {
  const contentType = req.headers["content-type"] || "";
  const boundaryMatch = contentType.match(/boundary=(.+)/);
  if (!boundaryMatch) return callback(new Error("No boundary"));
  const boundary = Buffer.from("--" + boundaryMatch[1]);

  const chunks: Buffer[] = [];
  req.on("data", (chunk) => chunks.push(chunk));
  req.on("end", () => {
    const body = Buffer.concat(chunks);
    const parts = splitBuffer(body, boundary);
    for (const part of parts) {
      const headerEnd = indexOfSequence(part, Buffer.from("\r\n\r\n"));
      if (headerEnd === -1) continue;
      const headers = part.slice(0, headerEnd).toString();
      const nameMatch = headers.match(/name="([^"]+)"/);
      const fileMatch = headers.match(/filename="([^"]+)"/);
      if (nameMatch?.[1] === "file" && fileMatch?.[1]) {
        const data = part.slice(headerEnd + 4, part.length - 2);
        callback(null, fileMatch[1], data);
        return;
      }
    }
    callback(new Error("No file found"));
  });
  req.on("error", callback);
}

function splitBuffer(buf: Buffer, delimiter: Buffer): Buffer[] {
  const parts: Buffer[] = [];
  let start = 0;
  let pos = 0;
  while ((pos = indexOfSequence(buf, delimiter, start)) !== -1) {
    parts.push(buf.slice(start, pos));
    start = pos + delimiter.length;
  }
  parts.push(buf.slice(start));
  return parts;
}

function indexOfSequence(buf: Buffer, seq: Buffer, offset = 0): number {
  outer: for (let i = offset; i <= buf.length - seq.length; i++) {
    for (let j = 0; j < seq.length; j++) {
      if (buf[i + j] !== seq[j]) continue outer;
    }
    return i;
  }
  return -1;
}

export function startAdminServer(port: number) {
  const server = http.createServer((req, res) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type");
    if (req.method === "OPTIONS") { res.writeHead(204); res.end(); return; }

    const url = new URL(req.url || "/", `http://localhost:${port}`);

    // Serve UI
    if (url.pathname === "/" && req.method === "GET") {
      res.writeHead(200, { "Content-Type": "text/html" });
      fs.createReadStream(WEB_PATH).pipe(res);
      return;
    }

    if (!authed(req)) return json(res, 401, { error: "Unauthorized" });

    // GET /env — read .env
    if (url.pathname === "/env" && req.method === "GET") {
      return json(res, 200, readEnv());
    }

    // POST /env — save .env
    if (url.pathname === "/env" && req.method === "POST") {
      const chunks: Buffer[] = [];
      req.on("data", (c) => chunks.push(c));
      req.on("end", () => {
        try {
          const vars = JSON.parse(Buffer.concat(chunks).toString());
          writeEnv(vars);
          json(res, 200, { ok: true });
        } catch { json(res, 400, { error: "Invalid JSON" }); }
      });
      return;
    }

    // GET /knowledge — list files
    if (url.pathname === "/knowledge" && req.method === "GET") {
      const files = fs.existsSync(knowledgeDir)
        ? fs.readdirSync(knowledgeDir).filter((f) => !f.startsWith("."))
        : [];
      return json(res, 200, { files });
    }

    // POST /knowledge/upload — upload a file
    if (url.pathname === "/knowledge/upload" && req.method === "POST") {
      parseMultipart(req, (err, filename, data) => {
        if (err || !filename || !data) return json(res, 400, { error: "Upload failed" });
        const safe = path.basename(filename);
        fs.writeFileSync(path.join(knowledgeDir, safe), data);
        json(res, 200, { ok: true, file: safe });
      });
      return;
    }

    // DELETE /knowledge/:file — remove a file
    if (url.pathname.startsWith("/knowledge/") && req.method === "DELETE") {
      const file = path.basename(url.pathname.replace("/knowledge/", ""));
      const target = path.join(knowledgeDir, file);
      if (fs.existsSync(target)) fs.unlinkSync(target);
      return json(res, 200, { ok: true });
    }

    // POST /reindex — run the index script
    if (url.pathname === "/reindex" && req.method === "POST") {
      const root = path.resolve(__dirname, "../..");
      res.writeHead(200, { "Content-Type": "text/plain" });
      const child = execFile("yarn", ["index"], { cwd: root });
      child.stdout?.pipe(res);
      child.stderr?.pipe(res);
      child.on("close", (code) => res.end(`\nExited with code ${code}`));
      return;
    }

    json(res, 404, { error: "Not found" });
  });

  server.listen(port, "0.0.0.0", () => {
    console.log(`[Admin] UI running at http://0.0.0.0:${port}`);
  });
}
