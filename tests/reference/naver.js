// naver.js · 네이버 교차 확인 · 2026-09-28
//
// 탭이 두 개 필요함. 출처가 달라 한 탭에서 두 API를 섞어 부를 수 없음
//   지오코딩 탭 · https://maps.apigw.ntruss.com/map-geocode/v2/geocode?query=test 를 연 탭
//      주소 묶기 보강용. 원본 도로명·지번을 넣으면 네이버 기준 도로명·지번을 돌려줌
//   지역 검색 탭 · https://naverapihub.apigw.ntruss.com/search/v1/local?query=test 를 연 탭
//      이름이 확연히 다른 근접 관리사무소의 위치 교차 확인용
// 두 탭 모두 이 파일 전체를 주입한 뒤 해당 함수를 씀
// 키는 네이버 클라우드 플랫폼 콘솔의 Application 키. 지오코딩 키와 지역 검색 키가 서로 다른 Application일 수 있음
// 키는 파일이나 문서에 적지 않음
(function () {
  const W = window; const sleep = ms => new Promise(r => setTimeout(r, ms));
  W.__NK = W.__NK || {};
  W.__NG = W.__NG || {}; W.__NV = W.__NV || {};
  W.__GQ = W.__GQ || []; W.__VQ = W.__VQ || [];
  W.__NRUN = W.__NRUN || {};
  W.__setNaverKey = (id, secret) => { W.__NK = { 'X-NCP-APIGW-API-KEY-ID': id, 'X-NCP-APIGW-API-KEY': secret }; return 'ok'; };
  const dist = (x1, y1, x2, y2) => { const r = Math.PI / 180; return Math.round(Math.hypot((x2 - x1) * Math.cos(y1 * r) * 111320, (y2 - y1) * 110540)); };
  const core = s => String(s || '').replace(/<[^>]+>/g, '').replace(/\s+|관리사무소|관리실|관리단|관리소|관리센터|경비실|방제실|입주자대표회의|아파트|전기차충전소/g, '');

  async function call(path, headers) {
    for (let t = 0; t < 4; t++) {
      try { const r = await fetch(path, { headers }); if (r.ok) return await r.json(); if (r.status === 401 || r.status === 403) throw new Error('키 또는 구독 오류 ' + r.status); }
      catch (e) { if (String(e).includes('키 또는 구독')) throw e; }
      await sleep(800 * (t + 1));
    }
    throw new Error('네이버 호출 실패 ' + path.slice(0, 80));
  }

  // ---------- 지오코딩 ----------
  async function geo(addr) {
    const j = await call('/map-geocode/v2/geocode?query=' + encodeURIComponent(addr), { ...W.__NK, Accept: 'application/json' });
    const a = (j.addresses || [])[0]; if (!a) return null;
    const e = a.addressElements.find(z => z.types[0] === 'BUILDING_NAME');
    return [a.roadAddress, a.jibunAddress, e ? e.longName : '', +a.x, +a.y];
  }
  W.__loadGeoQueue = (reg, rows) => { W.__NREG = reg; const have = new Set(W.__GQ.map(x => x[0])); for (const r of rows) if (!have.has(r[0])) W.__GQ.push(r); return { chunk_check: [rows.length, rows.reduce((a, x) => a + x[0], 0)], total: W.__GQ.length }; };
  async function runGeo() {
    const st = W.__NRUN.G = { running: true, done: 0, err: 0, last: '' }; const P = '인천광역시 ' + W.__NREG.gu + ' ';
    try {
      for (const [i, road, jib] of W.__GQ) {
        if (st.stop) break; if (W.__NG[i] && !W.__NG[i].err) continue;
        try { const o = { i }; if (road) { o.r = await geo(P + road); await sleep(120); } if (jib) { o.j = await geo(P + jib); await sleep(120); } W.__NG[i] = o; st.done++; }
        catch (e) { W.__NG[i] = { i, err: String(e) }; st.err++; st.last = String(e); if (String(e).includes('키 또는 구독')) break; }
      }
    } finally { st.running = false; }
  }

  // ---------- 지역 검색 ----------
  async function local(q) {
    const j = await call('/search/v1/local?display=5&query=' + encodeURIComponent(q), W.__NK);
    return (j.items || []).map(z => ({ n: z.title.replace(/<[^>]+>/g, ''), c: z.category, road: z.roadAddress, jib: z.address, x: Number(z.mapx) / 1e7, y: Number(z.mapy) / 1e7 }));
  }
  // q = [key, 관리사무소 이름, 카카오 x, 카카오 y, 구 이름]
  async function find(q) {
    const [key, name, x, y, gu] = q; const k = core(name); let best = null; const tried = [];
    for (const s of [name, k + ' 관리사무소', '인천 ' + k + ' 관리사무소', gu + ' ' + k, k]) {
      const items = await local(s); tried.push(s + ':' + items.length); await sleep(150);
      for (const z of items) { const c = core(z.n); if (c.length >= 2 && (c.includes(k) || k.includes(c))) { const d = dist(x, y, z.x, z.y); if (!best || d < best.d) best = { ...z, d }; } }
      if (best && best.d < 500) break;
    }
    return { key, best, tried };
  }
  W.__loadVerifyQueue = (reg, rows) => { W.__NREG = reg; const have = new Set(W.__VQ.map(x => x[0])); for (const r of rows) if (!have.has(r[0])) W.__VQ.push(r); return { chunk_check: [rows.length], total: W.__VQ.length }; };
  async function runVerify() {
    const st = W.__NRUN.V = { running: true, done: 0, err: 0, last: '' };
    try { for (const q of W.__VQ) { if (st.stop) break; if (W.__NV[q[0]] && !W.__NV[q[0]].err) continue; try { W.__NV[q[0]] = await find(q); st.done++; } catch (e) { W.__NV[q[0]] = { key: q[0], err: String(e) }; st.err++; st.last = String(e); if (String(e).includes('키 또는 구독')) break; } } }
    finally { st.running = false; }
  }

  W.__nstart = which => { if (!W.__NK['X-NCP-APIGW-API-KEY-ID']) return '__setNaverKey 먼저'; if (which === 'G') { runGeo(); return '시작 G'; } if (which === 'V') { runVerify(); return '시작 V'; } return 'G 또는 V'; };
  W.__nstatus = () => ({ region: W.__NREG, G: [Object.keys(W.__NG).length, W.__GQ.length], V: [Object.keys(W.__NV).length, W.__VQ.length], run: W.__NRUN });
  W.__ndump = (which, from, count) => {
    const src = which === 'G' ? W.__NG : W.__NV; const order = which === 'G' ? W.__GQ.map(x => x[0]) : W.__VQ.map(x => x[0]);
    const rows = {}; for (const k of order.slice(from, from + count)) if (src[k]) rows[k] = src[k];
    const s = JSON.stringify({ stage: which === 'G' ? 'NG' : 'NV', region: W.__NREG, from, n: Object.keys(rows).length, rows });
    return s + '\n' + '~'.repeat(Math.max(0, 120000 - s.length));
  };
  return 'naver.js 준비됨 · ' + location.host;
})();
