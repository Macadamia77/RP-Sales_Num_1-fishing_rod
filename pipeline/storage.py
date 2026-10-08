"""작업 저장소 · SQLite, 잠금, 코드 해시

한 건 조회할 때마다 SQLite에 바로 저장한다 (전원이 꺼져도 그 건까지는 남음).
단계가 끝나면 판정기(judge/merge.py)가 읽는 JSON 파일(A.json 등)을 만든다.
"""
import datetime
import hashlib
import json
import os
import sqlite3
import threading

from .errors import JobLocked

PIPE_DIR = os.path.dirname(os.path.abspath(__file__))


def now_iso():
    return datetime.datetime.now().isoformat(timespec='seconds')


def code_hash():
    """pipeline/ 안의 .py 파일(하위 폴더 포함, 판정 코드 judge/ 도 포함)을 해시. 루트 파일은 포함하지 않음"""
    h = hashlib.sha256()
    files = []
    for root, dirs, fs in os.walk(PIPE_DIR):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for f in fs:
            if f.endswith('.py'):
                files.append(os.path.join(root, f))
    for p in sorted(files, key=lambda x: os.path.relpath(x, PIPE_DIR).replace(os.sep, '/')):
        rel = os.path.relpath(p, PIPE_DIR).replace(os.sep, '/')
        with open(p, 'rb') as f:
            data = f.read().replace(b'\r\n', b'\n')   # 줄바꿈 방식이 바뀌어도 같은 해시
        h.update(rel.encode('utf-8') + b'\0' + hashlib.sha256(data).digest())
    return h.hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, obj):
    """임시 파일에 쓴 뒤 바꿔치기. 쓰다가 멈춰도 원래 파일이 깨지지 않음"""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


class JobLock:
    """OS 파일 잠금. 같은 작업을 두 곳에서 동시에 돌리지 못하게 함. 프로그램이 죽으면 OS가 잠금을 푼다"""

    def __init__(self, path):
        self.path = path
        self.f = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.f = open(self.path, 'a+')
        try:
            if os.name == 'nt':
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            self.f = None
            raise JobLocked('같은 작업이 다른 창에서 실행 중. 그 실행이 끝난 뒤 다시 실행')
        return self

    def __exit__(self, *exc):
        if self.f:
            try:
                if os.name == 'nt':
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            finally:
                self.f.close()
                self.f = None


class Store:
    """조회 결과 저장소. 행 = (단계, 그룹, 키). ok=1이면 성공, 0이면 실패 기록(다음 실행 때 다시 시도)"""

    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS rows (stage TEXT, grp TEXT, key TEXT, ok INTEGER, value TEXT, updated TEXT, '
                        'PRIMARY KEY (stage, grp, key))')

    def close(self):
        with self.lock:
            self.db.close()

    def put(self, stage, grp, key, value, ok):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO rows VALUES (?,?,?,?,?,?)',
                            (stage, grp, str(key), 1 if ok else 0, json.dumps(value, ensure_ascii=False), now_iso()))

    def ok_keys(self, stage, grp):
        with self.lock:
            return {r[0] for r in self.db.execute('SELECT key FROM rows WHERE stage=? AND grp=? AND ok=1', (stage, grp))}

    def all(self, stage, grp):
        with self.lock:
            return {r[0]: json.loads(r[1]) for r in self.db.execute('SELECT key, value FROM rows WHERE stage=? AND grp=?', (stage, grp))}

    def counts(self, stage, grp):
        with self.lock:
            r = self.db.execute('SELECT SUM(ok=1), SUM(ok=0) FROM rows WHERE stage=? AND grp=?', (stage, grp)).fetchone()
        return int(r[0] or 0), int(r[1] or 0)

    def export(self, stage, grp, path):
        """판정기가 읽는 JSON 파일로 내보냄. 실패 행도 {'err': ...} 형태로 들어감 (원본 형식과 같음)"""
        write_json(path, self.all(stage, grp))
