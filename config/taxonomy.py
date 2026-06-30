"""카테고리 택소노미 (정본). slug = 정본 키, 표시명/하위토픽은 프롬프트·렌더용."""

# slug -> (표시명, [하위 토픽 예시])
CATEGORIES = {
    "ds_algo":       ("자료구조/알고리즘", ["해시", "트리", "정렬", "시간복잡도", "그래프 탐색"]),
    "network":       ("네트워크",         ["TCP/IP", "HTTP(S)", "로드밸런싱", "쿠키/세션", "CORS"]),
    "os":            ("운영체제",         ["프로세스/스레드", "동기화", "메모리", "스케줄링"]),
    "database":      ("데이터베이스",     ["정규화", "인덱스", "트랜잭션/격리수준", "락"]),
    "java":          ("언어/런타임(Java)", ["JVM", "GC", "컬렉션", "동시성"]),
    "spring":        ("프레임워크(Spring)", ["DI/IoC", "AOP", "트랜잭션", "JPA"]),
    "web_backend":   ("웹/백엔드 일반",   ["REST", "인증/인가", "캐싱", "멱등성", "세션/토큰"]),
    "frontend":      ("프론트엔드 연관",  ["브라우저 렌더링", "CSR/SSR", "스토리지", "보안(XSS/CSRF)"]),
    "infra":         ("인프라/배포",      ["Docker", "CI/CD", "클라우드 기초", "모니터링"]),
    "system_design": ("시스템 디자인",    ["확장성", "캐시 전략", "메시지큐"]),
}

# 정본 slug 목록
SLUGS = list(CATEGORIES.keys())

# 균등 가중치(약점 보강 시에만 조정). slug -> weight
CATEGORY_WEIGHTS = {slug: 1.0 for slug in SLUGS}

# 난이도 단계 (정본 표기)
DIFFICULTIES = ["기초", "중급", "심화"]


def display_name(slug: str) -> str:
    return CATEGORIES[slug][0]


def subtopics(slug: str) -> list[str]:
    return CATEGORIES[slug][1]
