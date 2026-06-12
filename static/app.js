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

    const homeActions = document.querySelectorAll(".home-action");
    const homeActionArea = document.querySelector(".home-actions");
    const brandWelcome = document.querySelector(".brand-welcome");
    homeActions.forEach((action) => {
        action.addEventListener("click", () => {
            panels.forEach((panel) => panel.classList.toggle("active", panel.id === action.dataset.panel));
            if (homeActionArea) homeActionArea.hidden = true;
            if (brandWelcome) brandWelcome.classList.add("compact-welcome");
        });
    });
    document.querySelectorAll(".panel-back").forEach((button) => {
        button.addEventListener("click", () => {
            panels.forEach((panel) => panel.classList.remove("active"));
            if (homeActionArea) homeActionArea.hidden = false;
            if (brandWelcome) brandWelcome.classList.remove("compact-welcome");
        });
    });

    const copyButton = document.querySelector(".copy-code");
    if (copyButton) {
        copyButton.addEventListener("click", async () => {
            const inviteUrl = copyButton.dataset.copy;
            try {
                await navigator.clipboard.writeText(inviteUrl);
            } catch (_error) {
                const temporaryInput = document.createElement("textarea");
                temporaryInput.value = inviteUrl;
                temporaryInput.setAttribute("readonly", "");
                temporaryInput.style.position = "fixed";
                temporaryInput.style.opacity = "0";
                document.body.appendChild(temporaryInput);
                temporaryInput.select();
                document.execCommand("copy");
                temporaryInput.remove();
            }
            const feedback = document.getElementById("copy-feedback");
            if (feedback) {
                feedback.textContent = "초대 링크 복사됨";
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
        const uniqueThemes = new Map();
        customThemes.value.split(",").map((item) => item.trim()).filter(Boolean).forEach((theme) => {
            const key = theme.replace(/\s+/g, "").toLocaleLowerCase("ko-KR");
            if (!uniqueThemes.has(key)) uniqueThemes.set(key, theme);
        });
        return [...uniqueThemes.values()];
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

    const rankedThemeSelects = [...document.querySelectorAll(".ranked-theme-select")];
    rankedThemeSelects.forEach((select) => {
        select.addEventListener("change", () => {
            if (!select.value) return;
            const duplicate = rankedThemeSelects.find(
                (other) => other !== select && other.value === select.value
            );
            if (duplicate) {
                select.value = "";
                window.alert("같은 테마를 여러 순위에 중복으로 선택할 수 없습니다.");
            }
        });
    });

    const randomGame = document.getElementById("random-theme-game");
    const randomGameButton = document.getElementById("start-random-game");
    const randomGameStatus = document.getElementById("random-game-status");
    const randomGameGuide = document.getElementById("random-game-guide");
    const randomReels = [...document.querySelectorAll(".random-reel")];
    if (randomGame && randomGameButton && randomReels.length) {
        let groups = [];
        try {
            groups = JSON.parse(randomGame.dataset.groups || "[]");
        } catch (_error) {
            groups = [];
        }

        const shuffled = (values) => {
            const copy = [...values];
            for (let index = copy.length - 1; index > 0; index -= 1) {
                const target = Math.floor(Math.random() * (index + 1));
                [copy[index], copy[target]] = [copy[target], copy[index]];
            }
            return copy;
        };

        const candidates = groups.flatMap((group) => group.items);
        const buildRankedResult = () => {
            const result = [];
            groups.forEach((group) => {
                if (result.length >= 3) return;
                const remaining = 3 - result.length;
                result.push(...shuffled(group.items).slice(0, remaining));
            });
            return result;
        };
        const firstTie = groups.find((group) => group.items.length > 1);
        if (firstTie && randomGameGuide) {
            const higherCount = groups
                .filter((group) => group.rank < firstTie.rank)
                .reduce((total, group) => total + group.items.length, 0);
            const openSlots = Math.max(0, 3 - higherCount);
            randomGameGuide.textContent = firstTie.items.length > openSlots
                ? `${firstTie.rank}위 동률 ${firstTie.items.length}개 중 남은 ${openSlots}자리와 순서를 추첨합니다.`
                : `${firstTie.rank}위 동률 테마들의 최종 추천 순서를 추첨합니다.`;
        }

        if (!candidates.length) {
            randomGameButton.disabled = true;
            randomGameStatus.textContent = "랜덤으로 뽑을 테마 후보가 없습니다.";
        }

        randomGameButton.addEventListener("click", () => {
            if (!candidates.length) return;

            randomGameButton.disabled = true;
            randomGameButton.textContent = "추첨 중...";
            randomGameStatus.textContent = "후보 테마를 섞고 있습니다.";
            randomReels.forEach((reel) => {
                reel.classList.remove("winner");
                reel.classList.add("spinning");
            });

            const visibleCount = Math.min(3, candidates.length);
            const animation = window.setInterval(() => {
                randomReels.forEach((reel, index) => {
                    const value = index < visibleCount
                        ? candidates[Math.floor(Math.random() * candidates.length)]
                        : "-";
                    const strong = reel.querySelector("strong");
                    if (strong) strong.textContent = value;
                });
            }, 90);

            window.setTimeout(() => {
                window.clearInterval(animation);
                const winners = buildRankedResult();
                randomReels.forEach((reel, index) => {
                    reel.classList.remove("spinning");
                    const strong = reel.querySelector("strong");
                    if (strong) strong.textContent = winners[index] || "-";
                    reel.classList.toggle("winner", index < winners.length);
                });

                rankedThemeSelects.forEach((select, index) => {
                    select.value = winners[index] || "";
                });
                randomGameStatus.textContent = `결정 완료: ${winners.map((theme, index) => `${index + 1}순위 ${theme}`).join(" · ")}`;
                randomGameButton.disabled = false;
                randomGameButton.textContent = "다시 돌리기";
            }, 2400);
        });
    }
});
