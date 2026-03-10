코드 변경사항의 보안 정책 위반을 즉시 점검합니다. PR 전 또는 의심스러운 코드 추가 후 실행합니다.

security-agent를 호출하여 변경된 파일을 점검합니다:

```bash
git diff master --name-only
```

## 점검 항목
1. **민감 정보 하드코딩** - DB 비밀번호, API 키
2. **SQL Injection** - f-string SQL 조합
3. **DB 쓰기 권한 위반** - database-design 외에서 INSERT/UPDATE/DELETE
4. **개인정보 노출** - 사용자 ID 원문 로그 출력
5. **.gitignore 누락** - .env 등

## 결과
- 이슈 0건: "보안 점검 통과 - PR 진행 가능"
- 이슈 있음: 파일명, 행 번호, 수정 방법 제시
