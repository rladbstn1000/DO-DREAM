# 06. 자원 범위 검토와 체크포인트

## 분리한 과거 판정

팀 기준은 `4c763af2316ebb00f523bc43b0c29e49ef7bf62e`, 이번 시작 HEAD는 `8414eec66d7acb5d37794b6f0fcb6f31d3acb48c`다. 기존 54개 변경의 크기·SHA256가 최종 2-A 검증 목록과 모두 일치했고, 소스/테스트/문서를 대조했다. 출처가 구분되는 `docs/.DS_Store`는 보존하고 제외했다. 명시적인 후속 사용자 승인에 따라 2-A 체크포인트 `ef91856cdc8a96c0e0d28a63e89f6efc8e85be3b`를 생성했다. 과거 커밋 보류 사유와 보안 실패6개는 05 문서에 그대로 남는다.

과거 외부 컨테이너33개 중 ETCH6개의 ID가 교체됐다. 기존 이름·상태는 같았지만 ID 보존은 FAIL이다. 기존 볼륨/네트워크 이름 보존과 이 판정을 합쳐 PASS로 바꾸지 않는다.

| 이름 | 과거 before ID | 과거 after ID | 상태 |
|---|---|---|---|
| etch-phase6-rc-verify-logstash-1 | 98fc58060dc4 | 8744a68a38cc | exited |
| etch-phase6-rc-verify-backend-1 | f215b237f670 | ed9358e3859f | exited |
| etch-phase6-rc-verify-elasticsearch-1 | c3b04bd44eb8 | 8ba8f6c6515b | exited |
| etch-phase6-rc-backend-1 | a39cc575e99e | a5606be8b6a5 | running |
| etch-phase6-rc-elasticsearch-1 | d1a9567b26a4 | 5977d8e5132f | running |
| etch-phase6-rc-mysql-1 | 678427ab3f71 | 4327c057577f | running |

최초 metadata/event 조회는 Docker 연결 불가로 BLOCKED였다. 연결 복구 후 위6개 이름의 ID·생성시각·상태·Compose 라벨을 읽었다. `2026-09-29T11:17:53.288623+00:00`부터 `11:57:00+00:00`까지 종료되는 lifecycle 이벤트 조회는 exit0, 해당6개 이벤트0개였다. 보존된 이벤트가 없다는 사실은 과거 변경이 없었거나 특정 주체가 실행했다는 근거가 아니다. 원인 귀속은 UNVERIFIED다. 다른 프로젝트의 Env·명령 인자·앱 로그·파일·셸 이력·다른 대화는 읽지 않았다. ETCH를 재시작/복원하지 않았다.

증거: `.local/phase2b/review/historical-external-review.json`. 원본 `.local/phase2a/results/resources-{before,after}.json`과 strict 검사 기대값은 변경하지 않았다.

## 현재 실행 범위

`manage.py`는 명시적인 작업 디렉터리·Compose 파일·생성된 `.local/env`·프로젝트 `dodream-phase1`을 사용한다. `scope_guard.py`는 실제 변경 전에 로컬 unix Docker endpoint, 렌더링된 Compose 설정, 기존 볼륨4개/네트워크2개의 프로젝트 라벨, 컨테이너 프로젝트+서비스 허용 목록을 확인한다. 컨테이너 이름만으로 소유를 인정하지 않는다.

허용 서비스는 mysql/redis/be/ai/worker/python-service/web 및 검사 be-test/be-auth-short/web-auth-test다. 일회성 run은 이번 작업 이름·라벨·`--rm --no-deps`를 요구하며 timeout 정리는 라벨을 재검증한 단일 ID에만 적용한다. 알 수 없는 서비스·프로젝트/파일 override·down/rm/prune·Redis FLUSH를 거부한다. 이는 저장소 실행 경로의 제한이지 임의의 셸 프로그램 전체를 격리하는 보안 샌드박스는 아니다.

외부 프로젝트가 DO:DREAM의 볼륨·네트워크·빌드 이미지 태그·workspace 바인드를 참조하면 변경을 차단한다. 허용되지 않은 자체 mount/network도 차단한다. 공개 포트는 nginx의 loopback만 허용하며 충돌 프로세스를 종료하지 않는다. DB 포트는 공개하지 않는다. 기존4개 볼륨이 없거나 소유가 확인되지 않으면 새 환경으로 교체하지 않는다.

2-B의 local 저장 대역 검증을 위해 ai/worker에 기존 `be-data`의 read-only mount를 추가한다. DO:DREAM 내부에서 합성 JSON을 읽는 의도된 공유다. 기존 데이터 재소유/초기화는 하지 않는다. 다른 프로젝트의 자원 목록은 변경 명령에 전달하지 않는다.

`python3 scripts/local/manage.py scope-test`: 합성 명령/metadata 단위검사33개 PASS, exit0. `config`: exit0. 연결 복구 후 `scope`: 실제 target 검증 PASS, exit0. 새 `.local/phase2b/results/resources-before.json`에는 자체9개 컨테이너 모두 exited, 외부33개, 전체 볼륨31개/네트워크12개가 기록됐다. 변경 전 snapshot은 한번만 저장하고 덮어쓰지 않는다.

현재 명령 범위, 새 외부 ID 보존, 자체 데이터 보존은 각각 출력한다. 실행 종료 뒤의 결과는 08에 기록한다. 과거/현재 외부 ID 변화만으로 명령 범위를 추정하지 않고 관측 범위 밖의 직접·간접 영향 부재를 보장하지 않는다.
