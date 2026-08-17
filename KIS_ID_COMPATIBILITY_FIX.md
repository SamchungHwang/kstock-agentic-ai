# KIS 관심종목 ID 호환 수정

- 표준 환경변수: `KIS_HTS_ID`
- 의미: 기존 한국투자증권 HTS/홈페이지 로그인 ID
- PAPER/LIVE 공통으로 같은 ID 하나 사용
- 기존 `KIS_USER_ID`, 이전 패치의 `KIS_HTS_USER_ID`도 호환용으로 읽음
- 계좌번호/App Key를 USER_ID로 잘못 재사용하지 않음
- 기존 PAPER/LIVE App Key, App Secret, Account 변수는 변경하지 않음
