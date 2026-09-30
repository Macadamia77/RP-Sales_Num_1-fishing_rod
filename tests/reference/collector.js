// collector.js · 인천 콜리스트 공백 채우기 조회 스크립트 · 2026-09-28
//
// 실행 위치: Claude 앱 내장 브라우저에서 https://www.114.co.kr 을 연 탭의 콘솔
//   카카오 로컬 API, KB부동산, 집품, 114On을 이 한 화면에서 모두 부를 수 있음
// 하는 일: 조회만 함. 건물명·대표번호 판정은 merge.py 가 함
// 결과는 탭 메모리와 브라우저 IndexedDB 두 곳에 저장. 탭이 닫혀도 같은 브라우저에서 다시 주입하고 __resume() 하면 이어짐
//
// 순서
//   1. 이 파일 전체를 주입
//   2. __setKey('카카오 REST 키')                         키는 파일이나 문서에 적지 않음
//   3. inject_000.js ... 를 차례로 주입. 각 결과의 검증값을 meta.json 과 대조
//   4. __start('A')  카카오. 동시 4개
//   5. __start('B')  KB부동산·집품. 한 건씩 0.35초
//   6. __loadQueue114([...])  후 __start('C')  114On. 한 건씩 4.5초. merge.py 가 만든 q114_*.js 를 주입하면 자동으로 들어감
//   7. __status() 로 진행 확인. 긴 작업은 백그라운드로 돌고 도구 호출은 바로 끝남
//   8. __dump('A', 0, 300) 처럼 잘라서 꺼냄. 결과가 커서 도구가 파일로 저장하면 ingest.py 로 작업 폴더에 넣음
//   탭이 닫혔으면 이 파일을 다시 주입하고 __setKey 후 await __resume('구', '동'). 입력, 114On 대기열, 끝난 결과가 IndexedDB에서 돌아옴
(function () {
  const W = window;
  W.__C = W.__C || { key: '' };
  W.__REG = W.__REG || null;          // {gu, dong}
  W.__IN = W.__IN || [];              // [i, road, jib, n0, nt, pt]  도로명·지번은 '인천광역시 구' 뺀 짧은 형태
  W.__ST = W.__ST || { A: {}, B: {}, C: {} };
  W.__Q114 = W.__Q114 || [];
  W.__RUN = W.__RUN || {};
  W.__BLOCK = false;
  const SIDO = '인천광역시';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  W.__setKey = k => { W.__C.key = k; return 'ok'; };

  // ---------- IndexedDB ----------
  const DBN = 'gongbaek_v1';
  function idb() { return new Promise((res, rej) => { const r = indexedDB.open(DBN, 1); r.onupgradeneeded = () => { const d = r.result; for (const s of ['IN', 'A', 'B', 'C']) if (!d.objectStoreNames.contains(s)) d.createObjectStore(s); }; r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }); }
  async function put(store, key, val) { try { const d = await idb(); await new Promise((res, rej) => { const t = d.transaction(store, 'readwrite'); t.objectStore(store).put(val, key); t.oncomplete = res; t.onerror = () => rej(t.error); }); } catch (e) { console.warn('idb put', e); } }
  async function getPrefix(store, prefix) { const d = await idb(); return new Promise((res, rej) => { const out = {}; const t = d.transaction(store, 'readonly'); const c = t.objectStore(store).openCursor(); c.onsuccess = () => { const cur = c.result; if (!cur) return res(out); if (String(cur.key).startsWith(prefix)) out[String(cur.key).slice(prefix.length)] = cur.value; cur.continue(); }; c.onerror = () => rej(c.error); }); }
  const rk = () => W.__REG ? `${W.__REG.gu}_${W.__REG.dong}:` : '';

  // ---------- 입력 ----------
  W.__loadInput = function (reg, rows) {
    if (W.__REG && (W.__REG.gu !== reg.gu || W.__REG.dong !== reg.dong)) { W.__IN = []; W.__ST = { A: {}, B: {}, C: {} }; W.__Q114 = []; }
    W.__REG = reg;
    const have = new Set(W.__IN.map(x => x[0]));
    for (const r of rows) if (!have.has(r[0])) { W.__IN.push(r); have.add(r[0]); }
    put('IN', `${reg.gu}_${reg.dong}`, W.__IN);
    const chk = [rows.length, rows.reduce((a, x) => a + x[0], 0), rows.reduce((a, x) => a + x[1].length + x[2].length + x[3].length, 0)];
    return { chunk_check: chk, total_rows: W.__IN.length };
  };
  W.__resume = async function (gu, dong) {
    W.__REG = { gu, dong };
    const all = await getPrefix('IN', ''); W.__IN = all[`${gu}_${dong}`] || []; W.__Q114 = all[`${gu}_${dong}#q114`] || [];
    for (const s of ['A', 'B', 'C']) W.__ST[s] = await getPrefix(s, rk());
    return __status();
  };

  // ---------- 주소 키 ----------
  const nr = s => { if (!s) return ''; return String(s).replace('인천광역시', '인천').replace(/\s*\([^)]*\)/g, ' ').split(',')[0].replace(/\s+/g, ' ').trim(); };
  const nj = s => { if (!s) return ''; let t = String(s).replace('인천광역시', '인천').replace(/\s*\([^)]*\)/g, ' '); t = t.replace(/(\d+)\s*번지\s*(\d+)\s*호/, '$1-$2').replace(/번지/g, '').replace(/(\d+)\s*호\s*$/, ''); t = t.replace(/([가-힣]+?)\d+동/g, '$1동'); return t.replace(/\s+/g, ' ').trim(); };
  const dist = (x1, y1, x2, y2) => { if (x1 == null || x2 == null) return null; const r = Math.PI / 180; return Math.round(Math.hypot((x2 - x1) * Math.cos(y1 * r) * 111320, (y2 - y1) * 110540)); };
  const core = s => String(s || '').replace(/\s+|아파트|오피스텔|빌라|주택|\(.*?\)/g, '');
  const isMg = n => /관리사무소|관리실|관리단|관리소|관리센터|입주자대표회의/.test(n || '');
  const isBldg = (c, n) => !!c && c.startsWith('부동산') && !/부동산서비스|중개|고시원|고시텔|원룸|하숙|셰어|쉐어|숙박/.test(c) && !isMg(n);
  W.__keys = { nr, nj };

  // ---------- 카카오 ----------
  async function kj(url) {
    let last = '';
    for (let t = 0; t < 6; t++) {
      try { const r = await fetch(url, { headers: { Authorization: 'KakaoAK ' + W.__C.key } }); if (r.ok) return await r.json(); last = 'HTTP ' + r.status; if (r.status === 401) throw new Error('카카오 키 오류 401'); }
      catch (e) { if (String(e).includes('401')) throw e; last = String(e); }
      await sleep(600 * Math.pow(2, t));
    }
    throw new Error('kakao fail ' + last);
  }
  const kaddr = async q => ((await kj('https://dapi.kakao.com/v2/local/search/address.json?query=' + encodeURIComponent(q))).documents || []);
  async function kkw(q, x, y, radius, maxPage) {
    let out = [];
    for (let p = 1; p <= (maxPage || 3); p++) {
      let u = 'https://dapi.kakao.com/v2/local/search/keyword.json?query=' + encodeURIComponent(q) + '&page=' + p + '&size=15';
      if (x && y && radius) u += `&x=${x}&y=${y}&radius=${radius}`;
      const j = await kj(u); out = out.concat(j.documents || []); if (!j.meta || j.meta.is_end) break;
    }
    return out;
  }
  const kcat = async (code, x, y, r) => ((await kj(`https://dapi.kakao.com/v2/local/search/category.json?category_group_code=${code}&x=${x}&y=${y}&radius=${r}&sort=distance`)).documents || []);

  // 1단계 · 건물 1곳
  async function procA(b) {
    const [i, road, jib, n0, nt, pt] = b; const P = SIDO + ' ' + W.__REG.gu + ' ';
    const roadQ = road ? P + road : '', jibQ = jib ? P + jib : '';
    const log = [];
    const adR = roadQ ? await kaddr(roadQ) : [];
    const adJ = jibQ ? await kaddr(jibQ) : [];
    const first = adR[0] || adJ[0];
    let gx = first ? Number(first.x) : null, gy = first ? Number(first.y) : null;
    const bnR = adR[0] && adR[0].road_address ? adR[0].road_address.building_name || '' : '';
    const bnJ = adJ[0] && adJ[0].road_address ? adJ[0].road_address.building_name || '' : '';
    // 주소 묶기 · 원본 도로명·지번, 도로명 검색과 지번 검색이 알려준 도로명·지번
    const R = new Set(), J = new Set();
    if (roadQ) R.add(nr(roadQ)); if (jibQ) J.add(nj(jibQ));
    for (const d of [adR[0], adJ[0]]) { if (!d) continue; if (d.road_address) R.add(nr(d.road_address.address_name)); if (d.address) J.add(nj(d.address.address_name)); }
    log.push(`카카오 주소검색 도로명 ${adR.length ? '성공' + (bnR ? ', 건물명 ' + bnR : ', 건물명 없음') : (roadQ ? '결과 없음' : '생략')} · 지번 ${adJ.length ? '성공' + (bnJ ? ', 건물명 ' + bnJ : ', 건물명 없음') : (jibQ ? '결과 없음' : '생략')}`);
    const inB = d => R.has(nr(d.road_address_name)) || J.has(nj(d.address_name));
    const P2 = {}; const add = (docs, src) => { for (const d of docs) { if (P2[d.id]) continue; const m = inB(d); const dd = gx ? dist(gx, gy, Number(d.x), Number(d.y)) : null; if (!m && !(dd != null && dd <= 200)) continue; P2[d.id] = [d.id, d.place_name, d.category_name, d.phone, d.place_url, +(+d.x).toFixed(6), +(+d.y).toFixed(6), d.road_address_name, d.address_name, m ? 1 : 0, dd, src]; } };
    // 장소 검색 · 원본 도로명, 원본 지번, 그리고 원본과 다른 카카오 지번
    const qs = [];
    if (roadQ) qs.push(roadQ); if (jibQ) qs.push(jibQ);
    for (const d of [adR[0], adJ[0]]) if (d && d.address && nj(d.address.address_name) !== nj(jibQ)) qs.push(d.address.address_name);
    const cnt = [];
    for (const q of [...new Set(qs)]) { const docs = await kkw(q); add(docs, 'a'); cnt.push(`"${q}" ${docs.length}건`); }
    const places = Object.values(P2);
    if (!gx && places.length) { const m = places.find(p => p[9]); if (m) { gx = m[5]; gy = m[6]; } }
    log.push(`카카오 장소검색: ${cnt.join(', ')} · 주소 일치 ${places.filter(p => p[9]).length}곳`);
    // 임시 건물명 · 원본, 도로명주소 건물명, 건물 장소 순
    const bp = places.find(p => p[9] && isBldg(p[2], p[1]));
    const pn = n0 || bnR || bnJ || (bp ? bp[1] : '');
    // 건물명 재검색 · 번호 대상이고 이름이 있으면 반경 1km
    if (pt && pn && core(pn).length >= 2) {
      const a1 = await kkw(pn, gx, gy, gx ? 1000 : null, 1); const a2 = await kkw(pn + ' 관리사무소', gx, gy, gx ? 1000 : null, 1);
      add([...a1, ...a2], 'rs'); log.push(`카카오 건물명 재검색 "${pn}": ${a1.length + a2.length}건`);
    }
    // 주변 공인중개사 300m
    let ag = [];
    if (pt && gx) { ag = (await kcat('AG2', gx, gy, 300)).filter(d => d.phone).slice(0, 8).map(d => [d.place_name, d.phone, +d.distance, d.place_url]); }
    return { i, g: gx ? [+gx, +gy] : null, bnR, bnJ, R: [...R], J: [...J], P: Object.values(P2), ag, pn, log };
  }

  // ---------- KB부동산 · 집품 ----------
  if (!W.__origFetch) { W.__origFetch = W.fetch; W.fetch = (u, o = {}) => { const c = new AbortController(); const t = setTimeout(() => c.abort(), 10000); return W.__origFetch(u, { ...o, signal: c.signal }).finally(() => clearTimeout(t)); }; }
  async function kbS(q) { const u = 'https://api.kbland.kr/land-complex/serch/intgraSerch?' + new URLSearchParams({ '검색설정명': 'SRC_NTOTAL', '검색키워드': q, '출력갯수': '10', '페이지설정값': '1' }); const r = await fetch(u); if (!r.ok) throw new Error('KB ' + r.status); const j = await r.json(); const d = j.dataBody && j.dataBody.data && j.dataBody.data.data || {}; return [...((d.HSCM && d.HSCM.data) || []).map(x => ({ t: 'HSCM', ...x })), ...((d.VILLA && d.VILLA.data) || []).map(x => ({ t: 'VILLA', ...x }))]; }
  async function kbM(no) { const r = await fetch('https://api.kbland.kr/land-complex/complex/complexMain?' + new URLSearchParams({ '단지기본일련번호': no })); if (!r.ok) throw new Error('KBM ' + r.status); const j = await r.json(); return j.dataBody && j.dataBody.data || {}; }
  async function zpS(q) { const r = await fetch('https://live.zippo-om.com/api/v1/buildings/search/autoComplete?keyword=' + encodeURIComponent(q)); if (!r.ok) throw new Error('ZP ' + r.status); const j = await r.json(); return (j.payload || []).map(x => x.buildingDocument || {}); }
  const shortA = s => String(s || '').replace(/^인천(광역시)?\s*[가-힣]+(구|군)\s*/, '').replace(/\s*\(.*$/, '').replace(/번지.*$/, '').trim();
  const sq = s => String(s || '').replace(/\s+/g, '');
  const badNm = n => { const t = String(n || '').trim(); return sq(t).length < 2 || /^[가-힣]+\d*(동|리|가)\s*\d/.test(t) || /^(다세대|연립|도시형|아파트|주택|빌라|오피스텔|근린생활시설)\s*(\(.*\))?$/.test(t) || /^(가|나|다|라|[A-Z]|\d+)동$/.test(t) || /^[\d\-\s]+$/.test(t); };
  const cleanKb = n => String(n || '').trim().replace(/\.+$/, '').replace(/\.\(/, '(').replace(/\((도|고층|저층|신|구|\d+(-\d+)?)\)\s*$/, '').trim().replace(/\.+$/, '').trim();

  // 2단계 · 건물 1곳
  async function procB(b) {
    const [i, road, jib, n0, nt, pt] = b; const gu = W.__REG.gu; const GAP = 350;
    const A = W.__ST.A[i] || {}; const out = { i, log: [], P: [] };
    const isMatch = x => (jib && sq(shortA(x.JUSO_ARNO)) === sq(jib)) || (road && sq(shortA(x.NEWADDRESS)) === sq(road));
    const needKB = pt || (nt && !A.pn);
    let m = null;
    if (needKB) {
      if (jib) { const d = await kbS(jib); await sleep(GAP); m = d.find(isMatch); out.log.push(`KB부동산 지번검색 "${jib}": ${d.length}건${m ? ' 주소일치' : ''}`); }
      if (!m && road) { const d = await kbS(gu + ' ' + road); await sleep(GAP); m = d.find(isMatch); out.log.push(`KB부동산 도로명검색 "${gu} ${road}": ${d.length}건${m ? ' 주소일치' : ''}`); }
      if (m && m.COMPLEX_NO) { const mm = await kbM(m.COMPLEX_NO); await sleep(GAP); out.kb = { no: m.COMPLEX_NO, t: m.t, nm: m.HSCM_NM || '', addr: m.JUSO_ARNO || '', road: m.NEWADDRESS || '', main_nm: mm['단지명'] || '', tel: mm['관리사무소전화번호내용'] || '', hh: mm['총세대수'] || '' }; out.log.push(`KB부동산 단지정보: ${out.kb.main_nm}, 관리사무소 전화 ${out.kb.tel || '없음'}`); }
    }
    if (nt && !A.pn) {
      const q = SIDO + ' ' + gu + ' ' + (road || jib); const z = await zpS(q); await sleep(GAP);
      const zm = z.find(x => (road && sq(shortA(x.address)) === sq(road)) || (jib && sq(shortA(x.oldAddress)) === sq(jib)));
      if (zm) { const nm = zm.buildingName || ''; out.zp = { id: zm.buildingId, nm, type: zm.buildingType, generic: !nm || /^[가-힣]+\d*(동|리|가)\s*\d/.test(nm) }; out.log.push(`집품 주소검색: 주소일치 ${out.zp.generic ? '이름 없음 ' + nm : nm} · ${zm.buildingType || ''}`); }
      else out.log.push(`집품 주소검색 "${q}": ${z.length}건, 주소일치 없음`);
      out.zq = q;
    }
    // 새 이름 · 집품 이름, 없으면 KB 단지명
    let nn = '';
    if (!A.pn) { if (out.zp && !out.zp.generic && !badNm(out.zp.nm)) nn = out.zp.nm; else if (out.kb) { const k = cleanKb(out.kb.main_nm || out.kb.nm); if (!badNm(k)) nn = k; } }
    out.nn = nn;
    // 새 이름으로 카카오 재검색
    if (nn && pt && core(nn).length >= 2 && A.g) {
      const R = new Set(A.R || []), J = new Set(A.J || []); const [gx, gy] = A.g;
      const a1 = await kkw(nn, gx, gy, 1000, 1); const a2 = await kkw(nn + ' 관리사무소', gx, gy, 1000, 1);
      for (const d of [...a1, ...a2]) { const mm = R.has(nr(d.road_address_name)) || J.has(nj(d.address_name)); const dd = dist(gx, gy, +d.x, +d.y); if (!mm && !(dd != null && dd <= 200)) continue; out.P.push([d.id, d.place_name, d.category_name, d.phone, d.place_url, +(+d.x).toFixed(6), +(+d.y).toFixed(6), d.road_address_name, d.address_name, mm ? 1 : 0, dd, 'rs2']); }
      out.log.push(`카카오 건물명 재검색 "${nn}": ${a1.length + a2.length}건`);
    }
    return out;
  }

  // ---------- 114On ----------
  async function o114(q, lat, lng) {
    const body = { query: q, localcode: '', upjongcode: '', filter: '', localname: '', upjongname: '', collection: 'ALL', latitude: lat || 37.4639, longitude: lng || 126.6798 };
    const r = await W.__origFetch('/action/search', { method: 'POST', headers: { 'Content-Type': 'application/json;charset=UTF-8', 'Request-Type': 'action' }, body: JSON.stringify(body) });
    const tx = await r.text();
    if (!tx.startsWith('{')) { W.__BLOCK = true; throw new Error('BLOCK ' + r.status); }
    const sr = (JSON.parse(tx).data || {}).search || {}; const out = [];
    for (const c of ['dbdata', 'register', 'report', 'keynumber', 'spl']) for (const d of ((sr[c] && sr[c].Document) || [])) { const f = d.Field || {}; out.push({ c, nm: f.COMP_KOR_NM || f.COMP_NM || '', tel: f.TEL00 || (f.DDD && f.TEL ? f.DDD + '-' + f.TEL : f.TEL) || '', road: f.ROAD_ADDR || '', addr: f.ADDR || '', up: f.CST_UPJONG_NM || '' }); }
    return out;
  }
  const strip114 = s => String(s || '').replace(/^인천(광역시)?\s*[가-힣]+(구|군)\s*/, '').trim();
  const k114R = s => { const m = strip114(s).match(/^([가-힣A-Za-z0-9]+(?:로|길))\s*(\d+(?:-\d+)?)/); return m ? m[1] + ' ' + m[2] : ''; };
  // 지번 키 · "주안1동 137번지 2호" → "주안동 137-2", "항동1가 12" → "항동1가 12", "강화읍 관청리 123" → "강화읍 관청리 123"
  const k114J = s => { const m = strip114(s).match(/^(?:([가-힣]+[읍면])\s+)?([가-힣]+\d+가|[가-힣]+?\d*동|[가-힣]+리)\s*(\d+)(?:번지)?\s*(?:-(\d+)|(\d+)호)?/); if (!m) return ''; let dong = m[2]; if (/동$/.test(dong)) dong = dong.replace(/\d+동$/, '동'); const sub = m[4] || m[5]; return (m[1] ? m[1] + ' ' : '') + dong + ' ' + m[3] + (sub && sub !== '0' ? '-' + sub : ''); };
  const k114S = s => { const m = strip114(s).match(/^([가-힣A-Za-z0-9]+(?:로|길))\s*$/); return m ? m[1] : ''; };
  const fmtTel = t => { const d = String(t || '').replace(/\D/g, ''); if (!d) return ''; if (/^02/.test(d)) return d.length === 9 ? d.replace(/^(02)(\d{3})(\d{4})$/, '$1-$2-$3') : d.replace(/^(02)(\d{4})(\d{4})$/, '$1-$2-$3'); if (/^1[5-9]\d{2}/.test(d) && d.length === 8) return d.replace(/^(\d{4})(\d{4})$/, '$1-$2'); if (d.length === 11) return d.replace(/^(\d{3})(\d{4})(\d{4})$/, '$1-$2-$3'); if (d.length === 10) return d.replace(/^(\d{3})(\d{3})(\d{4})$/, '$1-$2-$3'); return t; };
  W.__k114 = { k114R, k114J, k114S };
  const nameEq = (a, b) => { const x = core(a), y = core(b); if (x.length < 2 || y.length < 2) return false; if (x === y) return true; const [s, l] = x.length < y.length ? [x, y] : [y, x]; return l.includes(s) && s.length / l.length >= 0.7; };
  const stripMg = n => String(n || '').replace(/\s*(관리사무소|관리실|관리단|관리소|관리센터|입주자대표회의).*$/, '').trim();

  // 5단계 · 건물 1곳. q = [i, road, jib, name, lat, lng]
  async function procC(q) {
    const [i, road, jib, name, lat, lng] = q; const P = SIDO + ' ' + W.__REG.gu + ' ';
    const street = (road || '').split(' ')[0] || '';
    const jk = jib ? jib.replace(/(\d+)-0$/, '$1') : '';
    const hit = d => (road && k114R(d.road) === road) || (jk && k114J(d.addr) === jk);
    const weak = d => street && k114S(d.road) === street && !k114J(d.addr);
    const excl = d => /고시원|고시텔|원룸|숙박|상가/.test((d.up || '') + ' ' + (d.nm || ''));
    const nmOK = name && name.replace(/\s+/g, '').length >= 2;
    const isRep = d => (isMg(d.nm) && (!nmOK || nameEq(stripMg(d.nm), name) || hit(d))) || (nmOK && nameEq(d.nm, name) && !excl(d));
    const link = s => 'https://www.114.co.kr/search/result/all?query=' + encodeURIComponent(s);
    const out = { i, log: [], pool: [], ph: null }; const seen = new Set();
    const push = (arr, via, s) => { for (const d of arr) { if (!d.tel) continue; const key = d.nm + '|' + d.tel; if (seen.has(key)) continue; const h = hit(d); const w = !h && via === '건물명검색' && weak(d) && nmOK && nameEq(stripMg(d.nm), name) && !excl(d); if (!h && !w) continue; seen.add(key); const x = { nm: d.nm, tel: fmtTel(d.tel), up: d.up, road: d.road, addr: d.addr, c: d.c, via, link: link(s) }; if (!out.ph && (w || isRep(d))) out.ph = { v: x.tel, src: '114On ' + via + ' ' + (isMg(d.nm) ? '관리사무소' : '건물 대표번호') + (w ? ' · 번지 비공개, 도로명·건물명 일치' : ''), name: d.nm, link: link(s), weak: !!w }; else if (h) out.pool.push(x); } };
    const GAP = 4500; let nR = 0;
    if (road) { const s = P + road; const r = await o114(s, lat, lng); await sleep(GAP); nR = r.filter(hit).length; push(r, '도로명검색', s); out.log.push(`114On 도로명검색 "${s}": ${r.length}건, 주소일치 ${nR}곳`); }
    if (!nR && jib) { const s = P + jib; const r = await o114(s, lat, lng); await sleep(GAP); push(r, '지번검색', s); out.log.push(`114On 지번검색 "${s}": ${r.length}건, 주소일치 ${r.filter(hit).length}곳`); }
    if (!out.ph && nmOK) { const r = await o114(name, lat, lng); await sleep(GAP); push(r, '건물명검색', name); out.log.push(`114On 건물명검색 "${name}": ${r.length}건, 주소일치 ${r.filter(d => hit(d) || weak(d)).length}곳`); }
    if (out.ph) out.log.push('114On 대표번호 후보: ' + out.ph.v + ' / ' + out.ph.src + ' / ' + out.ph.name);
    out.t = Date.now();
    return out;
  }
  W.__loadQueue114 = function (reg, rows) { if (!W.__REG || W.__REG.gu !== reg.gu || W.__REG.dong !== reg.dong) return '지역이 다름. 먼저 __resume(구, 동)'; const have = new Set(W.__Q114.map(x => x[0])); for (const r of rows) if (!have.has(r[0])) W.__Q114.push(r); put('IN', `${reg.gu}_${reg.dong}#q114`, W.__Q114); return { chunk_check: [rows.length, rows.reduce((a, x) => a + x[0], 0)], total: W.__Q114.length }; };

  // ---------- 실행 ----------
  async function runStage(stage) {
    const st = W.__RUN[stage] = { stage, running: true, done: 0, err: 0, started: Date.now(), last: '' };
    const store = W.__ST[stage];
    try {
      if (stage === 'A') {
        const todo = W.__IN.filter(b => !store[b[0]] || store[b[0]].err); let qi = 0;
        const worker = async () => { while (qi < todo.length && !st.stop) { const b = todo[qi++]; try { store[b[0]] = await procA(b); st.done++; } catch (e) { store[b[0]] = { i: b[0], err: String(e) }; st.err++; st.last = String(e); if (String(e).includes('401')) { st.stop = true; } } put('A', rk() + b[0], store[b[0]]); } };
        await Promise.all([1, 2, 3, 4].map(worker));
      } else if (stage === 'B') {
        for (const b of W.__IN) { if (st.stop) break; if (store[b[0]] && !store[b[0]].err) continue; if (!W.__ST.A[b[0]] || W.__ST.A[b[0]].err) continue; try { store[b[0]] = await procB(b); st.done++; } catch (e) { store[b[0]] = { i: b[0], err: String(e) }; st.err++; st.last = String(e); await sleep(3000); } put('B', rk() + b[0], store[b[0]]); }
      } else if (stage === 'C') {
        let blocks = 0;
        for (const q of W.__Q114) {
          if (st.stop) break; if (store[q[0]] && !store[q[0]].err) continue;
          try { store[q[0]] = await procC(q); st.done++; put('C', rk() + q[0], store[q[0]]); }
          catch (e) {
            st.err++; st.last = String(e);
            if (W.__BLOCK) { blocks++; st.blocks = blocks; if (blocks >= 4) { st.last = '차단 4회로 멈춤'; break; } st.sleeping = true; await sleep(75 * 60 * 1000); st.sleeping = false; W.__BLOCK = false; }
            else { store[q[0]] = { i: q[0], err: String(e) }; put('C', rk() + q[0], store[q[0]]); await sleep(10000); }
          }
        }
      }
    } finally { st.running = false; st.ended = Date.now(); }
  }
  W.__start = function (stage) { if (!W.__REG) return '입력이 없음'; if (stage !== 'A' && stage !== 'B' && stage !== 'C') return 'A, B, C 중 하나'; if (stage === 'A' && !W.__C.key) return '__setKey 먼저'; if (W.__RUN[stage] && W.__RUN[stage].running) return '이미 실행 중'; runStage(stage); return '시작 ' + stage; };
  W.__stop = function (stage) { if (W.__RUN[stage]) W.__RUN[stage].stop = true; return '멈춤 요청 ' + stage; };
  W.__status = function () {
    const n = W.__IN.length; const c = s => Object.values(W.__ST[s]).filter(x => !x.err).length; const e = s => Object.values(W.__ST[s]).filter(x => x.err).length;
    const run = {}; for (const k in W.__RUN) { const r = W.__RUN[k]; run[k] = { running: r.running, done: r.done, err: r.err, last: r.last, sleeping: !!r.sleeping, blocks: r.blocks || 0, min: Math.round(((r.ended || Date.now()) - r.started) / 60000) }; }
    return { region: W.__REG, input: n, A: [c('A'), e('A')], B: [c('B'), e('B')], q114: W.__Q114.length, C: [c('C'), e('C')], run };
  };
  // 꺼내기 · 도구 결과가 커서 파일로 저장되도록 뒤에 채움 문자를 붙임
  W.__dump = function (stage, from, count) {
    const order = stage === 'C' ? W.__Q114.map(q => q[0]) : W.__IN.map(b => b[0]);
    const ids = order.slice(from, from + count); const rows = {}; for (const i of ids) if (W.__ST[stage][i]) rows[i] = W.__ST[stage][i];
    const s = JSON.stringify({ stage, region: W.__REG, from, count: ids.length, n: Object.keys(rows).length, rows });
    return s + '\n' + '~'.repeat(Math.max(0, 120000 - s.length));
  };
  return 'collector.js 준비됨 · ' + (W.__REG ? JSON.stringify(W.__REG) : '입력 없음');
})();
