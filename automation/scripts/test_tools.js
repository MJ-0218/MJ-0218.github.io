// 계산기 로직 검증: node automation/scripts/test_tools.js
const assert = require("assert");
const T = require("../../assets/js/tools.js");

const close = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg}: ${a} != ${b}`);

// 평수: 1평 = 400/121 ㎡
close(T.toPyeong(84), 25.41, 0.005, "84㎡");
close(T.toPyeong(59), 17.85, 0.005, "59㎡");
close(T.toM2(34), 112.40, 0.01, "34평");
close(T.toM2(T.toPyeong(123.4)), 123.4, 1e-9, "왕복");

// 퇴직금: 2021-03-02 입사, 2026-10-15 마지막 근무 → 퇴직일 10-16
let r = T.severance({ startDate: "2021-03-02", lastDate: "2026-10-15", wage3: 9600000, bonusYear: 4000000, leavePay: 0 });
assert.strictEqual(r.serviceDays, 2054);
assert.strictEqual(r.periodDays, 92); // 7/16 ~ 10/15
close(r.dailyAvg, (9600000 + 1000000) / 92, 1e-6, "평균임금");
close(r.amount, r.dailyAvg * 30 * 2054 / 365, 1e-6, "퇴직금");
assert.ok(r.eligible);
// 딱 1년: 2025-01-01 ~ 2025-12-31 → 365일, 대상
r = T.severance({ startDate: "2025-01-01", lastDate: "2025-12-31", wage3: 9000000 });
assert.strictEqual(r.serviceDays, 365); assert.ok(r.eligible);
// 1년 미만
r = T.severance({ startDate: "2025-01-02", lastDate: "2025-12-31", wage3: 9000000 });
assert.ok(!r.eligible);
assert.ok(T.severance({ startDate: "2026-01-01", lastDate: "2025-01-01" }).error);

// 연차 (근로기준법 §60)
assert.deepStrictEqual([1, 2, 3, 4, 5, 21, 30].map(T.leaveForYear), [15, 15, 16, 16, 17, 25, 25]);
let a = T.annualLeave({ startDate: "2026-01-15", refDate: "2026-04-14" });
assert.strictEqual(a.days, 2); // 2/15, 3/15 두 달 개근
a = T.annualLeave({ startDate: "2025-01-15", refDate: "2026-01-14" });
assert.strictEqual(a.days, 11); // 1년 미만 최대 11
a = T.annualLeave({ startDate: "2025-01-15", refDate: "2026-01-15" });
assert.strictEqual(a.days, 15); assert.strictEqual(a.yearsCompleted, 1);
a = T.annualLeave({ startDate: "2020-05-11", refDate: "2026-10-15" });
assert.strictEqual(a.yearsCompleted, 6); assert.strictEqual(a.days, 17);
assert.strictEqual(a.nextGrantDate, "2027-05-11");
// 말일 입사 → 월 단위 보정
a = T.annualLeave({ startDate: "2026-01-31", refDate: "2026-02-28" });
assert.strictEqual(a.days, 1);

console.log("tools.js: 모든 테스트 통과");
