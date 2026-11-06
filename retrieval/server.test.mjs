import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createService, validateCorpus } from './server.mjs';

const revision = 'a'.repeat(64);
const changed = 'b'.repeat(64);
const corpus = (id = 'm-one', version = revision) => ({ id, revision: version, title: '材料', parts: [{ id: 's0', text: 'A complete source paragraph. 中文材料。', page: 1 }] });
async function fixture(t) {
  const root = await mkdtemp(path.join(process.env.TEST_ROOT || os.tmpdir(), 'qmd-contract-'));
  const collections = new Map();
  const calls = [];
  const store = {
    async listCollections() { return [...collections.keys()].map(name => ({ name })); },
    async addCollection(name) { collections.set(name, true); },
    async removeCollection(name) { collections.delete(name); },
    async update() {}, async embed() {}, async close() {},
    async search(options) { calls.push(options); return options.collections.map(name => ({ file: `qmd://${name}/s0.md`, body: 'WHOLE BODY MUST NOT ESCAPE', score: 0.8 })); },
  };
  const service = await createService(root, store);
  t.after(() => service.close());
  return { service, calls, root, store };
}

test('空权限范围不会调用 QMD', async t => {
  const { service, calls } = await fixture(t);
  assert.deepEqual(await service.search({ scopes: [], query: 'anything' }), { hits: [], available: true });
  assert.equal(calls.length, 0);
});
test('只将当前授权集合交给检索，不返回原始正文', async t => {
  const { service, calls } = await fixture(t);
  await service.put('m-one', corpus()); await service.work();
  await service.put('m-other-student', corpus('m-other-student')); await service.work();
  const result = await service.search({ scopes: [{ id: 'm-one', revision }], query: '中文', limit: 3 });
  assert.deepEqual(calls[0].collections, [`m-one_${revision}`]);
  assert.deepEqual(calls[0].queries.map(q => q.type), ['lex', 'vec']);
  assert.equal(result.hits.length, 1); assert.equal(result.hits[0].corpusId, 'm-one');
  assert.ok(!JSON.stringify(result).includes('WHOLE BODY'));
});
test('更新立即使旧指纹失效，索引完成后新指纹可用', async t => {
  const { service } = await fixture(t);
  await service.put('m-one', corpus()); await service.work();
  await service.put('m-one', corpus('m-one', changed));
  assert.equal((await service.search({ scopes: [{ id: 'm-one', revision }], query: 'source' })).hits.length, 0);
  await service.work();
  assert.equal((await service.search({ scopes: [{ id: 'm-one', revision: changed }], query: 'source' })).hits.length, 1);
});
test('删除标记立即撤销读取，重启后仍能继续清理', async t => {
  const { service, root, store } = await fixture(t);
  await service.put('m-one', corpus()); await service.work(); await service.remove('m-one');
  assert.equal((await service.search({ scopes: [{ id: 'm-one', revision }], query: 'source' })).hits.length, 0);
  const recovered = await createService(root, store); t.after(() => recovered.close()); await recovered.work();
  assert.deepEqual(recovered.manifestView(), []);
});
test('上游返回越界结果也会被封装层丢弃', async t => {
  const { service, store } = await fixture(t);
  await service.put('m-one', corpus()); await service.work();
  store.search = async () => [{ file: `qmd://m-other_${revision}/s0.md`, score: 1 }];
  assert.deepEqual((await service.search({ scopes: [{ id: 'm-one', revision }], query: 'source' })).hits, []);
});
test('不能通过业务标识或片段标识访问任意路径', () => {
  assert.throws(() => validateCorpus('../escape', corpus('../escape')));
  const value = corpus(); value.parts[0].id = '../../secret'; assert.throws(() => validateCorpus('m-one', value));
});
