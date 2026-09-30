# 04. 2-A 인증 보안 설계

기준 체크포인트: `8414eec66d7acb5d37794b6f0fcb6f31d3acb48c`. 파일/자료/퀴즈/RAG 객체 인가는 2-B이며 이 변경에서 완료로 처리하지 않는다.

## 실제 클라이언트 계약

- 교사 웹: `/api/auth/teacher/login`의 `accessToken`을 기존 localStorage에 저장하고 Authorization Bearer로 Spring/AI에 전달한다. Refresh Token은 HttpOnly cookie `refresh`에만 존재하며 웹 JSON 응답으로 주지 않는다.
- 교사와 학생의 cookie login/refresh/logout: CSRF bootstrap 후 POST. 만료된 AT가 Authorization에 함께 있어도 auth 경로에서 AT 필터가 refresh 처리를 막지 않는다. login은 비밀번호/기기 자격증명으로 인증하고, refresh/logout 컨트롤러는 RT를 엄격히 검증한다.
- 네이티브 학생: 기존 코드는 쿠키를 쓰지 않고 401 때 device credential로 재로그인했다. 새 `/api/auth/student/native/login`은 body `{deviceId, deviceSecret}`를 받는다. `native/refresh`와 `native/logout`은 body `{refreshToken}`을 받는다. login/refresh 응답은 `{accessToken, refreshToken}`, logout은200 빈 응답이다. native 경로는 ambient cookie를 인정하지 않는다. 임의 platform 헤더로 cookie 경로의 CSRF를 우회할 수 없다.
- 저장매체 전면 교체는 하지 않는다. localStorage의 XSS 토큰 탈취 위험은 남는다. native RT는 기존 MMKV에 저장하며 OS 보안 저장소 보호를 보장하지 않는다. 네이티브 저장소·생체인증의 실제 기기 검증은 후속 항목이다.

## 공통 JWT 계약

| 항목 | 정책 |
|---|---|
| 서명 | HS256만, 두 서버 동일 canonical Base64 해석, 디코드 키 최소32바이트. 빈/오류/짧은 키는 기동 실패. |
| 발급자 / 대상 | `iss=dodream`, 정확히 단일 `aud=dodream-api`(문자열 또는 원소1 배열). |
| 종류 | `token_use=access` 또는 `refresh`. 리소스는 access만, refresh/logout 컨트롤러는 refresh만. 이전 형식 fallback 없음. |
| 사용자 / 역할 | sub는 양의 Long 범위의 선행0 없는 문자열, role은 TEACHER 또는 STUDENT. |
| 고유성 | 발급마다 별도 canonical 소문자 UUID jti. 같은 초의 발급/회전도 토큰이 다름. |
| 시간 | iat/nbf/exp 필수, 정수 NumericDate(문자열·소수·bool 거부), 1..253402300799 범위, iat≤nbf<exp. |
| 수명 | AT900초, RT1,209,600초. 검증 시 최대수명도 제한. 일반 배포 AT단축/연장 임의 설정 불허. |
| 시계 오차 | 최대5초. 미래 iat/nbf 및 만료에 동일 기준. Redis 절대 만료는 RT exp이며 유예 때문에 저장 TTL을 늘리지 않음. |
| 기타 | 중복 JSON 키·8192자 초과 compact token 거부. name이 있으면 Unicode 공백만으로 이루어지지 않은 문자열이지만 인증 결정/로그에 불필요한 값을 출력하지 않음. |

서명/claims 검증을 통과하지 않으면 정해진 401을 반환한다. 다른 사용자 존재·원문 토큰·parser 상세 오류를 인증 오류에 붙이지 않는다. 정상 권한부족403은 토큰 갱신의 이유가 아니다. DB 장애와 잘못된 자격증명을 동일하게 성공/401로 감추지 않는다.

이전 AT/RT는 재로그인이 필요하다. 기존 Redis 키·다른 사용자 데이터는 삭제하지 않는다. 새로운 로그인만 새 형식 세션을 만든다.

## Redis 단일 세션 회전

기존 사용자당 현재 RT 하나 정책을 유지한다. 키는 `refresh:v2:<userId>`, 값은 원문 RT가 아닌 SHA-256 hex다. 이전 저장 키는 읽지 않으며 기존 TTL대로 남는다. 다중 기기·token family 저장 구조를 도입하지 않는다.

Lua 한 번으로 기존 값 존재/일치 → 새 해시 저장 → `PXAT` 절대 만료를 적용한다. 시각은 Redis TIME으로 확인한다. JVM synchronized나 GET 후 별도 SET에 의존하지 않는다. 같은 RT의 동시 요청은 정상 Redis에서 정확히 하나만 성공해야 한다. 실패한 요청은 새 상태를 덮어쓰거나 쿠키를 삭제하지 않는다.

로그인도 Redis 저장이 확인된 뒤에만 토큰을 응답한다. 회전 후 응답이 유실되면 이전 RT는 다시 허용하지 않으며 재로그인이 필요하다. 이를 위해 이전 토큰 grace/fallback을 만들지 않는다.

## 로그아웃·실패 범위

유효한 서명/종류/역할/기간의 RT로 로그아웃하면 **해당 사용자 현재 단일 세션 전체**를 원자적으로 DEL한다. 이미 회전된 RT로도 현재 세션을 폐기한다. 따라서 refresh가 먼저 성공해도 뒤의 logout이 새 RT를 지우고, logout이 먼저이면 refresh가 실패한다.

이 정책은 같은 사용자의 이후 로그인 세션도 유효한 이전 RT의 logout으로 폐기할 수 있다는 범위를 갖는다. 토큰 family별 선택 폐기·기기별 로그아웃을 보장하지 않는다. 존재하지 않는 키의 DEL 성공은 이미 폐기된 상태로 취급한다.

Redis 연결/저장/회전/폐기 오류는 503이고 로그인·refresh의 성공 토큰을 주지 않는다. 서버 폐기를 확인하지 못한 logout은 성공으로 응답하지 않는다. 잘못된 자격증명은401로 구분한다. 실패한 refresh/logout에서 cookie를 임의 삭제하여 다른 성공 응답과 경쟁시키지 않는다. 웹 UI는 실패를 알리고 로컬 인증 상태를 닫을 수 있지만 서버 폐기 성공을 주장하지 않는다.

AT denylist는 추가하지 않았다. 로그아웃 후 기존 AT가 만료+허용오차까지 유효할 수 있으며 테스트에서 이를 명시한다. 정상 단일 Redis의 원자성 검증을 복제 전환·백업 복구·Redis persistence 손실 후 부활 방지 보장으로 확대하지 않는다.

## 쿠키와 CSRF

Spring Security의 CookieCsrfTokenRepository를 사용한다. `/api/auth/csrf`에서 cookie와 `{token, headerName}`을 받고 `X-XSRF-TOKEN` 헤더로 제출한다. CSRF cookie의 값은 HttpOnly cookie의 자동 전달과 응답 token의 명시적 헤더를 함께 검증하는 데 사용한다. 웹 cookie 기반 login/refresh/logout은 CSRF가 없거나 다르면403이다. raw URI 대신 servlet의 decoded routing path로 비교하여 percent-encoded 경로도 같은 보호를 받는다.

Refresh cookie: HttpOnly, SameSite=Lax, Path=/api/auth. 발급·삭제에 같은 속성을 사용하고 Max-Age는 RT 실제 exp에 맞춘다. 배포 Secure=true, local/test HTTP만 Secure=false 허용. CORS·SameSite만으로 CSRF가 해결됐다고 보지 않는다. 네이티브는 cookie를 사용하지 않는 전용 body-token 경로이며 인증 세션 변경 경로 중 native 경로만 CSRF 예외다. 기존 bearer API와 공개 경로 전체의 CSRF 정책을 개편한 것은 아니다.

## 웹 경쟁 처리

동시401은 하나의 refresh promise로 모은다. 원래 요청은 갱신이 필요한 경우에만 최대1회 재시도하고, auth login/refresh/logout 자체는 이 재시도 경로에 넣지 않는다.403은 그대로 호출자에게 전달한다. 늦게 도착한 이전 AT의401은 이미 바뀐 AT를 사용하고 추가 refresh를 만들지 않는다.

세션 세대와 취소 처리를 통해 이전 login/refresh/API 응답이 logout 이후 또는 새 로그인 상태를 덮어쓰지 못하게 한다. refresh 실패는 진행 중 작업을 종료하고 로그인 안내로 전환한다. HTTPOnly Set-Cookie 전달 자체는 JavaScript 세대 검사로 취소할 수 없으므로 서버의 사용자 단위 세션 폐기가 logout/refresh 경쟁의 보안 근거다.

## 테스트 분리

일반 서비스는900초 그대로다. 별도 `auth-test` Compose 프로필의 `be-auth-short`만 AT2초, 실제 웹과 같은 이미지의 `web-auth-test`만 loopback15174를 사용한다. 기존 MySQL/Redis 데이터는 유지하며 합성 계정만 사용한다. 실제 브라우저의 만료/쿠키/CSRF/refresh를 확인하는 경로다. 정상Redis 동시성은12개 독립HTTP클라이언트×3라운드, logout/refresh는 장벽을 둔3라운드를 사용한다.

실제 결과·미검증 범위·예상된 2-B 실패는 [05-phase2a-results.md](05-phase2a-results.md)에 별도로 기록한다.
