(function () {
  const rootElement = document.getElementById("app-root");
  if (!window.React || !window.ReactDOM) {
    rootElement.innerHTML = "<main class=\"boot-error\"><h1>React non caricato</h1><p>Controlla la connessione: l'app usa React dal CDN ufficiale unpkg.</p></main>";
    return;
  }

  const { useEffect, useMemo, useState } = React;
  const h = React.createElement;

  const PAGES = {
    home: {
      title: "Home",
      kicker: "Benvenuto",
      description: "Esplora le potenzialità del tuo nuovo assistente allo studio.",
    },
    dashboard: {
      title: "Dashboard",
      kicker: "Oggi",
      description: "Una vista rapida su rendimento, prossimi impegni, documenti e comunicazioni.",
    },
    voti: {
      title: "Voti",
      kicker: "Rendimento",
      description: "Medie per periodo, media generale e dettaglio dei voti davvero utili.",
    },
    agenda: {
      title: "Agenda",
      kicker: "Calendario",
      description: "I giorni piu vicini e significativi, ordinati per priorita temporale.",
    },
    documenti: {
      title: "Documenti",
      kicker: "File",
      description: "Documenti e materiali leggibili nel programma, con download quando disponibile.",
    },
    bacheca: {
      title: "Bacheca",
      kicker: "Circolari",
      description: "Comunicazioni e allegati aperti in un viewer interno.",
    },
    planner: {
      title: "Planner",
      kicker: "Studio",
      description: "Un piano settimanale costruito dai dati del registro e dalle attivita manuali.",
    },
    attivita: {
      title: "Attivita",
      kicker: "To do",
      description: "Compiti personali e impegni da trasformare in sessioni di studio concrete.",
    },
    tutor: {
      title: "Tutor AI",
      kicker: "Chat",
      description: "Un assistente che usa voti, agenda, documenti e profilo della sessione corrente.",
    },
    profilo: {
      title: "Profilo",
      kicker: "Impostazioni",
      description: "Dati dello studente e preferenze che guidano il planner.",
    },
  };

  const NAV_GROUPS = [
    {
      title: "Scuola",
      links: [
        ["dashboard", "Panoramica"],
        ["voti", "Voti"],
        ["agenda", "Agenda"],
        ["documenti", "Documenti"],
        ["bacheca", "Bacheca"],
      ],
    },
    {
      title: "Studio",
      links: [
        ["planner", "Planner"],
        ["attivita", "Attivita"],
        ["tutor", "Tutor AI"],
        ["profilo", "Profilo"],
      ],
    },
  ];

  function toIso(date) {
    const copy = new Date(date);
    copy.setMinutes(copy.getMinutes() - copy.getTimezoneOffset());
    return copy.toISOString().slice(0, 10);
  }

  function parseIso(value) {
    const parsed = new Date(`${value}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
  }

  function addDays(value, days) {
    const date = typeof value === "string" ? parseIso(value) : new Date(value);
    date.setDate(date.getDate() + days);
    return date;
  }

  function addMonths(value, months) {
    const date = typeof value === "string" ? parseIso(value) : new Date(value);
    date.setMonth(date.getMonth() + months);
    return date;
  }

  function monthStart(value) {
    const date = typeof value === "string" ? parseIso(value) : new Date(value);
    return new Date(date.getFullYear(), date.getMonth(), 1);
  }

  function monthEnd(value) {
    const date = typeof value === "string" ? parseIso(value) : new Date(value);
    return new Date(date.getFullYear(), date.getMonth() + 1, 0);
  }

  function dateRange(startIso, days) {
    return Array.from({ length: days }, (_, index) => toIso(addDays(startIso, index)));
  }

  function todayIso(offsetDays = 0) {
    const date = new Date();
    date.setDate(date.getDate() + offsetDays);
    return toIso(date);
  }

  function schoolYearStart() {
    const now = new Date();
    const year = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
    return `${year}-09-01`;
  }

  function initialFilters() {
    return {
      day: todayIso(),
      start: schoolYearStart(),
      end: todayIso(60),
    };
  }

  function routeToPage() {
    const key = window.location.pathname.replace(/^\/+/, "").split("/")[0] || "home";
    if (key === "rendimento") {
      return "voti";
    }
    return PAGES[key] ? key : "home";
  }

  function formatDate(value, fallback = "Senza data") {
    if (!value) {
      return fallback;
    }
    const parsed = new Date(`${value}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleDateString("it-IT", { weekday: "short", day: "2-digit", month: "short" });
  }

  function formatLongDate(value, fallback = "Senza data") {
    if (!value) {
      return fallback;
    }
    const parsed = new Date(`${value}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "long" });
  }

  function dayDistance(value) {
    if (!value) {
      return 9999;
    }
    const today = new Date(`${todayIso()}T00:00:00`).getTime();
    const target = new Date(`${value}T00:00:00`).getTime();
    if (Number.isNaN(target)) {
      return 9999;
    }
    const days = Math.round((target - today) / 86400000);
    return Math.abs(days) + (days < 0 ? 2 : 0);
  }

  function shortDay(value) {
    const parsed = new Date(`${value}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) {
      return { day: "--", month: "" };
    }
    return {
      day: parsed.toLocaleDateString("it-IT", { day: "2-digit" }),
      month: parsed.toLocaleDateString("it-IT", { month: "short" }),
    };
  }

  function parseGradeNumber(grade) {
    if (typeof grade.numeric_grade === "number") {
      return grade.numeric_grade;
    }
    const raw = String(grade.grade || grade.display_grade || "").replace(",", ".");
    const match = raw.match(/\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  }

  function gradeTone(grade) {
    if (grade.contributes_to_average === false) {
      return "blue";
    }
    const value = parseGradeNumber(grade);
    if (value === null) {
      return "neutral";
    }
    return value >= 6 ? "green" : "red";
  }

  function numberText(value) {
    if (value === null || value === undefined || value === "") {
      return "n/d";
    }
    if (typeof value === "number") {
      return value.toLocaleString("it-IT", { maximumFractionDigits: 2 });
    }
    return String(value);
  }

  function classNames(...items) {
    return items.filter(Boolean).join(" ");
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      const error = payload.error || payload;
      throw new Error(error.message || payload.message || "Richiesta non riuscita");
    }
    return payload;
  }

  function section(pageData, key) {
    return pageData?.school?.sections?.[key] || null;
  }

  function sectionItems(pageData, key) {
    const value = section(pageData, key);
    if (!value || !value.ok) {
      return [];
    }
    return value.items || [];
  }

  function LandingPage({ onStart }) {
    useEffect(() => {
      if (window.gsap) {
        // Helper per dividere le lettere senza plugin esterni
        const splitText = (selector) => {
          const el = document.querySelector(selector);
          if (!el) return;
          const text = el.innerText;
          el.innerHTML = text.split(" ").map(word => 
            `<span class="word">${word.split("").map(char => `<span class="char">${char}</span>`).join("")}</span>`
          ).join(" ");
        };

        splitText(".hero-title");

        const tl = gsap.timeline();
        
        // WOW Hero Animation (Letter by Letter)
        tl.from(".hero-title .char", { 
          y: 150, 
          rotationX: -90, 
          stagger: 0.02, 
          opacity: 0, 
          duration: 1.2, 
          ease: "expo.out" 
        })
        .from(".hero-pills", { opacity: 0, scale: 0.5, duration: 0.8, ease: "back.out(1.7)" }, "-=0.6");

        // Floating Shapes (Smooth Parallax)
        gsap.to(".shape-1", { 
          y: 100, 
          x: 50, 
          rotation: 360,
          duration: 20, 
          repeat: -1, 
          yoyo: true, 
          ease: "none" 
        });
        
        gsap.to(".shape-2", { 
          y: -100, 
          x: -50, 
          rotation: -360,
          duration: 15, 
          repeat: -1, 
          yoyo: true, 
          ease: "none" 
        });

        // Horizontal Scroll with WOW factor
        if (window.ScrollTrigger) {
          const sections = gsap.utils.toArray(".horizontal-section");
          gsap.to(sections, {
            xPercent: -100 * (sections.length - 1),
            ease: "none",
            scrollTrigger: {
              trigger: ".horizontal-wrap",
              pin: true,
              scrub: 1,
              snap: 1 / (sections.length - 1),
              end: () => "+=" + document.querySelector(".horizontal-content").offsetWidth
            }
          });

          // Parallax e Reveal per il contenuto orizzontale
          sections.forEach(s => {
            gsap.from(s.querySelector("h2"), {
              x: 100,
              opacity: 0,
              scrollTrigger: {
                trigger: s,
                containerAnimation: gsap.to(sections, { xPercent: -100 * (sections.length - 1), ease: "none" }),
                start: "left center",
                scrub: true
              }
            });
          });
        }
      }
    }, []);

    return h("section", { className: "landing-page" }, [
      h("div", { className: "floating-shape shape-1", style: { top: "10%", left: "5%", width: "400px", height: "400px", background: "linear-gradient(45deg, var(--purple), var(--pink))", opacity: "0.2" }, key: "s1" }),
      h("div", { className: "floating-shape shape-2", style: { bottom: "10%", right: "5%", width: "500px", height: "500px", background: "linear-gradient(45deg, var(--blue), var(--green))", opacity: "0.2" }, key: "s2" }),

      h("div", { className: "hero-section", key: "hero" }, [
        h("div", { className: "hero-pills", key: "pills" }, [
          h("span", { className: "label-pill pink" }, "Next-Gen"),
          h("span", { className: "label-pill green", style: { marginLeft: "10px" } }, "Quantum Study"),
        ]),
        h("h1", { className: "hero-title" }, "Evolve your Learning. ZENITH."),
      ]),

      h("div", { className: "horizontal-wrap", key: "horiz" }, [
        h("div", { className: "horizontal-content" }, [
          h("div", { className: "horizontal-section" }, [
            h("span", { className: "gsap-box" }, "01"),
            h("h2", {}, "Deep Integration"),
            h("p", {}, "L'intero ecosistema ClasseViva, rielaborato per la tua mente.")
          ]),
          h("div", { className: "horizontal-section" }, [
            h("span", { className: "gsap-box", style: { background: "var(--pink)" } }, "02"),
            h("h2", {}, "Flow State"),
            h("p", {}, "Algoritmi che proteggono il tuo tempo e massimizzano il focus.")
          ]),
          h("div", { className: "horizontal-section" }, [
            h("span", { className: "gsap-box", style: { background: "var(--green)" } }, "03"),
            h("h2", {}, "Neural AI"),
            h("p", {}, "Il tuo tutor personale che evolve insieme ai tuoi voti.")
          ]),
        ])
      ]),

      h("div", { className: "huge-cta-section", key: "cta" }, [
        h("div", { className: "cta-huge", onClick: onStart }, "ASCEND NOW"),
        h("button", { className: "aura-btn", onClick: onStart }, "Initialize Zenith")
      ])
    ]);
  }

  function OnboardingPage({ session, onComplete }) {
    const [step, setStep] = useState(session?.onboarded ? 2 : 1);
    const [isLogin, setIsLogin] = useState(false);
    const [formData, setFormData] = useState({ email: "", name: "", school_level: "Superiori" });
    const [cvData, setCvData] = useState({ username: "", password: "" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    async function submitUserInfo(e) {
      e.preventDefault();
      setBusy(true);
      setError("");
      try {
        const payload = await api("/api/register", {
          method: "POST",
          body: JSON.stringify(isLogin ? { email: formData.email, name: "Login", school_level: "Superiori" } : formData),
        });
        setStep(2);
      } catch (err) {
        setError(err.message);
      } finally {
        setBusy(false);
      }
    }

    async function submitCvInfo(e) {
      e.preventDefault();
      setBusy(true);
      setError("");
      try {
        const payload = await api("/api/session", {
          method: "POST",
          body: JSON.stringify(cvData),
        });
        // Forza il ricaricamento della sessione o passa i dati corretti
        onComplete({ ...payload, authenticated: true, onboarded: true });
      } catch (err) {
        setError(err.message);
      } finally {
        setBusy(false);
      }
    }

    return h("section", { className: "onboarding-page" }, [
      h("div", { className: "onboarding-card", key: "card" }, [
        step === 1 ? h("div", { key: "step1" }, [
          h("h2", {}, isLogin ? "Bentornato" : "Dicci chi sei"),
          h("p", { className: "muted" }, isLogin ? "Inserisci la tua email per accedere." : "Queste informazioni ci aiutano a personalizzare la tua esperienza."),
          h("form", { className: "form-stack", onSubmit: submitUserInfo }, [
            !isLogin && h("label", { className: "field" }, [
              h("span", {}, "Nome Completo"),
              h("input", { required: true, value: formData.name, onChange: e => setFormData({ ...formData, name: e.target.value }) }),
            ]),
            h("label", { className: "field" }, [
              h("span", {}, "Email"),
              h("input", { type: "email", required: true, value: formData.email, onChange: e => setFormData({ ...formData, email: e.target.value }) }),
            ]),
            !isLogin && h("label", { className: "field" }, [
              h("span", {}, "Livello Scolastico"),
              h("select", {
                required: true,
                value: formData.school_level,
                onChange: e => setFormData({ ...formData, school_level: e.target.value }),
                className: "select-input"
              }, [
                h("option", { value: "Medie" }, "Medie"),
                h("option", { value: "Superiori" }, "Superiori"),
                h("option", { value: "Università" }, "Università"),
              ]),
            ]),
            error ? h("p", { className: "notice error" }, error) : null,
            h("button", { className: "button button-primary", type: "submit", disabled: busy }, busy ? "Verifica..." : "Avanti"),
            h("button", { 
              className: "button button-ghost", 
              type: "button", 
              onClick: () => setIsLogin(!isLogin),
              style: { marginTop: "12px", width: "100%" }
            }, isLogin ? "Non hai un account? Registrati" : "Hai già un account? Accedi"),
          ]),
        ]) : h("div", { key: "step2" }, [
          h("h2", {}, "Connetti ClasseViva"),
          h("p", { className: "muted" }, "Inserisci le tue credenziali per sincronizzare i dati scolastici."),
          h("form", { className: "form-stack", onSubmit: submitCvInfo }, [
            h("label", { className: "field" }, [
              h("span", {}, "Username"),
              h("input", { required: true, value: cvData.username, onChange: e => setCvData({ ...cvData, username: e.target.value }) }),
            ]),
            h("label", { className: "field" }, [
              h("span", {}, "Password"),
              h("input", { type: "password", required: true, value: cvData.password, onChange: e => setCvData({ ...cvData, password: e.target.value }) }),
            ]),
            error ? h("p", { className: "notice error" }, error) : null,
            h("button", { className: "button button-primary", type: "submit", disabled: busy }, busy ? "Connessione in corso..." : "Connetti"),
            h("button", { className: "button button-ghost", type: "button", onClick: () => setStep(1) }, "Indietro"),
          ]),
        ]),
      ]),
    ]);
  }

  function documentItems(pageData) {
    const docs = section(pageData, "documenti");
    if (!docs || !docs.ok) {
      return [];
    }
    return (docs.groups || []).flatMap((group) =>
      (group.items || []).map((item) => ({ ...item, group: group.title }))
    );
  }

  function uniqueItems(items) {
    const seen = new Set();
    return items.filter((item) => {
      const key = [item.id, item.date_iso, item.title, item.subtitle].filter(Boolean).join("|");
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }

  function groupBy(items, getter) {
    return items.reduce((groups, item) => {
      const key = getter(item);
      if (!groups[key]) {
        groups[key] = [];
      }
      groups[key].push(item);
      return groups;
    }, {});
  }

  function periodOptions(performance, grades = []) {
    const periods = performance?.period_averages || [];
    const counts = grades.reduce((acc, grade) => {
      const key = grade.period_key || "all";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    return [
      ...periods.map((period) => ({
        key: period.key,
        label: period.label,
        count: counts[period.key] || period.count || 0,
      })),
      {
        key: "all",
        label: "Tutto l'anno",
        count: grades.length,
      },
    ];
  }

  function selectedPeriodData(performance, selectedPeriod) {
    if (!performance) {
      return { label: "Periodo", overall_average: null, subject_averages: [] };
    }
    if (selectedPeriod === "all") {
      return {
        key: "all",
        label: "Tutto l'anno",
        overall_average: performance.overall_all_periods ?? performance.overall_average,
        subject_averages: performance.subject_averages_all_periods || performance.subject_averages || [],
      };
    }
    return (
      (performance.period_averages || []).find((period) => period.key === selectedPeriod) || {
        key: selectedPeriod,
        label: performance.active_period_label || "Periodo attivo",
        overall_average: performance.overall_average,
        subject_averages: performance.subject_averages || [],
      }
    );
  }

  function IconDot({ tone = "blue" }) {
    return h("span", { className: `icon-dot tone-${tone}`, "aria-hidden": "true" });
  }

  function Button({ children, tone = "secondary", type = "button", onClick, disabled, className = "" }) {
    return h(
      "button",
      { type, onClick, disabled, className: classNames("button", `button-${tone}`, className) },
      children
    );
  }

  function EmptyState({ title, body }) {
    return h("section", { className: "empty-state" }, [
      h("p", { className: "eyebrow", key: "k" }, "Vuoto"),
      h("h2", { key: "t" }, title),
      h("p", { className: "muted", key: "b" }, body),
    ]);
  }

  function MetricCard({ label, value, note, tone = "blue" }) {
    return h("article", { className: "metric-card" }, [
      h("div", { className: "metric-top", key: "top" }, [
        h(IconDot, { tone, key: "dot" }),
        h("span", { key: "label" }, label),
      ]),
      h("strong", { key: "value" }, numberText(value)),
      note ? h("p", { className: "muted", key: "note" }, note) : null,
    ]);
  }

  function PageHeader({ pageId, pageData, loading }) {
    const config = PAGES[pageId] || PAGES.dashboard;
    const overview = pageData?.overview || {};
    return h("header", { className: "page-header" }, [
      h("div", { key: "copy" }, [
        h("p", { className: "eyebrow", key: "k" }, config.kicker),
        h("h1", { key: "t" }, config.title),
        h("p", { className: "muted", key: "d" }, config.description),
      ]),
      h("div", { className: "header-chip", key: "chip" }, [
        h("span", { key: "label" }, loading ? "Synchronizing..." : "Active Zenith Profile"),
        h("strong", { key: "value" }, overview.display_name || overview.student_name || "Zenith Scholar"),
      ]),
    ]);
  }

  function Layout({ children, pageId, navigate, session, filters, setFilters, refresh, logout, loading }) {
    useEffect(() => {
      // Animazione di entrata per il workspace
      gsap.fromTo(".workspace", 
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.6, ease: "power3.out", clearProps: "all" }
      );
    }, [pageId]);

    return h("div", { className: "app-shell" }, [
      h("aside", { className: "rail", key: "rail" }, [
        h("a", { className: "brand", href: "/dashboard", onClick: (event) => navigate(event, "dashboard"), key: "brand" }, [
          h("span", { className: "brand-mark", key: "mark" }, "Z"),
          h("span", { className: "brand-text", key: "text" }, [
            h("strong", { key: "name" }, "Zenith"),
            h("small", { key: "tag" }, "peak performance study"),
          ]),
        ]),
        h("nav", { className: "nav", "aria-label": "Navigazione", key: "nav" },
          NAV_GROUPS.map((group) =>
            h("section", { className: "nav-section", key: group.title }, [
              h("p", { className: "nav-title", key: "title" }, group.title),
              ...group.links.map(([id, label]) =>
                h(
                  "a",
                  {
                    href: `/${id}`,
                    className: classNames("nav-link", pageId === id && "is-active"),
                    onClick: (event) => navigate(event, id),
                    key: id,
                  },
                  [h(IconDot, { tone: pageId === id ? "green" : "white", key: "dot" }), h("span", { key: "label" }, label)]
                )
              ),
            ])
          )
        ),
        session.authenticated
          ? h(FilterPanel, { filters, setFilters, refresh, logout, loading, key: "filters" })
          : h(LoginHint, { key: "login-hint" }),
      ]),
      h("main", { className: "workspace", key: "main" }, children),
    ]);
  }

  function LoginHint() {
    return h("section", { className: "side-card" }, [
      h("p", { className: "eyebrow", key: "k" }, "Accesso"),
      h("h2", { key: "t" }, "Connetti ClasseViva"),
      h("p", { className: "muted", key: "b" }, "Dopo l'accesso ogni sezione resta separata e la navigazione non riverifica la sessione."),
    ]);
  }

  function FilterPanel({ filters, setFilters, refresh, logout, loading }) {
    function update(key, value) {
      setFilters((current) => ({ ...current, [key]: value }));
    }
    return h("section", { className: "side-card compact" }, [
      h("p", { className: "eyebrow", key: "k" }, "Periodo dati"),
      h("label", { className: "field", key: "day" }, [
        h("span", { key: "l" }, "Giorno"),
        h("input", { key: "i", type: "date", value: filters.day, onChange: (event) => update("day", event.target.value) }),
      ]),
      h("div", { className: "two-fields", key: "range" }, [
        h("label", { className: "field", key: "start" }, [
          h("span", { key: "l" }, "Da"),
          h("input", { key: "i", type: "date", value: filters.start, onChange: (event) => update("start", event.target.value) }),
        ]),
        h("label", { className: "field", key: "end" }, [
          h("span", { key: "l" }, "A"),
          h("input", { key: "i", type: "date", value: filters.end, onChange: (event) => update("end", event.target.value) }),
        ]),
      ]),
      h("div", { className: "button-row", key: "buttons" }, [
        h(Button, { tone: "primary", onClick: refresh, disabled: loading, key: "refresh" }, loading ? "Aggiorno" : "Aggiorna"),
        h(Button, { tone: "ghost", onClick: logout, key: "logout" }, "Esci"),
      ]),
    ]);
  }

  function LoginScreen({ session, onLogin }) {
    const [username, setUsername] = useState(session.saved_username || "");
    const [password, setPassword] = useState("");
    const [saveEnv, setSaveEnv] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    async function submit(event, useSaved = false) {
      event.preventDefault();
      setBusy(true);
      setError("");
      try {
        const payload = await api("/api/session", {
          method: "POST",
          body: JSON.stringify(useSaved ? { use_saved: true } : { username, password, save_env: saveEnv }),
        });
        onLogin(payload);
      } catch (err) {
        setError(err.message);
      } finally {
        setBusy(false);
      }
    }

    return h("section", { className: "login-screen" }, [
      h("div", { className: "login-card", key: "card" }, [
        h("p", { className: "eyebrow", key: "k" }, "Accesso"),
        h("h1", { key: "t" }, "Entra nel tuo spazio studio."),
        h("p", { className: "muted", key: "d" }, "La nuova interfaccia separa voti, agenda, documenti e tutor AI in pagine vere."),
        error ? h("p", { className: "notice error", key: "e" }, error) : null,
        h("form", { className: "form-stack", onSubmit: submit, key: "form" }, [
          h("label", { className: "field", key: "u" }, [
            h("span", { key: "l" }, "Username"),
            h("input", {
              key: "i",
              value: username,
              autoComplete: "username",
              placeholder: "S1234567X",
              onChange: (event) => setUsername(event.target.value),
            }),
          ]),
          h("label", { className: "field", key: "p" }, [
            h("span", { key: "l" }, "Password"),
            h("input", {
              key: "i",
              type: "password",
              value: password,
              autoComplete: "current-password",
              placeholder: "Password",
              onChange: (event) => setPassword(event.target.value),
            }),
          ]),
          h("label", { className: "check-row", key: "s" }, [
            h("input", { type: "checkbox", checked: saveEnv, onChange: (event) => setSaveEnv(event.target.checked), key: "i" }),
            h("span", { key: "l" }, "Salva anche nel file .env"),
          ]),
          h("div", { className: "button-row", key: "b" }, [
            h(Button, { tone: "primary", type: "submit", disabled: busy, key: "login" }, busy ? "Accesso..." : "Accedi"),
            session.saved_credentials
              ? h(Button, { tone: "secondary", disabled: busy, onClick: (event) => submit(event, true), key: "saved" }, "Usa salvate")
              : null,
          ]),
        ]),
      ]),
      h("div", { className: "login-preview", key: "preview" }, [
        h(MetricCard, { label: "Voti", value: "per periodo", note: "Media generale e per materia", tone: "green", key: "m1" }),
        h(MetricCard, { label: "Agenda", value: "vicina", note: "Giorni piu importanti davanti", tone: "orange", key: "m2" }),
        h(MetricCard, { label: "AI", value: "contestuale", note: "Usa dati sincronizzati", tone: "blue", key: "m3" }),
      ]),
    ]);
  }

  function DashboardPage({ pageData, openAction }) {
    const performance = pageData?.performance || {};
    const agendaItems = uniqueItems([...sectionItems(pageData, "agenda_da_a"), ...sectionItems(pageData, "agenda"), ...sectionItems(pageData, "calendario_da_a"), ...sectionItems(pageData, "calendario")])
      .filter((item) => !item.date_iso || item.date_iso >= todayIso())
      .slice(0, 4);
    const documents = documentItems(pageData).slice(0, 4);
    const notices = sectionItems(pageData, "bacheca").slice(0, 4);
    const planDays = pageData?.plan?.days || [];
    const firstWeak = performance.risk_subjects?.[0];

    useEffect(() => {
      // Animazioni per le card della dashboard
      gsap.from(".metric-card, .panel", {
        opacity: 0,
        y: 30,
        stagger: 0.1,
        duration: 0.8,
        ease: "expo.out",
        clearProps: "all"
      });
    }, []);

    return h("div", { className: "page-grid" }, [
      h("section", { className: "hero-panel", key: "hero" }, [
        h("div", { key: "copy" }, [
          h("p", { className: "eyebrow", key: "k" }, "Focus Analysis"),
          h("h2", { key: "t" }, firstWeak ? `Potenzia ${firstWeak.subject}` : "Sincronizzazione Completa"),
          h(
            "p",
            { className: "muted", key: "b" },
            firstWeak
              ? `Media ${numberText(firstWeak.average)}: Zenith consiglia sessioni di recupero mirate nei prossimi 3 giorni.`
              : "I tuoi dati indicano un andamento ottimale in tutte le materie."
          ),
        ]),
        h("div", { className: "hero-number", key: "num" }, [
          h("span", { key: "label" }, "Average"),
          h("strong", { key: "value" }, numberText(performance.overall_average)),
        ]),
      ]),
      h("section", { className: "metric-grid", key: "metrics" }, [
        h(MetricCard, { label: "Active Average", value: performance.overall_average, note: performance.active_period_label, tone: "green", key: "avg" }),
        h(MetricCard, { label: "Yearly Average", value: performance.overall_all_periods, note: "Overall performance", tone: "blue", key: "all" }),
        h(MetricCard, { label: "Absences", value: performance.absences_count || 0, note: "Total recorded", tone: "orange", key: "abs" }),
        h(MetricCard, { label: "Active Tasks", value: pageData?.task_summary?.active || 0, note: "Zenith Planner", tone: "pink", key: "tasks" }),
      ]),
      h("section", { className: "split-grid", key: "split" }, [
        h(CompactList, { title: "Upcoming Events", items: agendaItems, empty: "No upcoming events in your agenda.", openAction, key: "agenda" }),
        h(PlanPreview, { days: planDays.slice(0, 3), key: "plan" }),
      ]),
      h("section", { className: "split-grid", key: "docs" }, [
        h(CompactList, { title: "Recent Files", items: documents, empty: "No recent documents found.", openAction, key: "documents" }),
        h(CompactList, { title: "Bulletins", items: notices, empty: "No school bulletins available.", openAction, key: "notices" }),
      ]),
    ]);
  }

  function CompactList({ title, items, empty, openAction }) {
    return h("section", { className: "panel" }, [
      h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, title), h("span", { key: "c" }, items.length)]),
      items.length
        ? h("div", { className: "list-stack", key: "list" }, items.map((item) => h(ItemRow, { item, openAction, compact: true, key: item.id || item.title })))
        : h("p", { className: "muted", key: "empty" }, empty),
    ]);
  }

  function PlanPreview({ days }) {
    return h("section", { className: "panel" }, [
      h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Planner"), h("span", { key: "c" }, `${days.length} giorni`)]),
      days.length
        ? h("div", { className: "list-stack", key: "days" },
            days.map((day) =>
              h("article", { className: "day-card", key: day.date }, [
                h("div", { key: "top" }, [h("strong", { key: "date" }, formatLongDate(day.date)), h("span", { key: "min" }, `${day.planned_minutes || 0} min`)]),
                h(
                  "p",
                  { className: "muted", key: "sessions" },
                  day.sessions?.length ? day.sessions.map((session) => `${session.title} (${session.minutes} min)`).join(", ") : "Giornata libera"
                ),
              ])
            )
          )
        : h("p", { className: "muted", key: "empty" }, "Nessun piano disponibile."),
    ]);
  }

  function VotiPage({ pageData }) {
    const performance = pageData?.performance || {};
    const allGrades = sectionItems(pageData, "voti");
    const options = periodOptions(performance, allGrades);
    const defaultPeriod = performance.active_period_key || options[0]?.key || "all";
    const [selectedPeriod, setSelectedPeriod] = useState(defaultPeriod);

    useEffect(() => {
      setSelectedPeriod(defaultPeriod);
    }, [defaultPeriod]);

    useEffect(() => {
      gsap.from(".grade-row, .panel", {
        opacity: 0,
        x: -20,
        stagger: 0.05,
        duration: 0.6,
        ease: "power2.out",
        clearProps: "all"
      });
    }, [selectedPeriod]);

    const selected = selectedPeriodData(performance, selectedPeriod);
    const grades = allGrades.filter((item) => selectedPeriod === "all" || item.period_key === selectedPeriod);
    const grouped = groupBy(grades, (item) => item.subject || "Materia");
    const subjectRows = selected.subject_averages || [];

    return h("div", { className: "page-grid" }, [
      h("section", { className: "panel grades-summary", key: "summary" }, [
        h("div", { key: "copy" }, [
          h("p", { className: "eyebrow", key: "k" }, "Selected Period"),
          h("h2", { key: "title" }, selected.label || "Period"),
          h("p", { className: "muted", key: "body" }, "Zenith tracks your performance across all subjects, highlighting trends and critical areas."),
        ]),
        h("div", { className: "grade-orb hero-number", key: "orb" }, [
          h("span", { key: "l" }, "Average"),
          h("strong", { key: "v" }, numberText(selected.overall_average)),
        ]),
      ]),
      h("section", { className: "period-tabs", key: "tabs" },
        options.map((period) =>
          h(
            "button",
            {
              className: classNames("period-tab", selectedPeriod === period.key && "is-active"),
              onClick: () => setSelectedPeriod(period.key),
              key: period.key,
              type: "button",
            },
            [h("span", { key: "l" }, period.label), h("small", { key: "c" }, `${period.count || 0} grades`)]
          )
        )
      ),
      h("section", { className: "split-grid", key: "split" }, [
        h(SubjectAverages, { rows: subjectRows, key: "avg" }),
        h(RecentGrades, { grades: grades.slice(0, 8), key: "recent" }),
      ]),
      h("section", { className: "panel", key: "details" }, [
        h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Subject Breakdown"), h("span", { key: "c" }, grades.length)]),
        grades.length
          ? h("div", { className: "subject-stack", key: "groups" },
              Object.entries(grouped).map(([subject, items]) =>
                h("article", { className: "subject-panel", key: subject }, [
                  h("div", { className: "subject-head", key: "head" }, [
                    h("h3", { key: "t" }, subject),
                    h("span", { key: "c" }, `${items.length} entries`),
                  ]),
                  h("div", { className: "grade-list", key: "items" }, items.map((item) => h(GradeRow, { grade: item, key: item.id }))),
                ])
              )
            )
          : h(EmptyState, { title: "No data found for this period", body: "Select a different period or check your connection.", key: "empty" }),
      ]),
    ]);
  }

  function SubjectAverages({ rows }) {
    return h("section", { className: "panel" }, [
      h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Medie per materia"), h("span", { key: "c" }, rows.length)]),
      rows.length
        ? h("div", { className: "average-list", key: "rows" },
            rows.map((row) =>
              h("article", { className: "average-row", key: row.subject }, [
                h("div", { key: "copy" }, [h("strong", { key: "s" }, row.subject), h("span", { key: "c" }, `${row.count} voti`)]),
                h("b", { key: "avg" }, numberText(row.average)),
              ])
            )
          )
        : h("p", { className: "muted", key: "empty" }, "Medie non disponibili."),
    ]);
  }

  function RecentGrades({ grades }) {
    return h("section", { className: "panel" }, [
      h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Ultimi voti"), h("span", { key: "c" }, grades.length)]),
      grades.length
        ? h("div", { className: "mini-grade-grid", key: "rows" }, grades.map((grade) => h(GradeRow, { grade, compact: true, key: grade.id })))
        : h("p", { className: "muted", key: "empty" }, "Nessun voto recente."),
    ]);
  }

  function GradeRow({ grade, compact = false }) {
    const makesAverage = grade.contributes_to_average !== false;
    const tone = gradeTone(grade);
    return h("article", { className: classNames("grade-row", compact && "compact", `grade-${tone}`, !makesAverage && "no-average") }, [
      h("div", { className: "grade-value", key: "value" }, grade.grade || grade.display_grade || "-"),
      h("div", { className: "grade-copy", key: "copy" }, [
        h("strong", { key: "subject" }, grade.subject || grade.title || "Materia"),
        h("span", { key: "teacher" }, grade.teacher || grade.subtitle || "Docente non indicato"),
        grade.description ? h("p", { key: "desc" }, grade.description) : null,
      ]),
      h("div", { className: "grade-meta", key: "meta" }, [
        grade.date_text ? h("span", { key: "date" }, grade.date_text) : null,
        grade.component ? h("span", { key: "component" }, grade.component) : null,
        !makesAverage ? h("span", { className: "no-average-badge", key: "avg" }, "non fa media") : null,
      ]),
    ]);
  }

  function AgendaPage({ pageData, openAction, filters, setFilters }) {
    const [viewMode, setViewMode] = useState("week");
    const [cursor, setCursor] = useState(todayIso());

    useEffect(() => {
      gsap.from(".time-card, .timeline-day", {
        opacity: 0,
        y: 20,
        stagger: 0.03,
        duration: 0.5,
        ease: "power2.out",
        clearProps: "all"
      });
    }, [cursor, viewMode]);

    useEffect(() => {
      if (filters.day && filters.day !== cursor) {
        setCursor(filters.day);
      }
    }, [filters.day]);
    const items = uniqueItems([
      ...sectionItems(pageData, "agenda_da_a"),
      ...sectionItems(pageData, "agenda"),
      ...sectionItems(pageData, "calendario_da_a"),
      ...sectionItems(pageData, "calendario"),
    ]);
    const groups = groupBy(items, (item) => item.date_iso || "senza-data");
    const firstDay = viewMode === "month" ? toIso(monthStart(cursor)) : cursor;
    const days = viewMode === "month" ? dateRange(firstDay, monthEnd(cursor).getDate()) : dateRange(firstDay, 10);
    const visibleCount = days.reduce((count, day) => count + (groups[day]?.length || 0), 0);

    function applyWindow(nextCursor, nextMode = viewMode) {
      const normalized = toIso(nextCursor);
      const start = nextMode === "month" ? toIso(monthStart(normalized)) : normalized;
      const end = nextMode === "month" ? toIso(monthEnd(normalized)) : toIso(addDays(normalized, 13));
      setCursor(normalized);
      setFilters((current) => ({ ...current, day: normalized, start, end }));
    }

    function switchMode(nextMode) {
      setViewMode(nextMode);
      applyWindow(cursor, nextMode);
    }

    function move(direction) {
      applyWindow(viewMode === "month" ? addMonths(cursor, direction) : addDays(cursor, direction * 7));
    }

    return h("div", { className: "page-grid" }, [
      h("section", { className: "panel agenda-toolbar", key: "toolbar" }, [
        h("div", { key: "copy" }, [
          h("p", { className: "eyebrow", key: "k" }, "Calendar View"),
          h("h2", { key: "title" }, viewMode === "month" ? formatLongDate(firstDay) : `${formatDate(firstDay)} - ${formatDate(days[days.length - 1])}`),
          h("p", { className: "muted", key: "body" }, `Zenith analysis from ${formatDate(filters.start)} to ${formatDate(filters.end)}.`),
        ]),
        h("div", { className: "calendar-actions", key: "actions" }, [
          h(Button, { tone: "ghost", onClick: () => move(-1), key: "prev" }, viewMode === "month" ? "Previous Month" : "Previous Week"),
          h(Button, { tone: "primary", onClick: () => applyWindow(todayIso()), key: "today" }, "Today"),
          h(Button, { tone: "ghost", onClick: () => move(1), key: "next" }, viewMode === "month" ? "Next Month" : "Next Week"),
          h("div", { className: "segmented", key: "segmented" }, [
            h("button", { type: "button", className: classNames("button", viewMode === "week" && "is-active"), onClick: () => switchMode("week"), key: "week" }, "Week"),
            h("button", { type: "button", className: classNames("button", viewMode === "month" && "is-active"), onClick: () => switchMode("month"), key: "month" }, "Month"),
          ]),
        ]),
      ]),
      h("section", { className: "panel agenda-timeline-panel", key: "strip" }, [
        h("div", { className: "section-head", key: "head" }, [
          h("h2", { key: "t" }, "Zenith Timeline"),
          h("span", { key: "c" }, `${visibleCount} events`),
        ]),
        h("div", { className: "time-rail", key: "grid" },
          days.map((day) => {
            const entries = groups[day] || [];
            const stamp = shortDay(day);
            return h("article", { className: classNames("time-card", day === todayIso() && "is-today"), key: day }, [
              h("div", { className: "time-stamp", key: "stamp" }, [
                h("strong", { key: "d" }, stamp.day),
                h("span", { key: "m" }, stamp.month),
              ]),
              h("h3", { key: "label" }, formatDate(day)),
              entries.length
                ? h("div", { className: "time-items", key: "items" },
                    entries.slice(0, 5).map((item) =>
                      h("button", { type: "button", onClick: () => openAction(item.actions?.[0]?.href, item.title), key: item.id || item.title }, item.title || "Event")
                    )
                  )
                : h("p", { className: "muted", key: "empty" }, "Free day"),
            ]);
          })
        ),
      ]),
      h("section", { className: "panel", key: "timeline" }, [
        h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Detailed Schedule"), h("span", { key: "c" }, "day by day")]),
        h("div", { className: "timeline", key: "list" },
          days.map((day) =>
            h("section", { className: "timeline-day", key: day }, [
              h("h3", { key: "date" }, formatLongDate(day)),
              h("div", { className: "list-stack", key: "items" },
                (groups[day] || []).length
                  ? groups[day].map((item) => h(ItemRow, { item, openAction, key: item.id || item.title }))
                  : [h("p", { className: "muted empty-day", key: "empty" }, "No scheduled activities for this day.")]
              ),
            ])
          )
        ),
      ]),
    ]);
  }

  function DocumentsPage({ pageData, openAction }) {
    const docs = documentItems(pageData);
    const didactics = sectionItems(pageData, "didattica");
    return h("div", { className: "page-grid" }, [
      h(FileSection, { title: "Documenti", items: docs, openAction, empty: "Nessun documento trovato.", key: "docs" }),
      h(FileSection, { title: "Materiali didattici", items: didactics, openAction, empty: "Nessun materiale didattico trovato.", key: "did" }),
    ]);
  }

  function FileSection({ title, items, openAction, empty }) {
    return h("section", { className: "panel" }, [
      h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, title), h("span", { key: "c" }, items.length)]),
      items.length
        ? h("div", { className: "file-grid", key: "grid" }, items.map((item) => h(FileCard, { item, openAction, key: item.id || item.title })))
        : h(EmptyState, { title: "Niente da mostrare", body: empty, key: "empty" }),
    ]);
  }

  function FileCard({ item, openAction }) {
    const actions = item.actions || [];
    return h("article", { className: "file-card" }, [
      h("div", { className: "file-icon", key: "icon" }, "FILE"),
      h("div", { className: "file-copy", key: "copy" }, [
        h("strong", { key: "title" }, item.title || "Documento"),
        item.subtitle || item.group ? h("span", { key: "sub" }, item.subtitle || item.group) : null,
        item.body ? h("p", { key: "body" }, item.body) : null,
      ]),
      h("div", { className: "action-row", key: "actions" },
        actions.length
          ? actions.slice(0, 3).map((action) => h(ActionButton, { action, openAction, key: `${action.label}-${action.href}` }))
          : [h("span", { className: "muted", key: "none" }, "Nessuna azione")]
      ),
    ]);
  }

  function BachecaPage({ pageData, openAction }) {
    const items = sectionItems(pageData, "bacheca");
    return h("section", { className: "panel" }, [
      h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Circolari"), h("span", { key: "c" }, items.length)]),
      items.length
        ? h("div", { className: "notice-grid", key: "grid" }, items.map((item) => h(ItemRow, { item, openAction, key: item.id || item.title })))
        : h(EmptyState, { title: "Nessuna circolare", body: "La bacheca non ha restituito comunicazioni nel periodo selezionato.", key: "empty" }),
    ]);
  }

  function PlannerPage({ pageData }) {
    const days = pageData?.plan?.days || [];
    const suggestions = pageData?.suggestions || [];
    return h("div", { className: "page-grid" }, [
      h("section", { className: "panel" }, [
        h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Timeline studio"), h("span", { key: "c" }, `${pageData?.plan?.daily_minutes || 0} min/giorno`)]),
        h("div", { className: "time-rail", key: "days" },
          days.map((day) => {
            const stamp = shortDay(day.date);
            return h("article", { className: "time-card planner-time-card", key: day.date }, [
              h("div", { className: "time-stamp", key: "stamp" }, [h("strong", { key: "d" }, stamp.day), h("span", { key: "m" }, stamp.month)]),
              h("h3", { key: "date" }, formatDate(day.date)),
              h("span", { className: "status-badge", key: "minutes" }, `${day.planned_minutes || 0} min`),
              h("div", { className: "time-items", key: "sessions" },
                day.sessions?.length
                  ? day.sessions.map((session, index) =>
                      h("p", { className: "session-line", key: `${session.title}-${index}` }, `${session.title} - ${session.minutes} min`)
                    )
                  : [h("p", { className: "muted", key: "empty" }, "Libero")]
              ),
            ]);
          })
        ),
      ]),
      h("section", { className: "panel" }, [
        h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Suggerimenti"), h("span", { key: "c" }, suggestions.length)]),
        h("div", { className: "list-stack", key: "list" },
          suggestions.map((item) =>
            h("article", { className: `suggestion tone-${item.tone || "neutral"}`, key: item.title }, [
              h("strong", { key: "title" }, item.title),
              h("p", { key: "body" }, item.body),
            ])
          )
        ),
      ]),
    ]);
  }

  function AttivitaPage({ pageData }) {
    const tasks = pageData?.tasks || [];
    return h("section", { className: "panel" }, [
      h("div", { className: "section-head", key: "head" }, [h("h2", { key: "t" }, "Attivita personali"), h("span", { key: "c" }, tasks.length)]),
      tasks.length
        ? h("div", { className: "list-stack", key: "list" },
            tasks.map((task) =>
              h("article", { className: "task-row", key: task.id }, [
                h("div", { key: "copy" }, [h("strong", { key: "t" }, task.title), h("span", { key: "s" }, `${task.subject} - ${task.category}`)]),
                h("span", { className: "status-badge", key: "date" }, task.due_date),
              ])
            )
          )
        : h(EmptyState, { title: "Nessuna attivita manuale", body: "Puoi comunque usare il planner generato da agenda, voti e materiali.", key: "empty" }),
    ]);
  }

  function TutorPage({ pageData, filters, setPageData }) {
    const [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const chat = pageData?.chat || {};
    const messages = chat.messages || [];
    const threads = chat.threads || [];

    async function loadThread(threadId) {
      setBusy(true);
      setError("");
      try {
        const query = new URLSearchParams({ ...filters, thread_id: String(threadId) });
        const payload = await api(`/api/chat?${query.toString()}`);
        setPageData((current) => ({ ...current, chat: payload.chat }));
      } catch (err) {
        setError(err.message);
      } finally {
        setBusy(false);
      }
    }

    async function newThread() {
      setBusy(true);
      setError("");
      try {
        const created = await api("/api/chat/threads", {
          method: "POST",
          body: JSON.stringify({ title: "Nuova chat" }),
        });
        await loadThread(created.thread.id);
      } catch (err) {
        setError(err.message);
      } finally {
        setBusy(false);
      }
    }

    async function send(event) {
      event.preventDefault();
      const clean = message.trim();
      if (!clean) {
        return;
      }
      const optimisticUser = {
        id: `temp-user-${Date.now()}`,
        role: "user",
        content: clean,
        created_at: new Date().toISOString(),
      };
      const thinking = {
        id: `temp-thinking-${Date.now()}`,
        role: "assistant",
        content: "Sto ragionando sui tuoi dati...",
        created_at: new Date().toISOString(),
        thinking: true,
      };
      setBusy(true);
      setError("");
      setMessage("");
      setPageData((current) => ({
        ...current,
        chat: {
          ...(current?.chat || chat),
          messages: [...((current?.chat || chat).messages || []), optimisticUser, thinking],
        },
      }));
      try {
        const payload = await api("/api/chat", {
          method: "POST",
          body: JSON.stringify({ message: clean, thread_id: chat.thread_id, ...filters }),
        });
        setPageData((current) => ({ ...current, chat: payload.chat }));
      } catch (err) {
        setError(err.message);
      } finally {
        setBusy(false);
      }
    }

    return h("div", { className: "chat-layout" }, [
      h("section", { className: "panel chat-panel", key: "chat" }, [
        h("div", { className: "section-head", key: "head" }, [
          h("h2", { key: "t" }, chat.thread?.title || (chat.provider?.enabled ? `Tutor AI (${chat.provider.label})` : "Tutor locale")),
          h("span", { key: "c" }, `${messages.length} messaggi`),
        ]),
        h("div", { className: "chat-messages", key: "messages" },
          messages.map((item) =>
            h("article", { className: classNames("chat-bubble", item.role === "user" && "is-user", item.thinking && "is-thinking"), key: item.id || `${item.role}-${item.created_at}` }, [
              h("strong", { key: "role" }, item.role === "user" ? "Tu" : "Tutor AI"),
              h("p", { key: "content" }, item.content),
            ])
          )
        ),
        error ? h("p", { className: "notice error", key: "error" }, error) : null,
        h("form", { className: "chat-form", onSubmit: send, key: "form" }, [
          h("textarea", {
            value: message,
            rows: 4,
            placeholder: "Esempio: analizza i miei voti del periodo e dimmi cosa migliorare questa settimana.",
            onChange: (event) => setMessage(event.target.value),
            key: "input",
          }),
          h(Button, { tone: "primary", type: "submit", disabled: busy, key: "button" }, busy ? "Invio..." : "Invia al tutor"),
        ]),
      ]),
      h("aside", { className: "panel context-panel", key: "context" }, [
        h("div", { className: "chat-side-head", key: "threads-head" }, [
          h("h2", { key: "t" }, "Le tue chat"),
          h(Button, { tone: "secondary", onClick: newThread, disabled: busy, key: "new" }, "Nuova"),
        ]),
        h("div", { className: "thread-list", key: "threads" },
          threads.length
            ? threads.map((thread) =>
                h(
                  "button",
                  {
                    type: "button",
                    className: classNames("thread-button", thread.id === chat.thread_id && "is-active"),
                    onClick: () => loadThread(thread.id),
                    disabled: busy,
                    key: thread.id,
                  },
                  [
                    h("strong", { key: "title" }, thread.title || "Chat"),
                    h("span", { key: "meta" }, `${thread.message_count || 0} messaggi`),
                  ]
                )
              )
            : [h("p", { className: "muted", key: "empty" }, "Nessuna chat salvata.")]
        ),
        h("h2", { key: "context-title" }, "Contesto usato"),
        h("div", { className: "context-grid", key: "cards" },
          (chat.context_cards || []).map((card) =>
            h(MetricCard, { label: card.label, value: card.value, note: card.note, tone: "blue", key: card.label })
          )
        ),
        chat.provider?.hint ? h("p", { className: "notice", key: "hint" }, chat.provider.hint) : null,
      ]),
    ]);
  }

  function ProfiloPage({ pageData }) {
    const profile = pageData?.profile || {};
    const overview = pageData?.overview || {};
    return h("div", { className: "page-grid" }, [
      h("section", { className: "panel profile-panel", key: "profile" }, [
        h("p", { className: "eyebrow", key: "k" }, "Studente"),
        h("h2", { key: "name" }, overview.display_name || profile.display_name || "Studente"),
        h("p", { className: "muted", key: "id" }, `ID risolto: ${overview.resolved_student_id || "n/d"}`),
        h("div", { className: "record-grid", key: "records" }, [
          h(MetricCard, { label: "Obiettivo", value: profile.study_goal || "non impostato", note: "Usato dal tutor", tone: "blue", key: "goal" }),
          h(MetricCard, { label: "Modalita", value: profile.learning_mode || "standard", note: "Impatta durata sessioni", tone: "green", key: "mode" }),
          h(MetricCard, { label: "Studio/giorno", value: `${profile.daily_study_minutes || 120} min`, note: "Planner", tone: "orange", key: "daily" }),
        ]),
      ]),
    ]);
  }

  function ItemRow({ item, openAction, compact = false }) {
    const actions = item.actions || [];
    return h("article", { className: classNames("item-row", compact && "compact") }, [
      h("div", { className: "item-main", key: "main" }, [
        h("strong", { key: "title" }, item.title || "Elemento"),
        item.subtitle ? h("span", { key: "sub" }, item.subtitle) : null,
        item.body ? h("p", { key: "body" }, item.body) : null,
        item.badges?.length
          ? h("div", { className: "badge-row", key: "badges" }, item.badges.slice(0, 3).map((badge) => h("span", { className: "status-badge", key: badge }, badge)))
          : null,
      ]),
      actions.length
        ? h("div", { className: "action-row", key: "actions" },
            actions.slice(0, 3).map((action) => h(ActionButton, { action, openAction, key: `${action.label}-${action.href}` }))
          )
        : null,
    ]);
  }

  function ActionButton({ action, openAction }) {
    return h(
      "button",
      {
        type: "button",
        className: "action-button",
        onClick: () => openAction(action.href, action.label),
      },
      action.label || "Apri"
    );
  }

  function DetailModal({ detail, close, openAction }) {
    if (!detail) {
      return null;
    }
    const actions = detail.actions || [];
    return h("div", { className: "modal-layer" }, [
      h("button", { className: "modal-backdrop", onClick: close, "aria-label": "Chiudi", key: "backdrop" }),
      h("section", { className: "detail-panel", key: "panel" }, [
        h("div", { className: "detail-head", key: "head" }, [
          h("div", { key: "copy" }, [
            h("p", { className: "eyebrow", key: "k" }, "Dettaglio"),
            h("h2", { key: "t" }, detail.title || "Elemento"),
            detail.subtitle ? h("p", { className: "muted", key: "s" }, detail.subtitle) : null,
          ]),
          h(Button, { tone: "ghost", onClick: close, key: "close" }, "Chiudi"),
        ]),
        detail.preview
          ? h("div", { className: "preview-box", key: "preview" }, [
              h("div", { className: "preview-head", key: "ph" }, [
                h("strong", { key: "l" }, detail.preview.label || "Anteprima"),
                detail.preview.raw_url
                  ? h("a", { href: detail.preview.raw_url, target: "_blank", rel: "noopener", key: "raw" }, "Apri originale")
                  : null,
              ]),
              h("iframe", { src: detail.preview.url, title: detail.preview.label || "Anteprima", key: "frame" }),
            ])
          : null,
        actions.length
          ? h("div", { className: "action-row", key: "actions" },
              actions.slice(0, 6).map((action) => h(ActionButton, { action, openAction, key: `${action.label}-${action.href}` }))
            )
          : null,
        detail.body ? h("article", { className: "detail-body", key: "body" }, detail.body) : null,
        detail.meta?.length
          ? h("div", { className: "record-grid", key: "meta" },
              detail.meta.map((item) => h(MetricCard, { label: item.label, value: item.value, tone: "blue", key: item.label }))
            )
          : null,
      ]),
    ]);
  }

  function CurrentPage({ pageId, pageData, openAction, filters, setFilters, setPageData }) {
    if (!pageData) {
      return h(EmptyState, { title: "Carico i dati", body: "Sto sincronizzando solo la pagina richiesta.", key: "loading" });
    }
    if (pageId === "dashboard") {
      return h(DashboardPage, { pageData, openAction });
    }
    if (pageId === "voti") {
      return h(VotiPage, { pageData });
    }
    if (pageId === "agenda") {
      return h(AgendaPage, { pageData, openAction, filters, setFilters });
    }
    if (pageId === "documenti") {
      return h(DocumentsPage, { pageData, openAction });
    }
    if (pageId === "bacheca") {
      return h(BachecaPage, { pageData, openAction });
    }
    if (pageId === "planner") {
      return h(PlannerPage, { pageData });
    }
    if (pageId === "attivita") {
      return h(AttivitaPage, { pageData });
    }
    if (pageId === "tutor") {
      return h(TutorPage, { pageData, filters, setPageData });
    }
    if (pageId === "profilo") {
      return h(ProfiloPage, { pageData });
    }
    return h(DashboardPage, { pageData, openAction });
  }

  function App() {
    const [pageId, setPageId] = useState(routeToPage);
    const [session, setSession] = useState({ booting: true, authenticated: false, onboarded: false });
    const [filters, setFilters] = useState(initialFilters);
    const [pageData, setPageData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [detail, setDetail] = useState(null);
    const [refreshTick, setRefreshTick] = useState(0);

    const queryString = useMemo(() => {
      const query = new URLSearchParams(filters);
      return query.toString();
    }, [filters]);

    useEffect(() => {
      // Global Cursor Logic
      if (window.gsap) {
        const cursor = document.getElementById("custom-cursor");
        const onMouseMove = (e) => {
          gsap.to(cursor, { 
            x: e.clientX, 
            y: e.clientY, 
            duration: 0.2,
            ease: "power2.out"
          });
        };
        window.addEventListener("mousemove", onMouseMove);

        const onMouseEnter = () => gsap.to(cursor, { scale: 2, background: "rgba(10, 228, 72, 0.3)", duration: 0.3 });
        const onMouseLeave = () => gsap.to(cursor, { scale: 1, background: "rgba(255, 255, 255, 0.1)", duration: 0.3 });

        const updateInteractive = () => {
          const interactive = document.querySelectorAll("button, a, .cta-huge, .highlight, input, select, textarea");
          interactive.forEach(el => {
            el.addEventListener("mouseenter", onMouseEnter);
            el.addEventListener("mouseleave", onMouseLeave);
          });
        };

        updateInteractive();
        const observer = new MutationObserver(updateInteractive);
        observer.observe(document.body, { childList: true, subtree: true });

        return () => {
          window.removeEventListener("mousemove", onMouseMove);
          observer.disconnect();
        };
      }
    }, []);

    useEffect(() => {
      let alive = true;
      api("/api/session")
        .then((payload) => {
          if (alive) {
            setSession({ booting: false, ...payload });
          }
        })
        .catch((err) => {
          if (alive) {
            setSession({ booting: false, authenticated: false, onboarded: false });
            setError(err.message);
          }
        });
      const onPop = () => setPageId(routeToPage());
      window.addEventListener("popstate", onPop);
      return () => {
        alive = false;
        window.removeEventListener("popstate", onPop);
      };
    }, []);

    useEffect(() => {
      if (!session.authenticated || pageId === "home") {
        return;
      }
      let alive = true;
      setLoading(true);
      setError("");
      api(`/api/page/${pageId}?${queryString}`)
        .then((payload) => {
          if (alive) {
            setPageData(payload);
          }
        })
        .catch((err) => {
          if (alive) {
            setError(err.message);
            setPageData(null);
          }
        })
        .finally(() => {
          if (alive) {
            setLoading(false);
          }
        });
      return () => {
        alive = false;
      };
    }, [session.authenticated, pageId, queryString, refreshTick]);

    function navigate(event, id) {
      if (event) event.preventDefault();
      if (id === pageId) {
        return;
      }
      window.history.pushState({}, "", `/${id}`);
      setPageId(id);
    }

    async function logout() {
      await api("/api/session", { method: "DELETE" }).catch(() => null);
      setSession({ booting: false, authenticated: false, onboarded: false });
      setPageData(null);
      navigate(null, "home");
    }

    async function openAction(href, label = "Dettaglio") {
      if (!href) {
        return;
      }
      if (href.includes("download=1") || href.startsWith("http")) {
        window.open(href, "_blank", "noopener");
        return;
      }
      if (href.startsWith("/api/details/")) {
        try {
          const payload = await api(href);
          setDetail(payload);
        } catch (err) {
          setDetail({ title: "Errore", body: err.message, actions: [] });
        }
        return;
      }
      if (href.startsWith("/api/preview/") || href.startsWith("/api/download/")) {
        setDetail({
          title: label,
          subtitle: "Anteprima interna",
          preview: { label, url: href, raw_url: href },
          actions: [{ label: "Apri in nuova scheda", href }],
        });
        return;
      }
      window.open(href, "_blank", "noopener");
    }

    if (session.booting) {
      return h("main", { className: "boot-screen" }, [h("div", { className: "loader", key: "l" }), h("p", { key: "p" }, "Avvio Nexus...")]);
    }

    // Se siamo in Home Page, mostriamo la Landing indipendentemente dalla sessione
    if (pageId === "home") {
      return h(LandingPage, { onStart: () => navigate(null, "dashboard") });
    }

    // Se non abbiamo completato l'onboarding (email/nome/scuola)
    if (!session.onboarded) {
      return h(OnboardingPage, { onComplete: (payload) => setSession({ booting: false, ...payload }) });
    }

    // Se siamo onboarded ma non abbiamo ancora fatto il login CV
    if (!session.authenticated) {
      return h(OnboardingPage, { onComplete: (payload) => setSession({ booting: false, ...payload }) });
    }

    return h(Layout, { pageId, navigate, session, filters, setFilters, refresh: () => setRefreshTick((value) => value + 1), logout, loading }, [
      h(PageHeader, { pageId, pageData, loading, key: "header" }),
      error ? h("p", { className: "notice error", key: "error" }, error) : null,
      loading && !pageData ? h("div", { className: "skeleton-grid", key: "skeleton" }, [h("div", { key: "a" }), h("div", { key: "b" }), h("div", { key: "c" })]) : null,
      h(CurrentPage, { pageId, pageData, openAction, filters, setFilters, setPageData, key: pageId }),
      h(DetailModal, { detail, close: () => setDetail(null), openAction, key: "detail" }),
    ]);
  }

  ReactDOM.createRoot(rootElement).render(h(App));
})();
