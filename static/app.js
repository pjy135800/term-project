document.addEventListener("DOMContentLoaded", () => {
    const startDate = document.querySelector('input[name="start_date"]');
    const endDate = document.querySelector('input[name="end_date"]');
    if (startDate && endDate && !startDate.value && !endDate.value) {
        const start = new Date();
        start.setDate(start.getDate() + 1);
        const end = new Date(start);
        end.setDate(end.getDate() + 13);
        startDate.value = start.toISOString().slice(0, 10);
        endDate.value = end.toISOString().slice(0, 10);
    }

    const tabs = document.querySelectorAll(".mode-tab");
    const panels = document.querySelectorAll(".mode-panel");
    tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            tabs.forEach((item) => item.classList.toggle("active", item === tab));
            panels.forEach((panel) => panel.classList.toggle("active", panel.id === tab.dataset.panel));
        });
    });

    const copyButton = document.querySelector(".copy-code");
    if (copyButton) {
        copyButton.addEventListener("click", async () => {
            await navigator.clipboard.writeText(copyButton.dataset.copy);
            const feedback = document.getElementById("copy-feedback");
            if (feedback) {
                feedback.textContent = "복사됨";
                window.setTimeout(() => { feedback.textContent = ""; }, 1500);
            }
        });
    }

    const memberTable = document.getElementById("member-table");
    if (memberTable) {
        const poll = async () => {
            try {
                const response = await fetch(memberTable.dataset.statusUrl, { cache: "no-store" });
                if (!response.ok) return;
                const data = await response.json();
                const rows = new Map(
                    [...memberTable.querySelectorAll("[data-member-id]")].map((row) => [Number(row.dataset.memberId), row])
                );

                data.members.forEach((member) => {
                    const row = rows.get(member.id);
                    if (!row) {
                        window.location.reload();
                        return;
                    }
                    const state = row.querySelector(".submission-state");
                    state.textContent = member.submitted ? "제출 완료" : "작성 전";
                    state.classList.toggle("done", Boolean(member.submitted));
                    state.classList.toggle("pending", !member.submitted);
                });

                if (rows.size !== data.members.length) {
                    window.location.reload();
                    return;
                }

                const summary = document.getElementById("submit-summary");
                if (summary) {
                    const done = data.members.filter((member) => member.submitted).length;
                    summary.textContent = `${done} / ${data.members.length}명 제출`;
                }

                const compileButton = document.getElementById("compile-button");
                if (compileButton && data.all_submitted) {
                    compileButton.classList.remove("disabled");
                    compileButton.href = window.location.pathname + "/compile";
                }

                if (data.status === "finalized" && !document.querySelector(".result-band")) {
                    window.location.reload();
                }
            } catch (_error) {
                // 다음 주기에서 다시 시도한다.
            }
        };
        window.setInterval(poll, 3000);
    }

    document.querySelectorAll(".date-month").forEach((month) => {
        const count = month.querySelector(".month-selected-count");
        const checkboxes = month.querySelectorAll('input[name="date_choices"]');
        const refresh = () => {
            count.textContent = [...checkboxes].filter((item) => item.checked).length;
        };
        checkboxes.forEach((checkbox) => checkbox.addEventListener("change", refresh));
        refresh();
    });

    const surveyThemeCheckboxes = document.querySelectorAll('input[name="themes"]');
    const customThemes = document.getElementById("custom-themes");
    const themeSelectedCount = document.getElementById("theme-selected-count");
    const maxSurveyThemes = 5;
    const customThemeList = () => {
        if (!customThemes) return [];
        return [...new Set(customThemes.value.split(",").map((item) => item.trim()).filter(Boolean))];
    };
    const refreshSurveyThemeCount = () => {
        if (!themeSelectedCount) return;
        const presetCount = [...surveyThemeCheckboxes].filter((item) => item.checked).length;
        themeSelectedCount.textContent = presetCount + customThemeList().length;
    };
    surveyThemeCheckboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            const presetCount = [...surveyThemeCheckboxes].filter((item) => item.checked).length;
            if (presetCount + customThemeList().length > maxSurveyThemes) {
                checkbox.checked = false;
                window.alert(`테마는 직접 입력을 포함해 최대 ${maxSurveyThemes}개까지 선택할 수 있습니다.`);
            }
            refreshSurveyThemeCount();
        });
    });
    if (customThemes) {
        customThemes.addEventListener("input", refreshSurveyThemeCount);
    }
    refreshSurveyThemeCount();

    const themeCheckboxes = document.querySelectorAll('input[name="selected_themes"]');
    themeCheckboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            const selected = [...themeCheckboxes].filter((item) => item.checked);
            if (selected.length > 3) {
                checkbox.checked = false;
                window.alert("테마는 최대 3개까지 선택할 수 있습니다.");
            }
        });
    });
});
