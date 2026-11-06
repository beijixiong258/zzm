import { createServer } from 'node:http';
import { mkdir, readFile, writeFile, rename, readdir, rm } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const validId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,150}$/.test(value);
const validRevision = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const collectionName = corpus => `${corpus.id}_${corpus.revision}`;
const fail = (status, message) => { throw Object.assign(new Error(message), { status }); };

export function validateCorpus(id, value) {
  if (!value || typeof value !== 'object' || !validId(id) || value.id !== id || !validRevision(value.revision) || !Array.isArray(value.parts)
      || value.parts.length > 3000 || typeof value.title !== 'string' || value.title.length > 1000) fail(400, 'Invalid corpus');
  const ids = new Set();
  for (const part of value.parts) {
    if (!validId(part.id) || ids.has(part.id) || typeof part.text !== 'string' || part.text.length > 12000
        || !Number.isInteger(part.page) || part.page < 0 || part.page > 10000) fail(400, 'Invalid part');
    ids.add(part.id);
  }
  return value;
}

/** 每个业务内容指纹使用独立集合；即使上游版本没有元数据过滤，也不会扩大读取范围。 */
export async function createService(root, store) {
  root = path.resolve(root);
  const manifests = path.join(root, 'manifests');
  await mkdir(manifests, { recursive: true });
  await mkdir(path.join(root, 'documents'), { recursive: true });
  const entries = new Map();
  for (const file of await readdir(manifests)) {
    if (!file.endsWith('.json')) continue;
    const entry = JSON.parse(await readFile(path.join(manifests, file), 'utf8'));
    validateCorpus(entry.id, entry);
    entries.set(entry.id, entry);
  }
  let active = false;
  let stopped = false;
  let searchCount = 0;
  let sequence = 0;
  const persist = async entry => {
    const target = path.join(manifests, `${entry.id}.json`);
    const temporary = `${target}.${process.pid}.${sequence++}.tmp`;
    await writeFile(temporary, JSON.stringify(entry));
    await rename(temporary, target);
  };
  const manifestView = () => [...entries.values()].map(e => ({ id: e.id, revision: e.revision,
    indexedRevision: e.indexedRevision ?? '', status: e.deleted ? 'deleted' : e.indexedRevision === e.revision ? 'ready' : 'pending' }));

  async function work() {
    if (active || stopped || searchCount > 0) return;
    const entry = [...entries.values()].find(e => (e.deleted || e.indexedRevision !== e.revision) && (e.retryAt ?? 0) < Date.now());
    if (!entry) return;
    active = true;
    try {
      const name = collectionName(entry);
      const existing = await store.listCollections();
      if (!entry.deleted) {
        const directory = path.join(root, 'documents', name);
        await mkdir(directory, { recursive: true });
        // 一个文件对应一个可定位的教学片段，不将整份教材作为单个检索结果。
        for (const part of entry.parts) await writeFile(path.join(directory, `${part.id}.md`), part.text);
        await store.addCollection(name, { path: directory, pattern: '*.md' });
        await store.update({ collections: [name] });
        await store.embed({ collection: name, maxDocsPerBatch: 16, maxBatchBytes: 16 * 1024 * 1024 });
      }
      // 正文更新和删除串行执行，检索在写索引期间直接降级，不与 SQLite 写入竞争。
      for (const collection of existing) {
        if (collection.name.startsWith(`${entry.id}_`) && validRevision(collection.name.substring(entry.id.length + 1)) && (entry.deleted || collection.name !== name)) {
          await store.removeCollection(collection.name);
          await rm(path.join(root, 'documents', collection.name), { recursive: true, force: true });
        }
      }
      if (entries.get(entry.id) !== entry) return;
      if (entry.deleted) {
        await rm(path.join(manifests, `${entry.id}.json`), { force: true });
        entries.delete(entry.id);
      } else {
        entry.indexedRevision = entry.revision; entry.retryAt = 0; await persist(entry);
      }
    } catch (error) {
      entry.retryAt = Date.now() + 30000;
      console.error('索引同步失败，稍后重试：', entry.id, error.name);
    } finally { active = false; }
  }
  const timer = setInterval(() => void work(), 1000);
  timer.unref();

  return {
    manifestView,
    work,
    async put(id, value) {
      validateCorpus(id, value);
      const old = entries.get(id);
      if (old && old.revision === value.revision && !old.deleted) return;
      const entry = { ...value, indexedRevision: '', retryAt: 0 };
      await persist(entry); entries.set(id, entry);
    },
    async remove(id) {
      if (!validId(id)) fail(400, 'Invalid identifier');
      const old = entries.get(id);
      if (!old) return;
      const entry = { ...old, deleted: true, retryAt: 0 };
      await persist(entry); entries.set(id, entry);
    },
    async search(value) {
      if (!Array.isArray(value.scopes) || value.scopes.length > 300 || typeof value.query !== 'string'
          || value.query.length > 4000) fail(400, 'Invalid search');
      if (value.scopes.length === 0 || !value.query.trim()) return { hits: [], available: true };
      if (active || searchCount >= 2) fail(503, 'Index is busy');
      const allowed = new Map();
      for (const scope of value.scopes) {
        if (!validId(scope.id) || !validRevision(scope.revision)) fail(400, 'Invalid scope');
        const entry = entries.get(scope.id);
        if (entry && !entry.deleted && entry.revision === scope.revision && entry.indexedRevision === scope.revision)
          allowed.set(collectionName(entry), entry);
      }
      if (allowed.size === 0) return { hits: [], available: false };
      searchCount++;
      try {
        // 显式提供两类查询，避免普通学生提问额外运行查询扩展模型。
        const results = await store.search({ queries: [{ type: 'lex', query: value.query }, { type: 'vec', query: value.query }],
          collections: [...allowed.keys()], limit: Math.min(12, Math.max(1, Number(value.limit) || 6)),
          rerank: value.rerank === true, candidateLimit: 12 });
        const hits = [];
        for (const result of results) {
          const match = /^qmd:\/\/([^/]+)\/([^/]+)\.md$/.exec(result.file);
          const entry = match && allowed.get(match[1]);
          if (!entry || entries.get(entry.id) !== entry) continue;
          const part = entry.parts.find(p => p.id === match[2]);
          if (!part) continue;
          hits.push({ corpusId: entry.id, revision: entry.revision, partId: part.id, page: part.page,
            snippet: part.text.slice(0, 350), score: result.score });
        }
        return { hits, available: true };
      } finally { searchCount--; }
    },
    async close() { stopped = true; clearInterval(timer); while (active || searchCount) await new Promise(r => setTimeout(r, 20)); await store.close(); },
  };
}

export function handler(service) {
  return async (request, response) => {
    try {
      const url = new URL(request.url, 'http://localhost');
      let body = {};
      if (['POST', 'PUT'].includes(request.method)) {
        const chunks = []; let bytes = 0;
        for await (const chunk of request) { bytes += chunk.length; if (bytes > 12 * 1024 * 1024) fail(413, 'Request too large'); chunks.push(chunk); }
        try { body = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { fail(400, 'Invalid JSON'); }
      }
      let result;
      if (request.method === 'GET' && url.pathname === '/corpora') result = { corpora: service.manifestView() };
      else if (request.method === 'POST' && url.pathname === '/search') result = await service.search(body);
      else if (/^\/corpora\/[A-Za-z0-9_-]+$/.test(url.pathname)) {
        const id = url.pathname.substring('/corpora/'.length);
        if (request.method === 'PUT') await service.put(id, body);
        else if (request.method === 'DELETE') await service.remove(id);
        else fail(405, 'Method not allowed');
        result = { accepted: true };
      } else fail(404, 'Not found');
      response.writeHead(200, { 'Content-Type': 'application/json' }); response.end(JSON.stringify(result));
    } catch (error) {
      response.writeHead(error.status || 503, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ error: error.status ? error.message : 'Retrieval unavailable' }));
    }
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const { createStore } = await import('@tobilu/qmd');
  const root = process.env.QMD_DATA || '/data';
  await mkdir(root, { recursive: true });
  const store = await createStore({ dbPath: path.join(root, 'index.sqlite') });
  const service = await createService(root, store);
  const server = createServer(handler(service));
  server.requestTimeout = 20000;
  server.listen(8181, '0.0.0.0');
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => void service.close().then(() => process.exit(0))));
}
