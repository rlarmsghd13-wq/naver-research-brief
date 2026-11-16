(function () {
  const dateSelect = document.getElementById("dateSelect");
  const metaSubtitle = document.getElementById("metaSubtitle");
  const pickTabs = document.getElementById("pickTabs");
  const articleContainer = document.getElementById("articleContainer");
  const themeToggle = document.getElementById("themeToggle");

  const lightboxModal = document.getElementById("lightboxModal");
  const lightboxImg = document.getElementById("lightboxImg");
  const lightboxCaption = document.getElementById("lightboxCaption");
  const lightboxClose = document.getElementById("lightboxClose");

  let currentData = null;
  let activePickIndex = 0;
  let activeChartIndex = 0;

  // ── 다크/라이트 테마 초기화 ──
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeToggle.textContent = theme === "dark" ? "☀️" : "🌙";
    localStorage.setItem("nrb_theme", theme);
  }
  const savedTheme = localStorage.getItem("nrb_theme") || "light";
  applyTheme(savedTheme);

  themeToggle.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    applyTheme(cur === "dark" ? "light" : "dark");
  });

  // ── 라이트박스 모달 ──
  function openLightbox(src, caption) {
    lightboxImg.src = src;
    lightboxCaption.textContent = caption || "차트 확대 보기";
    lightboxModal.classList.remove("hidden");
  }
  lightboxClose.addEventListener("click", () => lightboxModal.classList.add("hidden"));
  lightboxModal.addEventListener("click", (e) => {
    if (e.target === lightboxModal || e.target.classList.contains("lightbox-body")) {
      lightboxModal.classList.add("hidden");
    }
  });

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── 데이터 로드 ──
  async function loadDatesAndInit() {
    try {
      const datesResp = await fetch("data/dates.json?t=" + Date.now());
      if (datesResp.ok) {
        const { dates } = await datesResp.json();
        dateSelect.innerHTML = dates
          .map((d) => `<option value="${escapeHtml(d)}">${escapeHtml(d)}</option>`)
          .join("");
      }
    } catch (e) {
      console.warn("dates.json 로드 실패:", e);
    }

    await loadReportData("data/latest.json");
  }

  async function loadReportData(path) {
    try {
      const resp = await fetch(path + "?t=" + Date.now());
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      currentData = await resp.json();
      activePickIndex = 0;
      activeChartIndex = 0;

      if (dateSelect.value !== currentData.date) {
        const opt = Array.from(dateSelect.options).find((o) => o.value === currentData.date);
        if (opt) dateSelect.value = currentData.date;
      }

      metaSubtitle.textContent = `${currentData.date} 데일리 Pick ${currentData.count}선 · 생성 ${currentData.generated_at}`;
      renderTabs();
      renderArticle();
    } catch (err) {
      articleContainer.innerHTML = `
        <div class="loading-card">
          <p>리포트 데이터를 불러오지 못했습니다.<br/><small>${escapeHtml(err.message)}</small></p>
        </div>`;
    }
  }

  dateSelect.addEventListener("change", () => {
    const val = dateSelect.value;
    if (val) loadReportData(`data/archive/${val}.json`);
  });

  function renderTabs() {
    const picks = currentData?.picks || [];
    pickTabs.innerHTML = picks
      .map(
        (p, idx) => `
        <button class="pick-tab ${idx === activePickIndex ? "active" : ""}" data-idx="${idx}">
          <span class="tab-broker">${idx + 1}. ${escapeHtml(p.broker)}</span>
          <span class="tab-tag">${escapeHtml(p.category_tag)}</span>
        </button>`
      )
      .join("");

    pickTabs.querySelectorAll(".pick-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        activePickIndex = Number(btn.dataset.idx);
        activeChartIndex = 0;
        renderTabs();
        renderArticle();
      });
    });
  }

  function renderArticle() {
    const picks = currentData?.picks || [];
    const p = picks[activePickIndex];
    if (!p) return;

    const charts = p.charts || [];
    const curChart = charts[activeChartIndex] || charts[0];

    const chartHtml = curChart
      ? `
      <section class="chart-section">
        <div class="chart-header">
          <span class="chart-label">📊 ${escapeHtml(p.chart_title || "핵심 차트")}</span>
          <span class="zoom-hint">터치 시 확대 🔍</span>
        </div>
        <div class="chart-frame" id="chartFrame">
          <img src="${escapeHtml(curChart.url)}" alt="${escapeHtml(p.chart_title || p.title)}" />
        </div>
        ${
          charts.length > 1
            ? `<div class="chart-pager">
                ${charts
                  .map(
                    (c, i) =>
                      `<button class="chart-page-btn ${i === activeChartIndex ? "active" : ""}" data-cidx="${i}">차트 ${i + 1} (${c.page}p)</button>`
                  )
                  .join("")}
               </div>`
            : ""
        }
      </section>`
      : "";

    const takeawaysHtml = (p.key_takeaways || [])
      .map((t) => `<li>${escapeHtml(t)}</li>`)
      .join("");

    const glossaryHtml = (p.glossary || []).length
      ? `
      <section class="section-block">
        <h3 class="section-heading">📚 오늘의 금융 용어</h3>
        <div class="glossary-grid">
          ${p.glossary
            .map(
              (g) => `
            <div class="glossary-item">
              <div class="glossary-term">${escapeHtml(g.term)}</div>
              <div class="glossary-desc">${escapeHtml(g.desc)}</div>
            </div>`
            )
            .join("")}
        </div>
      </section>`
      : "";

    articleContainer.innerHTML = `
      <article class="article-card">
        <div class="article-meta">
          <span class="cat-pill">${escapeHtml(p.category_tag)}</span>
          <span class="meta-text">${escapeHtml(p.broker)} · ${escapeHtml(p.write_date)} · 원문 ${p.total_pages}p</span>
        </div>
        <h2 class="article-title">${escapeHtml(p.title)}</h2>

        ${chartHtml}

        <section class="section-block">
          <h3 class="section-heading">🎯 30초 핵심 결론</h3>
          <p class="summary-text">${escapeHtml(p.executive_summary)}</p>
        </section>

        <section class="section-block">
          <h3 class="section-heading">🔍 애널리스트 차트 독해 팁</h3>
          <div class="tip-box">${escapeHtml(p.chart_reading_tip)}</div>
        </section>

        <section class="section-block">
          <h3 class="section-heading">💡 나의 투자 액션 포인트</h3>
          <ul class="takeaway-list">${takeawaysHtml}</ul>
        </section>

        ${glossaryHtml}

        <div class="action-row">
          <a class="btn-primary" href="${escapeHtml(p.pdf_url)}" target="_blank" rel="noopener">📑 원본 PDF 열기</a>
          <a class="btn-secondary" href="${escapeHtml(p.naver_url)}" target="_blank" rel="noopener">🔗 네이버 원문</a>
        </div>
      </article>
    `;

    const chartFrame = document.getElementById("chartFrame");
    if (chartFrame && curChart) {
      chartFrame.addEventListener("click", () => {
        openLightbox(curChart.url, `${p.broker} · ${p.chart_title || p.title} (${curChart.page}p)`);
      });
    }

    articleContainer.querySelectorAll(".chart-page-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeChartIndex = Number(btn.dataset.cidx);
        renderArticle();
      });
    });
  }

  loadDatesAndInit();
})();
