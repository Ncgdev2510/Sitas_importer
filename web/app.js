/**
 * SITAS Cestoball Dashboard - Frontend Logic
 * Carga local instantánea, 0 tokens, filtros dinámicos y estadísticas.
 * Separación clara entre Torneos Metropolitanos y Competencias Nacionales.
 */

// Application State
const state = {
  data: null,
  targetClub: 'SITAS',
  currentScope: 'METRO', // 'METRO' | 'NACIONAL'
  selectedSeason: '2026',
  selectedCategory: 'PRIMERA A',
  selectedEdition: 'CLAUSURA',
  searchQuery: '',
  onlySitasMatches: true,
  selectedTournamentId: null,
  selectedPhaseIndex: 0,
  activeView: 'standings', // 'standings' | 'matches'
  theme: localStorage.getItem('sitas_theme') || 'dark',
};

// DOM Elements
const DOM = {
  themeToggle: document.getElementById('theme-toggle'),
  themeIcon: document.getElementById('theme-icon'),
  seasonSelect: document.getElementById('season-select'),
  scopeTabMetro: document.getElementById('scope-tab-metro'),
  scopeTabNacional: document.getElementById('scope-tab-nacional'),
  categoryPills: document.getElementById('category-pills'),
  searchInput: document.getElementById('search-input'),
  editionFilters: document.getElementById('edition-filters'),
  onlySitasToggle: document.getElementById('only-sitas-matches'),
  tournamentNavList: document.getElementById('tournament-nav-list'),
  tournamentCount: document.getElementById('tournament-count'),
  emptyState: document.getElementById('empty-state'),
  dashboardContent: document.getElementById('dashboard-content'),

  // KPIs
  kpiTournaments: document.getElementById('kpi-tournaments'),
  kpiPlayed: document.getElementById('kpi-played'),
  kpiWon: document.getElementById('kpi-won'),
  kpiLost: document.getElementById('kpi-lost'),
  kpiWinrate: document.getElementById('kpi-winrate'),
  kpiPoints: document.getElementById('kpi-points'),

  // Tournament Banner
  tName: document.getElementById('t-name'),
  tManager: document.getElementById('t-manager'),
  tSeasonTag: document.getElementById('t-season-tag'),
  tCategoryTag: document.getElementById('t-category-tag'),
  tEditionTag: document.getElementById('t-edition-tag'),
  tStatusTag: document.getElementById('t-status-tag'),
  sitasPosNum: document.getElementById('sitas-pos-num'),

  // Phase & Views
  phasesTabs: document.getElementById('phases-tabs'),
  viewTabStandings: document.getElementById('view-tab-standings'),
  viewTabBracket: document.getElementById('view-tab-bracket'),
  viewTabMatches: document.getElementById('view-tab-matches'),
  matchesTabCount: document.getElementById('matches-tab-count'),
  standingsContainer: document.getElementById('standings-container'),
  bracketContainer: document.getElementById('bracket-container'),
  matchesContainer: document.getElementById('matches-container'),
  standingsPhaseName: document.getElementById('standings-phase-name'),
  bracketPhaseName: document.getElementById('bracket-phase-name'),
  matchesPhaseName: document.getElementById('matches-phase-name'),
  standingsTbody: document.getElementById('standings-tbody'),
  bracketTreeViewer: document.getElementById('bracket-tree-viewer'),
  matchesList: document.getElementById('matches-list'),

  // Modal
  h2hModal: document.getElementById('h2h-modal'),
  modalClose: document.getElementById('modal-close'),
  modalRivalName: document.getElementById('modal-rival-name'),
  modalBodyContent: document.getElementById('modal-body-content'),
};

// Initialize Application
async function init() {
  applyTheme(state.theme);
  setupEventListeners();

  try {
    const res = await fetch('data.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
    state.targetClub = state.data.target_club || 'SITAS';

    populateSeasons();
    populateCategories();
    updateKPIs();
    renderTournamentsList();
  } catch (err) {
    console.error('Error al cargar datos:', err);
    try {
      const fallbackRes = await fetch('../sitas_data.json');
      const fallbackData = await fallbackRes.json();
      state.data = normalizeRawData(fallbackData);
      populateSeasons();
      populateCategories();
      updateKPIs();
      renderTournamentsList();
    } catch (fallbackErr) {
      showError('No se pudo cargar data.json. Asegúrate de generar los datos primero.');
    }
  }

  // Cargar módulos dinámicos (Próxima fecha y Noticias)
  loadUpcomingSchedule();
  loadNewsFeed();
  setupScrollSpy();

  if (window.lucide) {
    window.lucide.createIcons();
  }
}

// Club Logo Helper & Team Badge
function getClubLogoUrl(clubName) {
  if (!clubName) return null;
  const norm = clubName.toUpperCase();
  if (norm.includes('SITAS')) {
    return 'assets/clubs/sitas.png';
  }
  const slug = clubName.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, '');
  return `assets/clubs/${slug}.png`;
}

function renderTeamBadge(clubName) {
  const logoUrl = getClubLogoUrl(clubName);
  if (!logoUrl) return '';
  return `<img src="${logoUrl}" class="team-crest-sm" alt="" onerror="this.style.display='none'">`;
}

// Check if a tournament is National (Liga Nacional or Argentino)
function isNationalTournament(t) {
  const name = (t.name || '').toUpperCase();
  const cat = (t.category || '').toUpperCase();
  return (
    name.includes('LIGA NACIONAL') ||
    name.includes('ARGENTINO') ||
    cat.includes('LIGA NACIONAL') ||
    cat.includes('ARGENTINO')
  );
}

// Convert raw sitas_data.json if loaded as fallback
function normalizeRawData(raw) {
  const seasons = new Set();
  const categories = new Set();
  const tournaments = raw.tournaments || [];

  tournaments.forEach((t) => {
    const meta = t.tournament || {};
    if (meta.season) seasons.add(meta.season);
    if (meta.category) categories.add(meta.category);
  });

  return {
    target_club: raw.club || 'SITAS',
    seasons: Array.from(seasons),
    categories: Array.from(categories),
    tournaments: tournaments.map((t, idx) => ({
      id: idx + 1,
      clupik_id: t.tournament?.tournament_id,
      name: `${t.tournament?.season || ''} | ${t.tournament?.category || ''} | ${t.tournament?.edition || ''}`,
      season: t.tournament?.season || '2026',
      category: t.tournament?.category || '',
      edition: t.tournament?.edition || '',
      status: t.tournament?.status || 'Finalizada',
      phases: (t.phases || []).map((p) => ({
        id: p.phase?.phase_id,
        name: p.phase?.name || 'Fase',
        is_active: p.phase?.is_active || false,
        is_playoff: p.is_playoff || false,
        bracket: p.bracket || null,
        standings: (p.standings || []).map((s) => ({
          ...s,
          club_name: s.club?.name || '',
        })),
        matches: (p.matches || []).map((m) => ({
          ...m,
          home_club_name: m.home_club?.name || '',
          away_club_name: m.away_club?.name || '',
        })),
      })),
    })),
  };
}

// Populate Seasons
function populateSeasons() {
  const seasons = state.data?.seasons || ['2026'];
  DOM.seasonSelect.innerHTML = seasons
    .map((s) => `<option value="${s}" ${s === state.selectedSeason ? 'selected' : ''}>Temporada ${s}</option>`)
    .join('');
}

// Populate Categories in 2 Rows (Grid layout without horizontal scroll)
function populateCategories() {
  if (state.currentScope === 'METRO') {
    if (DOM.editionFilters) DOM.editionFilters.style.display = 'flex';

    // Fila 1: Adultas / Mayores (5 categorías)
    const row1 = ['PRIMERA A', 'PRIMERA B', 'PRIMERA MASCULINO', 'SUB 20', 'MAXI 30'];
    // Fila 2: Formativas / Juveniles (6 categorías)
    const row2 = ['SUB 17', 'SUB 17 FLEX', 'SUB 14', 'SUB 14 FLEX', 'SUB 12', 'SUB 10'];

    if (![...row1, ...row2].includes(state.selectedCategory)) {
      state.selectedCategory = 'PRIMERA A';
    }

    const renderPill = (cat) => `
      <button class="pill ${state.selectedCategory === cat ? 'active' : ''}" data-category="${cat}" role="tab" aria-selected="${state.selectedCategory === cat}">
        ${cat}
      </button>
    `;

    DOM.categoryPills.innerHTML = `
      <div class="category-grid-row category-row-1">
        ${row1.map(renderPill).join('')}
      </div>
      <div class="category-grid-row category-row-2">
        ${row2.map(renderPill).join('')}
      </div>
    `;

    renderEditionFilters();
  } else {
    // Competencias Nacionales
    if (DOM.editionFilters) DOM.editionFilters.style.display = 'none';

    const ligas = [
      { id: 'LIGA NACIONAL MAYORES FEMENINA', label: 'Liga Nac. Mayores Fem', icon: 'trophy' },
      { id: 'LIGA NACIONAL PRIMERA MASCULINO', label: 'Liga Nac. Masc', icon: 'trophy' },
      { id: 'LIGA NACIONAL SUB 17', label: 'Liga Nac. Sub 17', icon: 'trophy' },
      { id: 'LIGA NACIONAL SUB 14', label: 'Liga Nac. Sub 14', icon: 'trophy' },
    ];

    const argentinos = [
      { id: 'ARGENTINO MAYORES FEMENINO', label: 'Argentino Mayores Fem', icon: 'flag' },
      { id: 'ARGENTINO MAYORES MASCULINO', label: 'Argentino Mayores Masc', icon: 'flag' },
      { id: 'ARGENTINO SUB 17', label: 'Argentino Sub 17', icon: 'flag' },
      { id: 'ARGENTINO SUB 14', label: 'Argentino Sub 14', icon: 'flag' },
    ];

    const allNacIds = [...ligas, ...argentinos].map((x) => x.id);
    if (!allNacIds.includes(state.selectedCategory)) {
      state.selectedCategory = 'LIGA NACIONAL MAYORES FEMENINA';
    }

    const renderNacPill = (item) => `
      <button class="pill ${state.selectedCategory === item.id ? 'active' : ''}" data-category="${item.id}" role="tab" aria-selected="${state.selectedCategory === item.id}">
        <i data-lucide="${item.icon}"></i> ${item.label}
      </button>
    `;

    DOM.categoryPills.innerHTML = `
      <div class="category-grid-row category-row-1" title="Ligas Nacionales de Clubes">
        ${ligas.map(renderNacPill).join('')}
      </div>
      <div class="category-grid-row category-row-2" title="Campeonatos Argentinos de Selecciones">
        ${argentinos.map(renderNacPill).join('')}
      </div>
    `;
  }

  if (window.lucide) window.lucide.createIcons();
  resolveActiveTournament();
}

// Dynamic Edition Filters according to available editions for current category
function renderEditionFilters() {
  if (!DOM.editionFilters || state.currentScope !== 'METRO') return;

  const tournaments = (state.data?.tournaments || []).filter(
    (t) =>
      !isNationalTournament(t) &&
      t.category === state.selectedCategory &&
      (!state.selectedSeason || t.season === state.selectedSeason)
  );

  const availableEditions = [];
  const standardOrder = ['APERTURA', 'CLASIFICATORIO', 'CLAUSURA'];

  standardOrder.forEach((edKey) => {
    const hasEd = tournaments.some((t) => {
      const ed = (t.edition || '').toUpperCase();
      const nm = (t.name || '').toUpperCase();
      return ed.includes(edKey) || nm.includes(edKey);
    });
    if (hasEd) availableEditions.push(edKey);
  });

  if (availableEditions.length === 0) {
    tournaments.forEach((t) => {
      const ed = (t.edition || '').toUpperCase().trim();
      if (ed && !availableEditions.includes(ed)) availableEditions.push(ed);
    });
  }

  // Preserve selected edition or default to CLAUSURA
  if (!availableEditions.includes(state.selectedEdition)) {
    state.selectedEdition = availableEditions.includes('CLAUSURA')
      ? 'CLAUSURA'
      : (availableEditions[availableEditions.length - 1] || 'CLAUSURA');
  }

  DOM.editionFilters.innerHTML = availableEditions
    .map((ed) => {
      const label = ed.charAt(0) + ed.slice(1).toLowerCase();
      const isActive = state.selectedEdition === ed;
      return `
        <button class="filter-btn ${isActive ? 'active' : ''}" data-edition="${ed}">
          ${label}
        </button>
      `;
    })
    .join('');
}

// Resolve and auto-select tournament (1 Category + 1 Edition = 1 Exact Tournament)
function resolveActiveTournament() {
  if (!state.data?.tournaments) return;

  let tournament = null;

  if (state.currentScope === 'METRO') {
    tournament = state.data.tournaments.find((t) => {
      if (isNationalTournament(t)) return false;
      const matchSeason = !state.selectedSeason || t.season === state.selectedSeason;
      const matchCat = t.category === state.selectedCategory;
      const ed = (t.edition || '').toUpperCase();
      const nm = (t.name || '').toUpperCase();
      const matchEd = ed.includes(state.selectedEdition) || nm.includes(state.selectedEdition);
      return matchSeason && matchCat && matchEd;
    });

    // Fallback: match by category
    if (!tournament) {
      tournament = state.data.tournaments.find((t) => {
        if (isNationalTournament(t)) return false;
        const matchSeason = !state.selectedSeason || t.season === state.selectedSeason;
        return matchSeason && t.category === state.selectedCategory;
      });
    }
  } else {
    // NACIONAL scope
    tournament = state.data.tournaments.find((t) => {
      if (!isNationalTournament(t)) return false;
      const matchSeason = !state.selectedSeason || t.season === state.selectedSeason;
      const cat = (t.category || '').toUpperCase();
      const nm = (t.name || '').toUpperCase();
      const sel = (state.selectedCategory || '').toUpperCase();
      return matchSeason && (cat.includes(sel) || nm.includes(sel) || sel.includes(cat));
    });

    if (!tournament) {
      tournament = state.data.tournaments.find(isNationalTournament);
    }
  }

  if (tournament) {
    selectTournament(tournament.id);
  } else {
    if (DOM.emptyState) DOM.emptyState.style.display = 'flex';
    if (DOM.dashboardContent) DOM.dashboardContent.style.display = 'none';
  }
}

// Alias for backwards compatibility
const renderTournamentsList = resolveActiveTournament;

// Select a Tournament & Render Full-Width Dashboard
function selectTournament(tournamentId) {
  state.selectedTournamentId = tournamentId;
  state.selectedPhaseIndex = 0;

  const tournament = state.data.tournaments.find((t) => t.id === tournamentId);
  if (!tournament) return;

  DOM.emptyState.style.display = 'none';
  DOM.dashboardContent.style.display = 'block';

  // Update Banner
  DOM.tName.textContent = tournament.category ? `${tournament.category} ${tournament.edition && !tournament.edition.includes('Federación') ? '— ' + tournament.edition : ''}` : tournament.name;
  DOM.tManager.textContent = isNationalTournament(tournament)
    ? 'Confederación Argentina de Cestoball (CADC)'
    : (tournament.name || 'Federación de Cestoball de Capital Federal');

  DOM.tSeasonTag.textContent = tournament.season;
  DOM.tCategoryTag.textContent = tournament.category || 'Categoría';
  DOM.tEditionTag.textContent = isNationalTournament(tournament) ? 'Nacional' : (tournament.edition || 'Torneo');

  const statusText = tournament.status || 'Finalizada';
  const isFinished = statusText.toLowerCase().includes('final');
  DOM.tStatusTag.textContent = statusText;
  DOM.tStatusTag.className = `tag ${isFinished ? 'tag-status-finished' : 'tag-status-live'}`;

  renderPhases(tournament);
  renderPhaseData(tournament);
}

// Render Phase Tabs
function renderPhases(tournament) {
  const phases = tournament.phases || [];
  DOM.phasesTabs.innerHTML = phases
    .map((p, idx) => {
      let icon = '';
      const nameUpper = (p.name || '').toUpperCase();
      if (nameUpper.includes('ORO')) icon = '🏆 ';
      else if (nameUpper.includes('PLATA')) icon = '🥈 ';
      else if (nameUpper.includes('BRONCE')) icon = '🥉 ';
      else if (nameUpper.includes('COPA')) icon = '🛡️ ';

      return `
        <button class="phase-tab ${idx === state.selectedPhaseIndex ? 'active' : ''}" data-phase-idx="${idx}" role="tab">
          ${icon}${p.name}
        </button>
      `;
    })
    .join('');
}

// Switch between Standings, Bracket, and Matches views
function switchPhaseView(viewName) {
  state.activeView = viewName;
  if (DOM.viewTabStandings) DOM.viewTabStandings.classList.toggle('active', viewName === 'standings');
  if (DOM.viewTabBracket) DOM.viewTabBracket.classList.toggle('active', viewName === 'bracket');
  if (DOM.viewTabMatches) DOM.viewTabMatches.classList.toggle('active', viewName === 'matches');

  if (DOM.standingsContainer) DOM.standingsContainer.style.display = viewName === 'standings' ? 'block' : 'none';
  if (DOM.bracketContainer) DOM.bracketContainer.style.display = viewName === 'bracket' ? 'block' : 'none';
  if (DOM.matchesContainer) DOM.matchesContainer.style.display = viewName === 'matches' ? 'block' : 'none';
}

// Render Standings, Matches, and Bracket for Selected Phase
function renderPhaseData(tournament) {
  const phases = tournament.phases || [];
  const activePhase = phases[state.selectedPhaseIndex] || phases[0];

  if (!activePhase) return;

  const phaseName = activePhase.name || 'Fase';
  const isPlayoff = Boolean(
    activePhase.is_playoff ||
    activePhase.bracket ||
    ['COPA', 'PLAYOFF', 'ORO', 'PLATA', 'BRONCE'].some((w) => phaseName.toUpperCase().includes(w))
  );

  DOM.standingsPhaseName.textContent = phaseName;
  DOM.matchesPhaseName.textContent = phaseName;
  if (DOM.bracketPhaseName) DOM.bracketPhaseName.textContent = phaseName;

  if (isPlayoff) {
    if (DOM.viewTabBracket) DOM.viewTabBracket.style.display = 'inline-flex';
    if (!state.activeView || state.activeView === 'bracket' || state.activeView === 'standings') {
      switchPhaseView('bracket');
    } else {
      switchPhaseView(state.activeView);
    }
    renderBracketTree(activePhase, tournament);
  } else {
    if (DOM.viewTabBracket) DOM.viewTabBracket.style.display = 'none';
    if (state.activeView === 'bracket') {
      switchPhaseView('standings');
    } else {
      switchPhaseView(state.activeView || 'standings');
    }
  }

  // 1. Standings Table
  const standings = activePhase.standings || [];
  const sitasStanding = standings.find(
    (s) => s.club_name.toUpperCase().includes(state.targetClub) || (isNationalTournament(tournament) && s.club_name.toUpperCase().includes('CAPITAL'))
  );

  DOM.sitasPosNum.textContent = sitasStanding ? `#${sitasStanding.position}` : '-';

  if (standings.length === 0) {
    DOM.standingsTbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding: 2rem; color: var(--text-muted);">Sin tabla de posiciones disponible para esta fase</td></tr>`;
  } else {
    DOM.standingsTbody.innerHTML = standings
      .map((s) => {
        const isSitas = s.club_name.toUpperCase().includes(state.targetClub) || (isNationalTournament(tournament) && s.club_name.toUpperCase().includes('CAPITAL'));
        const goalDiff = s.goal_diff > 0 ? `+${s.goal_diff}` : s.goal_diff;

        return `
          <tr class="${isSitas ? 'sitas-row' : ''}">
            <td class="td-pos"><span class="pos-pill">${s.position}</span></td>
            <td>
              <div class="club-cell">
                ${renderTeamBadge(s.club_name)}
                <a class="club-link" data-club="${s.club_name}">${s.club_name}</a>
              </div>
            </td>
            <td class="td-num"><strong>${s.points}</strong></td>
            <td class="td-num">${s.played}</td>
            <td class="td-num" style="color: var(--accent-green); font-weight: 600;">${s.won}</td>
            <td class="td-num" style="color: #ef4444;">${s.lost}</td>
            <td class="td-num hide-mobile">${s.goals_for}</td>
            <td class="td-num hide-mobile">${s.goals_against}</td>
            <td class="td-num" style="font-weight: 600;">${goalDiff}</td>
          </tr>
        `;
      })
      .join('');
  }

  // 2. Matches List
  let matches = activePhase.matches || [];
  if (state.onlySitasMatches) {
    matches = matches.filter(
      (m) =>
        m.home_club_name.toUpperCase().includes(state.targetClub) ||
        m.away_club_name.toUpperCase().includes(state.targetClub) ||
        (isNationalTournament(tournament) && (m.home_club_name.toUpperCase().includes('CAPITAL') || m.away_club_name.toUpperCase().includes('CAPITAL')))
    );
  }

  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    matches = matches.filter(
      (m) =>
        (m.home_club_name || '').toLowerCase().includes(q) ||
        (m.away_club_name || '').toLowerCase().includes(q) ||
        (m.round_name || '').toLowerCase().includes(q) ||
        (m.venue || '').toLowerCase().includes(q)
    );
  }

  DOM.matchesTabCount.textContent = matches.length;

  if (matches.length === 0) {
    DOM.matchesList.innerHTML = `
      <div style="text-align:center; padding: 2.5rem; color: var(--text-muted); background: var(--bg-input); border-radius: var(--radius-md);">
        <i data-lucide="calendar-x" style="width: 32px; height: 32px; margin-bottom: 0.5rem;"></i>
        <p>No hay partidos registrados para los filtros seleccionados.</p>
      </div>
    `;
  } else {
    const rounds = {};
    matches.forEach((m) => {
      const r = m.round_name || 'Partidos de la Fase';
      if (!rounds[r]) rounds[r] = [];
      rounds[r].push(m);
    });

    let matchesHtml = '';
    for (const [roundName, roundMatches] of Object.entries(rounds)) {
      matchesHtml += `
        <div class="round-group">
          <div class="round-title"><i data-lucide="flag"></i> ${roundName}</div>
          <div class="matches-cards-container">
      `;

      roundMatches.forEach((m) => {
        const isSitasHome = m.home_club_name.toUpperCase().includes(state.targetClub) || (isNationalTournament(tournament) && m.home_club_name.toUpperCase().includes('CAPITAL'));
        const isSitasAway = m.away_club_name.toUpperCase().includes(state.targetClub) || (isNationalTournament(tournament) && m.away_club_name.toUpperCase().includes('CAPITAL'));
        const isSitas = isSitasHome || isSitasAway;

        let statusTag = '';
        if (m.played) {
          const homeScore = m.home_score ?? 0;
          const awayScore = m.away_score ?? 0;
          if (isSitas) {
            const sitasWon = (isSitasHome && homeScore > awayScore) || (isSitasAway && awayScore > homeScore);
            statusTag = sitasWon
              ? `<span class="match-status-tag win">Victoria</span>`
              : `<span class="match-status-tag loss">Derrota</span>`;
          } else {
            statusTag = `<span class="match-status-tag win">Finalizado</span>`;
          }
        } else {
          statusTag = `<span class="match-status-tag pending">Pendiente</span>`;
        }

        const dateStr = m.scheduled_at
          ? new Date(m.scheduled_at).toLocaleDateString('es-AR', {
              day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
            })
          : 'Horario a confirmar';

        matchesHtml += `
          <div class="match-card ${isSitas ? 'sitas-match' : ''}">
            <div class="match-meta">
              <span class="match-date"><i data-lucide="clock" style="width:13px; height:13px;"></i> ${dateStr}</span>
              ${statusTag}
            </div>
            <div class="match-teams">
              <div class="team-row ${isSitasHome ? 'sitas-team' : ''} ${m.played && m.home_score > m.away_score ? 'winner' : ''}">
                <span style="display:inline-flex;align-items:center;gap:0.4rem;">${renderTeamBadge(m.home_club_name)}${m.home_club_name}</span>
                <span class="team-score">${m.played ? m.home_score : '-'}</span>
              </div>
              <div class="team-row ${isSitasAway ? 'sitas-team' : ''} ${m.played && m.away_score > m.home_score ? 'winner' : ''}">
                <span style="display:inline-flex;align-items:center;gap:0.4rem;">${renderTeamBadge(m.away_club_name)}${m.away_club_name}</span>
                <span class="team-score">${m.played ? m.away_score : '-'}</span>
              </div>
            </div>
          </div>
        `;
      });

      matchesHtml += `</div></div>`;
    }

    DOM.matchesList.innerHTML = matchesHtml;
  }

  if (window.lucide) window.lucide.createIcons();
}

// Render Interactive Bracket Tree Viewer
function renderBracketTree(activePhase, tournament) {
  const container = DOM.bracketTreeViewer;
  if (!container) return;

  let bracketData = activePhase.bracket;
  if (!bracketData || !bracketData.rounds || bracketData.rounds.length === 0) {
    bracketData = buildBracketFromMatches(activePhase.matches || []);
  }

  const rounds = bracketData.rounds || [];
  if (rounds.length === 0) {
    container.innerHTML = `
      <div style="text-align:center; padding: 2.5rem; color: var(--text-muted);">
        <i data-lucide="git-branch" style="width: 32px; height: 32px; margin-bottom: 0.5rem;"></i>
        <p>No se encontraron cruces eliminatorios registrados para esta copa.</p>
      </div>
    `;
    if (window.lucide) window.lucide.createIcons();
    return;
  }

  // Sort rounds logically: Cuartos -> Semifinales -> Final -> Tercer puesto
  const sortedRounds = [...rounds].sort((a, b) => {
    return getRoundSortWeight(a.round_name) - getRoundSortWeight(b.round_name);
  });

  let html = `<div class="bracket-tree">`;

  sortedRounds.forEach((round) => {
    html += `
      <div class="bracket-round-col">
        <div class="bracket-round-title">
          <i data-lucide="trophy" style="width:16px;height:16px;"></i>
          ${round.round_name}
        </div>
        <div class="bracket-round-matches">
    `;

    (round.matches || []).forEach((m) => {
      const homeName = m.home_club?.name || m.home_club_name || 'Por definir';
      const awayName = m.away_club?.name || m.away_club_name || 'Por definir';
      const isSitasHome = homeName.toUpperCase().includes(state.targetClub);
      const isSitasAway = awayName.toUpperCase().includes(state.targetClub);
      const isSitas = isSitasHome || isSitasAway;

      const played = Boolean(m.played);
      const hasGames = Array.isArray(m.games) && m.games.length > 0;

      // Determine series winners
      const isHomeSeriesWin = Boolean(m.home_club?.is_winner) || m.series_winner === 'home';
      const isAwaySeriesWin = Boolean(m.away_club?.is_winner) || m.series_winner === 'away';
      const isFinished = Boolean(m.is_finished) || isHomeSeriesWin || isAwaySeriesWin || (played && !hasGames);

      const homeWinner = isHomeSeriesWin || (!hasGames && played && m.home_score !== null && m.away_score !== null && m.home_score > m.away_score);
      const awayWinner = isAwaySeriesWin || (!hasGames && played && m.home_score !== null && m.away_score !== null && m.away_score > m.home_score);

      const homeLogo = m.home_club?.logo_url || getClubLogoUrl(homeName);
      const awayLogo = m.away_club?.logo_url || getClubLogoUrl(awayName);

      // Status badge
      let statusBadgeHtml = '';
      if (isFinished) {
        statusBadgeHtml = `<span class="badge-status-finished" style="font-size:0.68rem; padding: 2px 6px; border-radius:4px; background: rgba(16,185,129,0.15); color:#4ade80; font-weight:700;">Finalizado</span>`;
      } else if (played) {
        statusBadgeHtml = `<span class="badge-status-live" style="font-size:0.68rem; padding: 2px 6px; border-radius:4px;">En juego</span>`;
      } else {
        statusBadgeHtml = `<span style="font-size:0.68rem; padding: 2px 6px; border-radius:4px; background: rgba(255,255,255,0.05); color:var(--text-muted);">Pendiente</span>`;
      }

      // Render score badges (columns for each game if series, or single badge)
      let homeScoresHtml = '';
      let awayScoresHtml = '';

      if (hasGames) {
        homeScoresHtml = `<div class="bracket-scores-group">` + m.games.map((g) => {
          const scoreText = (g.played && g.home_score !== null) ? g.home_score : '-';
          const isWin = Boolean(g.home_winner);
          return `<span class="bracket-score-badge ${isWin ? 'winner' : ''} ${!g.played ? 'score-pending' : ''}">${scoreText}</span>`;
        }).join('') + `</div>`;

        awayScoresHtml = `<div class="bracket-scores-group">` + m.games.map((g) => {
          const scoreText = (g.played && g.away_score !== null) ? g.away_score : '-';
          const isWin = Boolean(g.away_winner);
          return `<span class="bracket-score-badge ${isWin ? 'winner' : ''} ${!g.played ? 'score-pending' : ''}">${scoreText}</span>`;
        }).join('') + `</div>`;
      } else {
        homeScoresHtml = `<div class="bracket-scores-group"><span class="bracket-score-badge ${homeWinner ? 'winner' : ''} ${!played ? 'score-pending' : ''}">${played && m.home_score !== null ? m.home_score : '-'}</span></div>`;
        awayScoresHtml = `<div class="bracket-scores-group"><span class="bracket-score-badge ${awayWinner ? 'winner' : ''} ${!played ? 'score-pending' : ''}">${played && m.away_score !== null ? m.away_score : '-'}</span></div>`;
      }

      let nextInfoHtml = '';
      if (m.scheduled_at || m.venue) {
        let dateStr = '';
        if (m.scheduled_at) {
          try {
            const d = new Date(m.scheduled_at.replace(' ', 'T'));
            if (!isNaN(d.getTime())) {
              dateStr = d.toLocaleDateString('es-AR', {
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
              });
            }
          } catch (e) {
            dateStr = m.scheduled_at;
          }
        }
        const venueStr = m.venue ? `· ${m.venue}` : '';
        if (dateStr || venueStr) {
          nextInfoHtml = `
            <div class="bracket-match-footer">
              <i data-lucide="clock" style="width:13px; height:13px; flex-shrink:0;"></i>
              <span>${dateStr} ${venueStr}</span>
            </div>
          `;
        }
      }

      html += `
        <div class="bracket-match-node ${isSitas ? 'sitas-match' : ''}">
          <div class="bracket-node-header">
            <span class="bracket-node-label">${m.bracket_label || round.round_name}</span>
            ${statusBadgeHtml}
          </div>

          <div class="bracket-team-item ${homeWinner ? 'winner' : ''} ${isSitasHome ? 'sitas-team' : ''}">
            <div class="bracket-team-info">
              ${homeLogo ? `<img src="${homeLogo}" alt="${homeName}" class="bracket-team-logo" onerror="this.style.display='none'">` : `<i data-lucide="shield" style="width:18px;height:18px;color:var(--text-muted);flex-shrink:0;"></i>`}
              <span class="bracket-team-name-text" title="${homeName}">${homeName}</span>
            </div>
            ${homeScoresHtml}
          </div>

          <div class="bracket-team-item ${awayWinner ? 'winner' : ''} ${isSitasAway ? 'sitas-team' : ''}">
            <div class="bracket-team-info">
              ${awayLogo ? `<img src="${awayLogo}" alt="${awayName}" class="bracket-team-logo" onerror="this.style.display='none'">` : `<i data-lucide="shield" style="width:18px;height:18px;color:var(--text-muted);flex-shrink:0;"></i>`}
              <span class="bracket-team-name-text" title="${awayName}">${awayName}</span>
            </div>
            ${awayScoresHtml}
          </div>

          ${nextInfoHtml}
        </div>
      `;
    });

    html += `</div></div>`;
  });

  html += `</div>`;
  container.innerHTML = html;
  if (window.lucide) window.lucide.createIcons();

  // Initialize smooth drag-to-scroll, scroll arrows, and hint indicator
  setupBracketInteractions();
}

// Setup horizontal drag, arrow navigation and scroll cues for bracket
function setupBracketInteractions() {
  const container = DOM.bracketTreeViewer;
  if (!container) return;

  const btnPrev = document.getElementById('bracket-btn-prev');
  const btnNext = document.getElementById('bracket-btn-next');
  const hint = document.getElementById('bracket-scroll-hint');

  const updateControls = () => {
    const hasOverflow = container.scrollWidth > container.clientWidth + 10;
    if (hint) {
      if (!hasOverflow || container.scrollLeft > 40) {
        hint.style.opacity = '0';
        hint.style.pointerEvents = 'none';
      } else {
        hint.style.opacity = '1';
        hint.style.pointerEvents = 'auto';
      }
    }
    if (btnPrev) {
      const atStart = container.scrollLeft <= 5;
      btnPrev.disabled = atStart;
      btnPrev.style.opacity = atStart ? '0.35' : '1';
    }
    if (btnNext) {
      const atEnd = container.scrollLeft + container.clientWidth >= container.scrollWidth - 10;
      btnNext.disabled = atEnd;
      btnNext.style.opacity = atEnd ? '0.35' : '1';
    }
  };

  if (!container._interactionsBound) {
    container._interactionsBound = true;

    btnPrev?.addEventListener('click', () => {
      container.scrollBy({ left: -300, behavior: 'smooth' });
    });
    btnNext?.addEventListener('click', () => {
      container.scrollBy({ left: 300, behavior: 'smooth' });
    });

    container.addEventListener('scroll', updateControls, { passive: true });
    window.addEventListener('resize', updateControls, { passive: true });

    // Drag-to-scroll for mouse users
    let isDown = false;
    let startX = 0;
    let scrollLeft = 0;

    container.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      isDown = true;
      container.classList.add('is-dragging');
      startX = e.pageX - container.offsetLeft;
      scrollLeft = container.scrollLeft;
    });

    window.addEventListener('mouseup', () => {
      if (isDown) {
        isDown = false;
        container.classList.remove('is-dragging');
      }
    });

    container.addEventListener('mouseleave', () => {
      if (isDown) {
        isDown = false;
        container.classList.remove('is-dragging');
      }
    });

    container.addEventListener('mousemove', (e) => {
      if (!isDown) return;
      e.preventDefault();
      const x = e.pageX - container.offsetLeft;
      const walk = (x - startX) * 1.5;
      container.scrollLeft = scrollLeft - walk;
    });
  }

  // Update controls state
  setTimeout(updateControls, 60);
}

// Helper to sort playoff rounds chronologically
function getRoundSortWeight(name) {
  const n = (name || '').toLowerCase().trim();
  if (n.includes('32')) return 5;
  if (n.includes('16') || n.includes('diecis')) return 10;
  if (n.includes('octav')) return 20;
  if (n.includes('cuart') && !n.includes('puesto')) return 30;
  if (n.includes('semi')) return 40;
  // Tercer y cuarto puesto: después de semifinal (40) y antes de final (50)
  if (
    n.includes('tercer') ||
    n.includes('tercero') ||
    n.includes('3er') ||
    n.includes('3°') ||
    n.includes('3º') ||
    n.includes('3ro') ||
    n.includes('bronce') ||
    n.includes('cuarto puesto') ||
    n.includes('4to puesto') ||
    n.includes('4° puesto') ||
    n.includes('4º puesto')
  ) {
    return 45;
  }
  if (n.includes('final')) return 50;
  if (n.includes('5') || n.includes('quinto')) return 60;
  if (n.includes('7') || n.includes('sept') || n.includes('sépt')) return 70;
  if (n.includes('9') || n.includes('noveno')) return 80;
  if (n.includes('11')) return 85;
  if (n.includes('13')) return 90;
  if (n.includes('15')) return 95;
  return 99;
}

// Fallback: Build bracket tree structure from flat matches list
function buildBracketFromMatches(matches) {
  const roundsMap = {};
  matches.forEach((m) => {
    const rName = m.round_name || 'Eliminatoria';
    if (!roundsMap[rName]) roundsMap[rName] = {};

    const hName = m.home_club_name || m.home_club?.name || 'Por definir';
    const aName = m.away_club_name || m.away_club?.name || 'Por definir';
    const pairKey = [hName, aName].sort().join('___');

    if (!roundsMap[rName][pairKey]) {
      roundsMap[rName][pairKey] = {
        bracket_label: rName,
        match_id: m.clupik_id,
        home_club: { name: hName, is_winner: false },
        away_club: { name: aName, is_winner: false },
        games: [],
        home_score: m.home_score,
        away_score: m.away_score,
        played: false,
        scheduled_at: m.scheduled_at,
        venue: m.venue,
      };
    }

    const entry = roundsMap[rName][pairKey];
    const isDirect = entry.home_club.name === hName;
    const gPlayed = Boolean(m.played);
    const hs = m.home_score;
    const as = m.away_score;
    const gHScore = isDirect ? hs : as;
    const gAScore = isDirect ? as : hs;
    const gHWin = (gPlayed && gHScore !== null && gAScore !== null) ? gHScore > gAScore : false;
    const gAWin = (gPlayed && gHScore !== null && gAScore !== null) ? gAScore > gHScore : false;

    entry.games.push({
      match_id: m.clupik_id,
      game_number: entry.games.length + 1,
      home_score: gHScore,
      away_score: gAScore,
      home_winner: gHWin,
      away_winner: gAWin,
      played: gPlayed,
    });
  });

  const sortedNames = Object.keys(roundsMap).sort((a, b) => getRoundSortWeight(a) - getRoundSortWeight(b));
  return {
    rounds: sortedNames.map((name) => {
      const matchups = Object.values(roundsMap[name]);
      matchups.forEach((mu) => {
        mu.played = mu.games.some((g) => g.played);
        const hWins = mu.games.filter((g) => g.played && g.home_winner).length;
        const aWins = mu.games.filter((g) => g.played && g.away_winner).length;
        if (hWins >= 2 || (mu.games.length === 1 && hWins === 1)) {
          mu.home_club.is_winner = true;
          mu.is_finished = true;
        } else if (aWins >= 2 || (mu.games.length === 1 && aWins === 1)) {
          mu.away_club.is_winner = true;
          mu.is_finished = true;
        } else {
          mu.is_finished = false;
        }
      });
      return {
        round_name: name,
        matches: matchups,
      };
    }),
  };
}

// Update Global KPIs based on active season
function updateKPIs() {
  const tournaments = (state.data?.tournaments || []).filter(
    (t) => (!state.selectedSeason || t.season === state.selectedSeason) && !isNationalTournament(t)
  );

  let totalPlayed = 0;
  let totalWon = 0;
  let totalLost = 0;
  let totalPoints = 0;
  let sitasTournamentsCount = 0;

  tournaments.forEach((t) => {
    let playedInTournament = false;
    (t.phases || []).forEach((p) => {
      const s = (p.standings || []).find((st) => st.club_name.toUpperCase().includes(state.targetClub));
      if (s) {
        playedInTournament = true;
        totalPlayed += s.played || 0;
        totalWon += s.won || 0;
        totalLost += s.lost || 0;
        totalPoints += s.points || 0;
      }
    });
    if (playedInTournament) sitasTournamentsCount++;
  });

  const winrate = totalPlayed > 0 ? Math.round((totalWon / totalPlayed) * 100) : 0;

  DOM.kpiTournaments.textContent = sitasTournamentsCount;
  DOM.kpiPlayed.textContent = totalPlayed;
  DOM.kpiWon.textContent = totalWon;
  DOM.kpiLost.textContent = totalLost;
  DOM.kpiWinrate.textContent = `${winrate}%`;
  DOM.kpiPoints.textContent = totalPoints;
}

// Rival Head-to-Head Modal
function openRivalModal(rivalName) {
  if (!state.data?.tournaments) return;

  DOM.modalRivalName.textContent = rivalName;
  const h2hMatches = [];

  state.data.tournaments.forEach((t) => {
    (t.phases || []).forEach((p) => {
      (p.matches || []).forEach((m) => {
        const involvesSitas = m.home_club_name.toUpperCase().includes(state.targetClub) ||
                              m.away_club_name.toUpperCase().includes(state.targetClub);
        const involvesRival = m.home_club_name.toUpperCase().includes(rivalName.toUpperCase()) ||
                              m.away_club_name.toUpperCase().includes(rivalName.toUpperCase());

        if (involvesSitas && involvesRival) {
          h2hMatches.push({ ...m, tournament_name: t.name, phase_name: p.name });
        }
      });
    });
  });

  let won = 0, lost = 0, played = 0;
  h2hMatches.forEach((m) => {
    if (m.played) {
      played++;
      const isSitasHome = m.home_club_name.toUpperCase().includes(state.targetClub);
      if (isSitasHome ? m.home_score > m.away_score : m.away_score > m.home_score) {
        won++;
      } else {
        lost++;
      }
    }
  });

  DOM.modalBodyContent.innerHTML = `
    <div style="display: flex; gap: 1rem; background: var(--bg-input); padding: 1rem; border-radius: var(--radius-md); justify-content: space-around; text-align: center;">
      <div>
        <span style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary);">${played}</span>
        <div style="font-size: 0.75rem; color: var(--text-muted);">Partidos</div>
      </div>
      <div>
        <span style="font-size: 1.4rem; font-weight: 800; color: var(--accent-green);">${won}</span>
        <div style="font-size: 0.75rem; color: var(--text-muted);">Victorias SITAS</div>
      </div>
      <div>
        <span style="font-size: 1.4rem; font-weight: 800; color: #ef4444;">${lost}</span>
        <div style="font-size: 0.75rem; color: var(--text-muted);">Victorias Rival</div>
      </div>
    </div>

    <h4 style="font-size: 0.95rem; font-family: var(--font-heading); margin-top: 0.5rem;">Historial de Partidos</h4>
    <div style="display: flex; flex-direction: column; gap: 0.5rem; max-height: 350px; overflow-y: auto;">
      ${
        h2hMatches.length === 0
          ? `<p style="color: var(--text-muted); font-size: 0.88rem;">No hay partidos registrados contra este rival aún.</p>`
          : h2hMatches
              .map((m) => `
                <div style="background: var(--bg-input); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 0.75rem; font-size: 0.85rem;">
                  <div style="display: flex; justify-content: space-between; color: var(--text-muted); font-size: 0.75rem; margin-bottom: 0.3rem;">
                    <span>${m.tournament_name}</span>
                    <span>${m.phase_name}</span>
                  </div>
                  <div style="display: flex; justify-content: space-between; font-weight: 600;">
                    <span style="display:inline-flex;align-items:center;gap:0.4rem;">${renderTeamBadge(m.home_club_name)}${m.home_club_name} vs ${renderTeamBadge(m.away_club_name)}${m.away_club_name}</span>
                    <span style="font-family: var(--font-heading);">${m.played ? `${m.home_score} - ${m.away_score}` : 'Pendiente'}</span>
                  </div>
                </div>
              `)
              .join('')
      }
    </div>
  `;

  DOM.h2hModal.style.display = 'flex';
}

// Setup Event Listeners
function setupEventListeners() {
  // Theme Toggle
  DOM.themeToggle.addEventListener('click', () => {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('sitas_theme', state.theme);
    applyTheme(state.theme);
  });

  // Scope Switcher (Metro vs Nacional)
  DOM.scopeTabMetro.addEventListener('click', () => {
    if (state.currentScope === 'METRO') return;
    state.currentScope = 'METRO';
    state.selectedCategory = 'PRIMERA A';
    state.selectedEdition = 'CLAUSURA';
    DOM.scopeTabMetro.classList.add('active');
    DOM.scopeTabMetro.setAttribute('aria-selected', 'true');
    DOM.scopeTabNacional.classList.remove('active');
    DOM.scopeTabNacional.setAttribute('aria-selected', 'false');
    populateCategories();
  });

  DOM.scopeTabNacional.addEventListener('click', () => {
    if (state.currentScope === 'NACIONAL') return;
    state.currentScope = 'NACIONAL';
    state.selectedCategory = 'LIGA NACIONAL MAYORES FEMENINA';
    state.selectedEdition = 'ALL';
    DOM.scopeTabNacional.classList.add('active');
    DOM.scopeTabNacional.setAttribute('aria-selected', 'true');
    DOM.scopeTabMetro.classList.remove('active');
    DOM.scopeTabMetro.setAttribute('aria-selected', 'false');
    populateCategories();
  });

  // Season Picker
  DOM.seasonSelect.addEventListener('change', (e) => {
    state.selectedSeason = e.target.value;
    updateKPIs();
    populateCategories();
  });

  // Category Pills
  DOM.categoryPills.addEventListener('click', (e) => {
    const pill = e.target.closest('.pill');
    if (!pill) return;
    document.querySelectorAll('.pill').forEach((p) => {
      p.classList.remove('active');
      p.setAttribute('aria-selected', 'false');
    });
    pill.classList.add('active');
    pill.setAttribute('aria-selected', 'true');
    state.selectedCategory = pill.dataset.category;
    
    if (state.currentScope === 'METRO') {
      renderEditionFilters();
    }
    resolveActiveTournament();
  });

  // Search Input (filters matches in active tournament)
  DOM.searchInput?.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.trim();
    const tournament = state.data?.tournaments?.find((t) => t.id === state.selectedTournamentId);
    if (tournament) renderPhaseData(tournament);
  });

  // Edition Filter Buttons (Apertura / Clausura / Clasificatorio)
  DOM.editionFilters?.addEventListener('click', (e) => {
    const btn = e.target.closest('.filter-btn');
    if (!btn) return;
    document.querySelectorAll('.edition-filters .filter-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    state.selectedEdition = btn.dataset.edition;
    resolveActiveTournament();
  });

  // Only SITAS Toggle
  DOM.onlySitasToggle.addEventListener('change', (e) => {
    state.onlySitasMatches = e.target.checked;
    const tournament = state.data?.tournaments?.find((t) => t.id === state.selectedTournamentId);
    if (tournament) renderPhaseData(tournament);
  });

  // Tournament Sidebar Selection (if exists)
  DOM.tournamentNavList?.addEventListener('click', (e) => {
    const item = e.target.closest('.tournament-nav-item');
    if (!item) return;
    selectTournament(Number(item.dataset.id));
  });

  // Phase Tab Selection
  DOM.phasesTabs.addEventListener('click', (e) => {
    const tab = e.target.closest('.phase-tab');
    if (!tab) return;
    document.querySelectorAll('.phase-tab').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    state.selectedPhaseIndex = Number(tab.dataset.phaseIdx);
    const tournament = state.data?.tournaments?.find((t) => t.id === state.selectedTournamentId);
    if (tournament) renderPhaseData(tournament);
  });

  // View Switcher (Standings vs Bracket vs Matches)
  DOM.viewTabStandings.addEventListener('click', () => switchPhaseView('standings'));
  if (DOM.viewTabBracket) {
    DOM.viewTabBracket.addEventListener('click', () => switchPhaseView('bracket'));
  }
  DOM.viewTabMatches.addEventListener('click', () => switchPhaseView('matches'));

  // Rival Link Click in Standings Table
  DOM.standingsTbody.addEventListener('click', (e) => {
    const link = e.target.closest('.club-link');
    if (!link) return;
    openRivalModal(link.dataset.club);
  });

  // Modal Close
  DOM.modalClose.addEventListener('click', () => {
    DOM.h2hModal.style.display = 'none';
  });

  DOM.h2hModal.addEventListener('click', (e) => {
    if (e.target === DOM.h2hModal) {
      DOM.h2hModal.style.display = 'none';
    }
  });
}

// Apply Theme
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  DOM.themeIcon.setAttribute('data-lucide', theme === 'dark' ? 'moon' : 'sun');
  if (window.lucide) window.lucide.createIcons();
}

function showError(msg) {
  DOM.emptyState.innerHTML = `
    <i data-lucide="alert-triangle" class="empty-icon" style="color: #ef4444;"></i>
    <h3>Error de carga</h3>
    <p>${msg}</p>
  `;
  if (window.lucide) window.lucide.createIcons();
}

// ==========================================
// Módulo: Próxima Fecha (PDF Importado)
// ==========================================
function resolveMediaUrl(url) {
  if (!url) return null;
  if (url.startsWith('/uploads/')) {
    return url.replace(/^\/+/, '');
  }
  return url;
}

function formatRound(r) {
  if (!r && r !== 0) return '';
  let str = String(r).trim();
  if (!str) return '';

  if (/^\d+$/.test(str)) {
    return `Fecha ${str}`;
  }

  // Normalización y corrección de OCR en instancias
  str = str
    .replace(/\bIida\b/gi, 'Ida')
    .replace(/\blIda\b/g, 'Ida')
    .replace(/Semifial\b/gi, 'Semifinal')
    .replace(/\bAmistos0\b/gi, 'Amistoso')
    .replace(/50\s+Puesto/gi, '5° Puesto')
    .replace(/5[09′'*°º]?\s*al\s*10[9f°'*]?\s*Puesto/gi, '5° al 10° Puesto')
    .replace(/5[09′'*°º]?\s*al\s*9[9°'*]?\s*Puesto/gi, '5° al 9° Puesto')
    .replace(/Puesto\s+del\s+5[09′'*°º]?\s+al\s+10[9f°'*]?/gi, 'Puesto del 5° al 10°')
    .replace(/Puesto\s+del\s+5[09′'*°º]?\s+al\s+9[9°'*]?/gi, 'Puesto del 5° al 9°')
    .replace(/Puesto\s+del\s+9['*]\s+al\s+11['*]?/gi, 'Puesto del 9° al 11°')
    .replace(/3[9#]\s*Partido/gi, '3° Partido')
    .replace(/-(?=[A-Za-z])/g, '- ')
    .replace(/\s+/g, ' ')
    .trim();

  return str;
}

function getStageBadgeHtml(roundNum) {
  const roundStr = formatRound(roundNum);
  if (!roundStr) return '';

  const upper = roundStr.toUpperCase();
  let stageClass = 'stage-default';
  let icon = 'flag';

  if (upper.includes('ORO') || upper.includes('FINAL') || upper.includes('SEMI')) {
    stageClass = 'stage-gold';
    icon = 'trophy';
  } else if (upper.includes('PLATA')) {
    stageClass = 'stage-silver';
    icon = 'trophy';
  } else if (upper.includes('BRONCE') || upper.includes('3°') || upper.includes('TERCER')) {
    stageClass = 'stage-bronze';
    icon = 'trophy';
  } else if (upper.includes('AMISTOSO')) {
    stageClass = 'stage-blue';
    icon = 'activity';
  } else if (upper.startsWith('FECHA')) {
    stageClass = 'stage-default';
    icon = 'calendar';
  }

  return `
    <span class="upcoming-stage-badge ${stageClass}" title="Instancia: ${roundStr}">
      <i data-lucide="${icon}"></i>
      ${roundStr}
    </span>
  `;
}

async function loadUpcomingSchedule() {
  const grid = document.getElementById('upcoming-matches-grid');
  const roundInfo = document.getElementById('upcoming-round-info');
  if (!grid) return;

  try {
    let matches = [];

    // Intento 1: API dinámica (cuando corre con server.py local)
    try {
      const res = await fetch('/api/schedule/upcoming?sitas_only=1');
      if (res.ok) {
        const data = await res.json();
        matches = data.matches || [];
      } else {
        throw new Error('API no disponible');
      }
    } catch {
      // Intento 2: Fallback estático para GitHub Pages
      const resStatic = await fetch('upcoming.json');
      if (resStatic.ok) {
        const dataStatic = await resStatic.json();
        const allMatches = dataStatic.matches || [];
        matches = allMatches.filter((m) => m.is_sitas);
      }
    }

    if (matches.length === 0) {
      grid.innerHTML = `
        <div class="upcoming-empty-card">
          <i data-lucide="calendar-check"></i>
          <p>No hay partidos cargados en el cronograma para esta semana.</p>
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    // Encabezado del cronograma: solo unificar la fecha/instancia si todas las categorías coinciden
    if (roundInfo && matches.length > 0) {
      const uniqueDates = [...new Set(matches.map((m) => (m.match_date || '').trim()).filter(Boolean))];
      let datesStr = '';
      if (uniqueDates.length === 1) {
        datesStr = uniqueDates[0];
      } else if (uniqueDates.length > 1) {
        datesStr = uniqueDates.join(' y ');
      }

      const uniqueRounds = [...new Set(matches.map((m) => formatRound(m.round_num)).filter(Boolean))];

      if (uniqueRounds.length === 1) {
        roundInfo.innerHTML = `<i data-lucide="calendar"></i> ${uniqueRounds[0]} — ${datesStr || 'Próxima Fecha'}`;
      } else {
        roundInfo.innerHTML = `<i data-lucide="calendar"></i> ${datesStr ? 'Fin de Semana — ' + datesStr : 'Cronograma Oficial'}`;
      }
    }

    grid.innerHTML = matches.map((m) => {
      const isHome = /sitas|sita5/i.test(m.home_team);
      const isAway = /sitas|sita5/i.test(m.away_team);
      const venueStr = m.venue ? m.venue : (isHome ? 'SITAS' : m.home_team);
      const stageBadgeHtml = getStageBadgeHtml(m.round_num);

      return `
        <div class="upcoming-card">
          <div class="upcoming-card-header">
            <div class="upcoming-header-badges">
              <span class="upcoming-cat-badge">${m.category}</span>
              ${stageBadgeHtml}
            </div>
            <span class="upcoming-datetime">
              <i data-lucide="clock" style="width:14px;height:14px;"></i>
              ${m.match_date} · ${m.time} hs
            </span>
          </div>

          <div class="upcoming-teams">
            <div class="upcoming-team-line ${isHome ? 'sitas' : ''}">
              <span style="display:inline-flex;align-items:center;gap:0.4rem;">${renderTeamBadge(m.home_team)}${m.home_team}</span>
              ${isHome ? '<span class="tag tag-category" style="font-size:0.65rem;">LOCAL</span>' : ''}
            </div>
            <div class="upcoming-team-line ${isAway ? 'sitas' : ''}">
              <span style="display:inline-flex;align-items:center;gap:0.4rem;">${renderTeamBadge(m.away_team)}${m.away_team}</span>
              ${isAway ? '<span class="tag tag-category" style="font-size:0.65rem;">VISITANTE</span>' : ''}
            </div>
          </div>

          <div class="upcoming-venue-box">
            <div class="upcoming-venue-line">
              <i data-lucide="map-pin" style="width:14px;height:14px;color:var(--accent-gold);"></i>
              <span>Sede: <strong>${venueStr}</strong></span>
            </div>
            ${m.ref1 ? `<div style="font-size:0.75rem;opacity:0.8;">Árbitros: ${m.ref1} ${m.ref2 ? '/ ' + m.ref2 : ''}</div>` : ''}
            ${m.observations ? `<div class="upcoming-obs-badge">ℹ️ ${m.observations}</div>` : ''}
          </div>
        </div>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    console.warn('No se pudieron cargar los próximos partidos:', err);
    grid.innerHTML = `
      <div class="upcoming-empty-card">
        <i data-lucide="calendar"></i>
        <p>Consultá el fixture de cada categoría en la sección de torneos.</p>
      </div>
    `;
    if (window.lucide) window.lucide.createIcons();
  }
}

// ==========================================
// Módulo: Noticias y Galería (Blog)
// ==========================================
let loadedPosts = [];

async function loadNewsFeed() {
  const grid = document.getElementById('news-posts-grid');
  if (!grid) return;

  try {
    let posts = [];

    // Intento 1: API dinámica (cuando corre con server.py local)
    try {
      const res = await fetch('/api/posts?limit=50');
      if (res.ok) {
        const data = await res.json();
        posts = data.posts || [];
      } else {
        throw new Error('API no disponible');
      }
    } catch {
      // Intento 2: Fallback estático para GitHub Pages
      const resStatic = await fetch('posts.json');
      if (resStatic.ok) {
        const dataStatic = await resStatic.json();
        posts = dataStatic.posts || [];
      }
    }

    loadedPosts = posts;

    if (loadedPosts.length === 0) {
      grid.innerHTML = `
        <div class="upcoming-empty-card" style="grid-column: 1/-1;">
          <i data-lucide="newspaper"></i>
          <p>Pronto publicaremos novedades y crónicas de partidos.</p>
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    grid.innerHTML = loadedPosts.map((p, idx) => {
      const dateStr = p.published_at ? new Date(p.published_at).toLocaleDateString('es-AR', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
      const resolvedImg = resolveMediaUrl(p.image_url);
      const img = resolvedImg || 'https://images.unsplash.com/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=800&q=80';

      return `
        <article class="news-card" onclick="openArticleModal(${idx})">
          <div class="news-img-wrap">
            <img src="${img}" alt="${p.title}" class="news-img" loading="lazy" onerror="this.src='https://images.unsplash.com/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=800&q=80'">
            <span class="news-category-tag">${p.category || 'General'}</span>
          </div>
          <div class="news-card-body">
            <h3 class="news-title">${p.title}</h3>
            <p class="news-summary">${p.summary || p.content}</p>
            <span class="news-read-more">Leer artículo completo →</span>
          </div>
        </article>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    console.warn('No se pudieron cargar noticias:', err);
  }
}

function setupScrollSpy() {
  const navLinks = document.querySelectorAll('.nav-links .nav-link:not(.admin-link)');
  const sections = [
    document.getElementById('section-upcoming'),
    document.getElementById('section-tournaments'),
    document.getElementById('section-news')
  ].filter(Boolean);

  if (!sections.length) return;

  const onScroll = () => {
    const scrollPos = window.scrollY + 140;
    let currentSectionId = '';

    for (const section of sections) {
      const top = section.offsetTop;
      const height = section.offsetHeight;
      if (scrollPos >= top && scrollPos < top + height) {
        currentSectionId = section.id;
        break;
      }
    }

    if (!currentSectionId && window.scrollY < 200 && sections[0]) {
      currentSectionId = sections[0].id;
    }

    if (currentSectionId) {
      navLinks.forEach((link) => {
        const href = link.getAttribute('href');
        if (href === `#${currentSectionId}`) {
          link.classList.add('active');
        } else {
          link.classList.remove('active');
        }
      });
    }
  };

  window.addEventListener('scroll', onScroll, { passive: true });
  // Also run on hashchange
  window.addEventListener('hashchange', onScroll);
  setTimeout(onScroll, 300);
}

window.openArticleModal = function(postIndex) {
  const post = loadedPosts[postIndex];
  if (!post) return;

  const modal = document.getElementById('article-modal');
  const title = document.getElementById('article-modal-title');
  const cat = document.getElementById('article-modal-category');
  const date = document.getElementById('article-modal-date');
  const img = document.getElementById('article-modal-img');
  const text = document.getElementById('article-modal-text');
  const btnClose = document.getElementById('article-modal-close');

  title.textContent = post.title;
  cat.textContent = post.category || 'General';
  if (date) date.style.display = 'none';

  const resolvedImg = resolveMediaUrl(post.image_url);
  if (resolvedImg) {
    img.src = resolvedImg;
    img.style.display = 'block';
  } else {
    img.style.display = 'none';
  }

  text.textContent = post.content;
  modal.style.display = 'flex';

  btnClose.onclick = () => { modal.style.display = 'none'; };
  modal.onclick = (e) => { if (e.target === modal) modal.style.display = 'none'; };
};

// Boot
window.addEventListener('DOMContentLoaded', init);

