"""오류 종류

Fatal 계열은 한 건만의 문제가 아니라 계속하면 전부 실패하거나 차단이 심해지는 경우다.
단계 실행기는 Fatal을 만나면 즉시 멈추고, 일반 오류는 3건까지 기록하며 넘어간다.
"""


class PipelineError(Exception):
    """이 프로그램이 일부러 내는 오류의 부모"""


class UsageError(PipelineError):
    """사용법·입력 오류. 종료 코드 2"""


class FatalError(PipelineError):
    """즉시 중단해야 하는 오류"""


class AuthError(FatalError):
    """401·403 · 키가 틀렸거나 구독이 없음"""


class RateLimitError(FatalError):
    """429 · 호출 한도 초과"""


class BlockedError(FatalError):
    """사이트가 요청을 막음 (114On이 JSON 대신 차단 화면을 줄 때 등)"""


class UnexpectedResponse(FatalError):
    """리다이렉트, JSON이 아님, 예상과 다른 응답 구조. 「결과 없음」으로 처리하면 틀린 결과가 쌓이므로 멈춘다"""


class RetryableError(PipelineError):
    """네트워크 오류·시간 초과·5xx. 조회 모듈이 정해진 횟수만큼 다시 시도"""


class RequestError(PipelineError):
    """그 밖의 4xx. 그 건만 실패로 기록"""


class MissingCredential(UsageError):
    """필요한 환경변수 키가 없음"""


class JobLocked(PipelineError):
    """같은 작업이 다른 곳에서 실행 중"""


class StageStopped(PipelineError):
    """단계가 중간에 멈춤. 완료된 행은 저장되어 있음"""

    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal
