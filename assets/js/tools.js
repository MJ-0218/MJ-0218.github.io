/* 셈터 계산기 — 계산 로직(순수 함수)과 화면 연결을 분리해 둠.
   순수 함수는 automation/scripts/test_tools.js 에서 node 로 검증한다. */
(function (root) {
  "use strict";

  var M2_PER_PYEONG = 400 / 121; // 1평 = 400/121 ㎡ ≈ 3.305785㎡ (1평 = 6자×6자)

  function toPyeong(m2) { return m2 / M2_PER_PYEONG; }
  function toM2(pyeong) { return pyeong * M2_PER_PYEONG; }

  /* 날짜는 모두 'YYYY-MM-DD' 문자열 ↔ UTC 자정으로 다뤄 시간대 오차를 없앤다 */
  function parseDate(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : NaN;
  }
  var DAY = 86400000;
  function daysBetween(a, b) { return Math.round((b - a) / DAY); }
  function addMonthsUTC(t, n) {
    var d = new Date(t), y = d.getUTCFullYear(), mo = d.getUTCMonth() + n, day = d.getUTCDate();
    var last = new Date(Date.UTC(y, mo + 1, 0)).getUTCDate();
    return Date.UTC(y, mo, Math.min(day, last));
  }
  function addYearsUTC(t, n) { return addMonthsUTC(t, 12 * n); }

  /* 퇴직금 (근로자퇴직급여 보장법 제8조)
     퇴직금 = 1일 평균임금 × 30 × (재직일수 / 365)
     1일 평균임금 = (퇴직 전 3개월 임금총액 + 연간 상여금×3/12 + 연차수당×3/12) / 그 3개월 총일수
     startDate: 입사일, lastDate: 마지막 근무일 (퇴직일 = 마지막 근무일 다음 날) */
  function severance(o) {
    var start = parseDate(o.startDate), last = parseDate(o.lastDate);
    if (isNaN(start) || isNaN(last) || last < start) return { error: "날짜를 확인해 주세요." };
    var retire = last + DAY;
    var serviceDays = daysBetween(start, retire);
    var periodStart = Math.max(addMonthsUTC(retire, -3), start);
    var periodDays = daysBetween(periodStart, retire);
    var wage3 = +o.wage3 || 0, bonus = +o.bonusYear || 0, leavePay = +o.leavePay || 0;
    var total = wage3 + bonus * 3 / 12 + leavePay * 3 / 12;
    var dailyAvg = periodDays > 0 ? total / periodDays : 0;
    var amount = dailyAvg * 30 * serviceDays / 365;
    return {
      serviceDays: serviceDays,
      periodDays: periodDays,
      dailyAvg: dailyAvg,
      amount: amount,
      eligible: serviceDays >= 365
    };
  }

  /* 연차 (근로기준법 제60조) — 입사일 기준, 출근율 80% 이상·상시 5인 이상 사업장 가정
     1년 미만: 1개월 개근마다 1일 (최대 11일)
     1년 이상: 15일 + 최초 1년을 초과하는 계속근로 2년마다 1일, 총 25일 한도 */
  function leaveForYear(yearsCompleted) {
    if (yearsCompleted < 1) return 0;
    return Math.min(25, 15 + Math.floor((yearsCompleted - 1) / 2));
  }
  function annualLeave(o) {
    var start = parseDate(o.startDate), ref = parseDate(o.refDate);
    if (isNaN(start) || isNaN(ref) || ref < start) return { error: "날짜를 확인해 주세요." };
    var years = 0;
    while (addYearsUTC(start, years + 1) <= ref) years++;
    var months = 0;
    if (years === 0) { while (months < 11 && addMonthsUTC(start, months + 1) <= ref) months++; }
    var nextGrant = addYearsUTC(start, years + 1);
    return {
      yearsCompleted: years,
      monthsCompleted: months,
      days: years === 0 ? months : leaveForYear(years),
      firstYearMonthly: years === 0,
      nextGrantDate: new Date(nextGrant).toISOString().slice(0, 10),
      nextGrantDays: leaveForYear(years + 1)
    };
  }

  var api = { M2_PER_PYEONG: M2_PER_PYEONG, toPyeong: toPyeong, toM2: toM2, severance: severance, annualLeave: annualLeave, leaveForYear: leaveForYear, parseDate: parseDate };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.Semter = api;

  /* ───────── 화면 연결 ───────── */
  var won = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });
  var num2 = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function today() {
    var d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 10);
  }
  function stamp(el, on) { if (el) el.classList.toggle("result--stamped", !!on); }

  var tools = {
    pyeong: function (form) {
      var mode = "m2";
      var input = $("#area", form), unit = $("#area-unit", form), out = $("#out", form), note = $("#note", form), box = $(".result", form);
      form.querySelectorAll(".seg button").forEach(function (b) {
        b.addEventListener("click", function () {
          mode = b.dataset.mode;
          form.querySelectorAll(".seg button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
          unit.textContent = mode === "m2" ? "㎡" : "평";
          run();
        });
      });
      function run() {
        var v = parseFloat(input.value);
        if (!(v > 0)) { out.innerHTML = "—"; note.textContent = "면적을 입력하면 바로 바뀝니다."; stamp(box, false); return; }
        if (mode === "m2") {
          out.innerHTML = num2.format(toPyeong(v)) + '<span class="u">평</span>';
          note.innerHTML = "<strong>" + num2.format(v) + "㎡</strong> = " + num2.format(v) + " ÷ 3.3058";
        } else {
          out.innerHTML = num2.format(toM2(v)) + '<span class="u">㎡</span>';
          note.innerHTML = "<strong>" + num2.format(v) + "평</strong> = " + num2.format(v) + " × 3.3058";
        }
        stamp(box, true);
      }
      input.addEventListener("input", run); run();
    },

    severance: function (form) {
      var f = { start: $("#start", form), last: $("#last", form), monthly: $("#monthly", form), wage3: $("#wage3", form), bonus: $("#bonus", form), leave: $("#leavepay", form) };
      var out = $("#out", form), note = $("#note", form), warn = $("#warn", form), box = $(".result", form);
      if (!f.last.value) f.last.value = today();
      f.monthly.addEventListener("input", function () {
        var m = parseFloat(f.monthly.value);
        if (m > 0) f.wage3.value = Math.round(m * 3);
        run();
      });
      function run() {
        var r = severance({ startDate: f.start.value, lastDate: f.last.value, wage3: f.wage3.value, bonusYear: f.bonus.value, leavePay: f.leave.value });
        warn.hidden = true;
        if (r.error || !(+f.wage3.value > 0)) { out.innerHTML = "—"; note.textContent = r.error || "입사일과 임금을 넣으면 계산합니다."; stamp(box, false); return; }
        out.innerHTML = won.format(r.amount) + '<span class="u">원</span>';
        note.innerHTML = "재직 <strong>" + won.format(r.serviceDays) + "일</strong> · 1일 평균임금 <strong>" + won.format(r.dailyAvg) + "원</strong> (3개월 " + r.periodDays + "일 기준)";
        if (!r.eligible) { warn.hidden = false; warn.textContent = "재직 1년 미만이면 법정 퇴직금 지급 대상이 아닙니다. 위 금액은 참고용입니다."; }
        stamp(box, r.eligible);
      }
      Object.keys(f).forEach(function (k) { if (k !== "monthly") f[k].addEventListener("input", run); });
      run();
    },

    "annual-leave": function (form) {
      var start = $("#start", form), ref = $("#ref", form), out = $("#out", form), note = $("#note", form), box = $(".result", form), tbody = $("#leave-table tbody");
      if (!ref.value) ref.value = today();
      function run() {
        var r = annualLeave({ startDate: start.value, refDate: ref.value });
        if (r.error) { out.innerHTML = "—"; note.textContent = start.value ? r.error : "입사일을 넣으면 계산합니다."; stamp(box, false); paint(-1); return; }
        out.innerHTML = r.days + '<span class="u">일</span>';
        note.innerHTML = r.firstYearMonthly
          ? "입사 1년 미만 · 개근한 달 <strong>" + r.monthsCompleted + "개월</strong>마다 1일씩 (최대 11일). <strong>" + r.nextGrantDate + "</strong>에 " + r.nextGrantDays + "일이 새로 생깁니다."
          : "근속 <strong>" + r.yearsCompleted + "년</strong> 기준. 다음 발생일 <strong>" + r.nextGrantDate + "</strong> → " + r.nextGrantDays + "일";
        stamp(box, true); paint(r.yearsCompleted);
      }
      function paint(y) {
        if (!tbody) return;
        tbody.querySelectorAll("tr").forEach(function (tr) { tr.classList.toggle("is-current", +tr.dataset.year === y); });
      }
      if (tbody) {
        var rows = "";
        for (var y = 1; y <= 21; y++) rows += '<tr data-year="' + y + '"><td>' + y + "년 차 완료</td><td class=\"num\">" + leaveForYear(y) + "일</td></tr>";
        tbody.innerHTML = rows;
      }
      start.addEventListener("input", run); ref.addEventListener("input", run); run();
    }
  };

  document.querySelectorAll("[data-tool]").forEach(function (form) {
    var fn = tools[form.dataset.tool];
    if (fn) fn(form);
  });
})(typeof window !== "undefined" ? window : this);
