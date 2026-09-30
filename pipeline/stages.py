"""단계 실행기

규칙
  · 이미 성공한 행은 건너뛴다. 실패로 기록된 행은 다음 실행 때 다시 시도한다
  · 한 건 끝날 때마다 저장소에 바로 쓴다
  · 일반 오류가 max_errors 건(수집설정.toml [limits], 기본 3) 쌓이면 멈춘다. 같은 원인이 반복될 가능성이 높기 때문
  · 인증 오류·호출 한도 초과·차단·예상 밖 응답(FatalError)은 즉시 멈춘다
  · Ctrl+C 는 그대로 위로 올려 보낸다. 끝난 행은 이미 저장되어 있다
  · 진행 상황은 progress_every 건(기본 20)마다 출력
"""
import threading
from dataclasses import dataclass

from . import credentials
from .errors import FatalError, StageStopped
from .settings import current as settings


@dataclass
class StageResult:
    total: int = 0
    done: int = 0
    err: int = 0
    skipped: int = 0


def _err_value(stage, key, e):
    k = 'key' if stage == 'NV' else 'i'
    return {k: key, 'err': credentials.mask(f'Error: {e}')}


def run_stage(stage, grp, items, key_of, fn, store, transport, label, workers=1, after_error_sleep=0.0,
              max_errors=None, log=print):
    """items 중 성공 기록이 없는 것만 fn(item)으로 조회해 저장한다"""
    S = settings()
    max_errors = max_errors or S.max_errors
    every = S.progress_every
    have = store.ok_keys(stage, grp)
    todo = [it for it in items if str(key_of(it)) not in have]
    res = StageResult(total=len(todo), skipped=len(items) - len(todo))
    if not todo:
        return res
    lock = threading.Lock()
    state = {'stop': None, 'next': 0}

    def one(it):
        key = key_of(it)
        transport.begin(stage, key)
        try:
            v = fn(it)
            store.put(stage, grp, key, v, True)
            with lock:
                res.done += 1
        except FatalError as e:
            store.put(stage, grp, key, _err_value(stage, key, e), False)
            with lock:
                res.err += 1
                if not state['stop']:
                    state['stop'] = StageStopped(credentials.mask(f'{label} 중단 · {e}'), fatal=True)
        except Exception as e:  # noqa: BLE001 · 그 건만 실패로 기록하고 계속
            store.put(stage, grp, key, _err_value(stage, key, e), False)
            with lock:
                res.err += 1
                if res.err >= max_errors and not state['stop']:
                    state['stop'] = StageStopped(credentials.mask(f'{label} 오류 {res.err}건으로 중단 · 마지막 오류 {e}'))
            if after_error_sleep:
                transport.sleep(after_error_sleep)
        finally:
            transport.end()
        with lock:
            n = res.done + res.err
            if n % every == 0 or n == res.total:
                log(f'  {label} {n}/{res.total} · 오류 {res.err}')

    if workers <= 1:
        for it in todo:
            if state['stop']:
                break
            one(it)
    else:
        def worker():
            while True:
                with lock:
                    if state['stop'] or state['next'] >= len(todo):
                        return
                    it = todo[state['next']]
                    state['next'] += 1
                one(it)
        ths = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
        for t in ths:
            t.start()
        try:
            for t in ths:
                while t.is_alive():
                    t.join(0.5)
        except KeyboardInterrupt:
            with lock:
                state['stop'] = StageStopped('Ctrl+C')
            for t in ths:
                t.join(15)
            raise
    if state['stop']:
        raise state['stop']
    return res
