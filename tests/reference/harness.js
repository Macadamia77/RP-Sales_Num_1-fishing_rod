// 원본 collector.js · naver.js 를 node 에서 가짜 fetch 로 돌려 결과를 JSON으로 출력한다 (파이썬 이식본 대조용)
// 사용: node harness.js <입력.json>   입력 = {routes, defaults, rows, geo, verify, q114, gu, dong}
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const calls = [];

function normKey(method, url, body) {
  if (method === 'POST') return 'POST 114 ' + JSON.parse(body).query;
  for (const host of ['https://maps.apigw.ntruss.com', 'https://naverapihub.apigw.ntruss.com']) if (url.startsWith(host)) return url.slice(host.length);
  return url;
}
function lookup(key) {
  if (input.routes[key]) return input.routes[key];
  for (const [prefix, body] of input.defaults) if (key.startsWith(prefix)) return { status: 200, body: JSON.stringify(body) };
  return { status: 404, body: '' };
}
function makeContext() {
  const ctx = {
    console: { log() {}, warn() {}, error() {} },
    URLSearchParams, AbortController, clearTimeout, Promise, JSON, Math, Date, Number, String, Object, Array, Set, Error, RegExp,
    encodeURIComponent, location: { host: 'test' },
    setTimeout: (f) => setTimeout(f, 0),   // 대기 시간 없이
  };
  ctx.window = ctx;
  ctx.fetch = async (u, o = {}) => {
    const method = o.method || 'GET';
    const key = normKey(method, String(u), o.body);
    calls.push(key);
    const r = lookup(key);
    return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => JSON.parse(r.body), text: async () => r.body };
  };
  vm.createContext(ctx);
  return ctx;
}
const wait = (pred) => new Promise((res) => { const t = setInterval(() => { if (pred()) { clearInterval(t); res(); } }, 5); });

(async () => {
  const out = {};
  // collector.js · A, B, C
  const c = makeContext();
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'collector.js'), 'utf8'), c);
  c.__setKey('KEY');
  c.__loadInput({ gu: input.gu, dong: input.dong }, input.rows);
  c.__start('A'); await wait(() => c.__RUN.A && !c.__RUN.A.running);
  c.__start('B'); await wait(() => c.__RUN.B && !c.__RUN.B.running);
  c.__loadQueue114({ gu: input.gu, dong: input.dong }, input.q114);
  c.__start('C'); await wait(() => c.__RUN.C && !c.__RUN.C.running);
  out.A = JSON.parse(JSON.stringify(c.__ST.A));
  out.B = JSON.parse(JSON.stringify(c.__ST.B));
  out.C = JSON.parse(JSON.stringify(c.__ST.C));
  // naver.js · 지오코딩, 지역 검색 (탭이 달랐으므로 새 환경)
  const n = makeContext();
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'naver.js'), 'utf8'), n);
  n.__setNaverKey('ID', 'SECRET');
  n.__loadGeoQueue({ gu: input.gu, dong: input.dong }, input.geo);
  n.__nstart('G'); await wait(() => n.__NRUN.G && !n.__NRUN.G.running);
  n.__loadVerifyQueue({ gu: input.gu, dong: input.dong }, input.verify);
  n.__nstart('V'); await wait(() => n.__NRUN.V && !n.__NRUN.V.running);
  out.NG = JSON.parse(JSON.stringify(n.__NG));
  out.NV = JSON.parse(JSON.stringify(n.__NV));
  out.calls = calls;
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
