# 세대 인벤토리와 거래 배정 민감도 분석

현재 운영 화면의 거래 분포는 신고 거래 **건수**다. 아래 두 스크립트는 연구용이며 `web/`에 파일을 생성하지 않는다. 호별 거래 연결이나 현 소유주의 매입가를 주장하지 않는다.

## 1. 건축HUB 전유부 접근

공공데이터포털의 [건축HUB 건축물대장정보 서비스](https://www.data.go.kr/data/15134735/openapi.do) 활용신청 후 `DATA_GO_KR_KEY`(디코딩 키)를 환경변수로 설정한다. 기존 RTMS 서비스 키와 별개로 이 서비스의 접근 권한이 필요하다. 키를 저장소에 커밋하지 않는다.

검증할 단지를 `data/unit_manifest.json`에 **명시적으로** 적는다. 예시는 형식만 보여준다. 주소·건물명·세대수는 건축물대장/단지 자료와 실제 대조하여 기입해야 한다.

```json
[
  {
    "complex_key": "실거래 complexes.json의 key",
    "sigunguCd": "5자리",
    "bjdongCd": "5자리",
    "bun": "4자리",
    "ji": "4자리",
    "platGbCd": "0",
    "building_names": ["전유부 응답의 정확한 bldNm"],
    "expected_units": 344
  }
]
```

```bash
python collector/unit_inventory.py --manifest data/unit_manifest.json --output data/units/inventory.json
```

단지명이 같은 필지의 다른 단지와 섞이거나 호수 중복·층/면적 누락·총 세대수 불일치가 있으면 생성이 중단된다. `expected_units`는 임시 동·층 슬롯 수가 아니라 외부에서 독립적으로 확인한 호별 세대수다. 결과 파일에는 **동·층·면적별 세대 수**만 남기며 호수는 기록하지 않는다. 인벤토리와 매핑 파일은 gitignored, 검증된 집계 결과도 자동 공개하지 않는다.

## 2. 같은 세대수를 사용한 F/D 비교

```bash
python collector/audit_unit_models.py \
  --inventory data/units/inventory.json \
  --complex-key '실거래 complexes.json의 key' \
  --band 35 \
  --output data/units/audit-35.json
```

- `F_all`: 동이 없던 과거 거래까지 포함, 층·면적 밴드별 세대수만큼 최신 거래 선택.
- `F_known`: 동 정보가 있는 거래만 대상으로 같은 F 풀 배정. `D_known`과 동일한 입력 집합으로 풀의 효과를 비교.
- `D_known`: 동·층·면적 밴드별 세대수만큼 동 정보가 있는 최신 거래 선택.
- `dong_missing`, `dong_unmatched`, `unfilled_slots`, `pre_2023_selected`를 같이 점검한다. 미매칭 동은 임의 추측으로 연결하지 않는다.

이 방법은 **선택 규칙의 민감도**를 측정한다. F와 D 모두 같은 세대의 재거래를 식별하지 못한다. 선택 거래의 가격 중앙값을 실제 소유주의 매수가 중앙값으로 표시하면 안 된다. `F_all`과 `D_known`의 차이에는 동 정보 누락에 따른 입력 표본 차이도 섞여 있다. 면적 밴드의 실제 호 구성과 건축물대장 자료의 기준시점 차이를 확인한 뒤 분석 결과를 해석한다.

호별 공시가격 CSV는 교차검증에 사용할 수 있지만 공시가격을 매입가격으로 취급하지 않는다. 단지·면적별 세대수, 동 표기, 건축물대장 연계 PK의 일치율을 별도로 기록해야 한다.
