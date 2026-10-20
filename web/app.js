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
  selectedCategory: 'ALL',
  selectedEdition: 'ALL',
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

// Populate Categories according to current scope (Metro vs Nacional)
function populateCategories() {
  if (state.currentScope === 'METRO') {
    if (DOM.editionFilters) DOM.editionFilters.style.display = 'flex';

    const metroCategories = [
      'PRIMERA A',
      'PRIMERA B',
      'PRIMERA MASCULINO',
      'SUB 20',
      'SUB 17',
      'SUB 17 FLEX',
      'SUB 14',
      'SUB 14 FLEX',
      'SUB 12',
      'SUB 10',
      'MAXI 30',
    ];

    let html = `
      <button class="pill ${state.selectedCategory === 'ALL' ? 'active' : ''}" data-category="ALL" role="tab">
        <i data-lucide="layout-grid"></i> Todas las Categorías
      </button>
    `;

    metroCategories.forEach((cat) => {
      html += `
        <button class="pill ${state.selectedCategory === cat ? 'active' : ''}" data-category="${cat}" role="tab">
          ${cat}
        </button>
      `;
    });

    DOM.categoryPills.innerHTML = html;
  } else {
    // Competencias Nacionales
    if (DOM.editionFilters) DOM.editionFilters.style.display = 'none';

    const nationalFilters = [
      { id: 'ALL', label: 'Todas las Nacionales', icon: 'trophy' },
      { id: 'LIGA', label: 'Ligas Nacionales (Clubes)', icon: 'shield' },
      { id: 'ARGENTINO', label: 'Campeonatos Argentinos', icon: 'flag' },
    ];

    let html = '';
    nationalFilters.forEach((f) => {
      html += `
        <button class="pill ${state.selectedCategory === f.id ? 'active' : ''}" data-category="${f.id}" role="tab">
          <i data-lucide="${f.icon}"></i> ${f.label}
        </button>
      `;
    });

    DOM.categoryPills.innerHTML = html;
  }

  if (window.lucide) window.lucide.createIcons();
}

// Filtered Tournaments
function getFilteredTournaments() {
  if (!state.data?.tournaments) return [];

  return state.data.tournaments.filter((t) => {
    const isNat = isNationalTournament(t);

    // 1. Scope filter
    if (state.currentScope === 'METRO' && isNat) return false;
    if (state.currentScope === 'NACIONAL' && !isNat) return false;

    // 2. Season filter
    const matchSeason = !state.selectedSeason || t.season === state.selectedSeason;
    if (!matchSeason) return false;

    // 3. Category / Sub-type filter
    if (state.currentScope === 'METRO') {
      if (state.selectedCategory !== 'ALL' && t.category !== state.selectedCategory) {
        return false;
      }
      if (state.selectedEdition !== 'ALL') {
        const ed = (t.edition || '').toUpperCase();
        const nm = (t.name || '').toUpperCase();
        if (!ed.includes(state.selectedEdition) && !nm.includes(state.selectedEdition)) {
          return false;
        }
      }
    } else {
      // NACIONAL filter
      const nm = (t.name || '').toUpperCase();
      const cat = (t.category || '').toUpperCase();
      if (state.selectedCategory === 'LIGA') {
        if (!nm.includes('LIGA') && !cat.includes('LIGA')) return false;
      } else if (state.selectedCategory === 'ARGENTINO') {
        if (!nm.includes('ARGENTINO') && !cat.includes('ARGENTINO')) return false;
      }
    }

    // 4. Search query
    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase();
      const inName = (t.name || '').toLowerCase().includes(q);
      const inCat = (t.category || '').toLowerCase().includes(q);
      const inClubs = (t.phases || []).some((p) =>
        (p.standings || []).some((s) => (s.club_name || '').toLowerCase().includes(q))
      );
      if (!inName && !inCat && !inClubs) return false;
    }

    return true;
  });
}

// Render Tournaments in Sidebar
function renderTournamentsList() {
  const tournaments = getFilteredTournaments();
  DOM.tournamentCount.textContent = tournaments.length;

  if (tournaments.length === 0) {
    DOM.tournamentNavList.innerHTML = `
      <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.88rem;">
        No se encontraron torneos para los filtros seleccionados.
      </div>
    `;
    DOM.emptyState.style.display = 'flex';
    DOM.dashboardContent.style.display = 'none';
    return;
  }

  DOM.tournamentNavList.innerHTML = tournaments
    .map((t) => {
      const isSelected = t.id === state.selectedTournamentId;
      const isFinished = (t.status || '').toLowerCase().includes('final');

      let displayCat = t.category || t.name;
      let displayEd = t.edition || t.season;

      if (isNationalTournament(t)) {
        if (displayCat.includes('LIGA NACIONAL')) {
          displayEd = 'LIGA NACIONAL';
        } else if (displayCat.includes('ARGENTINO')) {
          displayEd = 'CAMPEONATO';
        }
      }

      return `
        <div class="tournament-nav-item ${isSelected ? 'active' : ''}" data-id="${t.id}" role="button">
          <div class="t-item-header">
            <span class="t-item-category">${displayCat}</span>
            <span class="t-item-edition">${displayEd}</span>
          </div>
          <div class="t-item-status">
            <span class="status-dot ${isFinished ? 'finished' : ''}"></span>
            ${t.status || 'Finalizada'} • ${t.phases?.length || 1} fases
          </div>
        </div>
      `;
    })
    .join('');

  // Auto-select first if none selected or not in current list
  const currentExists = tournaments.some((t) => t.id === state.selectedTournamentId);
  if (!currentExists && tournaments.length > 0) {
    selectTournament(tournaments[0].id);
  } else if (state.selectedTournamentId) {
    selectTournament(state.selectedTournamentId);
  }
}

// Select a Tournament
function selectTournament(tournamentId) {
  state.selectedTournamentId = tournamentId;
  state.selectedPhaseIndex = 0;

  // Highlight in sidebar
  document.querySelectorAll('.tournament-nav-item').forEach((el) => {
    el.classList.toggle('active', Number(el.dataset.id) === tournamentId);
  });

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

  let html = `<div class="bracket-tree">`;

  rounds.forEach((round) => {
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
      const homeScore = m.home_score;
      const awayScore = m.away_score;
      const homeWinner = played && homeScore !== null && awayScore !== null && homeScore > awayScore;
      const awayWinner = played && homeScore !== null && awayScore !== null && awayScore > homeScore;

      const homeLogo = m.home_club?.logo_url || getClubLogoUrl(homeName);
      const awayLogo = m.away_club?.logo_url || getClubLogoUrl(awayName);

      let nextInfoHtml = '';
      if (m.scheduled_at || m.venue) {
        const dateStr = m.scheduled_at
          ? new Date(m.scheduled_at).toLocaleDateString('es-AR', {
              day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
            })
          : '';
        const venueStr = m.venue ? `· ${m.venue}` : '';
        nextInfoHtml = `
          <div class="bracket-match-footer">
            <i data-lucide="clock" style="width:13px; height:13px; flex-shrink:0;"></i>
            <span>${dateStr} ${venueStr}</span>
          </div>
        `;
      }

      html += `
        <div class="bracket-match-node ${isSitas ? 'sitas-match' : ''}">
          <div class="bracket-node-header">
            <span class="bracket-node-label">${m.bracket_label || round.round_name}</span>
            ${played ? `<span class="badge-status-finished" style="font-size:0.68rem; padding: 2px 6px; border-radius:4px; background: rgba(16,185,129,0.15); color:#4ade80;">Finalizado</span>` : `<span style="font-size:0.68rem; padding: 2px 6px; border-radius:4px; background: rgba(255,255,255,0.05); color:var(--text-muted);">Pendiente</span>`}
          </div>

          <div class="bracket-team-item ${homeWinner ? 'winner' : ''} ${isSitasHome ? 'sitas-team' : ''}">
            <div class="bracket-team-info">
              ${homeLogo ? `<img src="${homeLogo}" alt="${homeName}" class="bracket-team-logo" onerror="this.style.display='none'">` : `<i data-lucide="shield" style="width:18px;height:18px;color:var(--text-muted);flex-shrink:0;"></i>`}
              <span class="bracket-team-name-text" title="${homeName}">${homeName}</span>
            </div>
            <span class="bracket-score-badge ${homeWinner ? 'winner' : ''}">${played ? homeScore : '-'}</span>
          </div>

          <div class="bracket-team-item ${awayWinner ? 'winner' : ''} ${isSitasAway ? 'sitas-team' : ''}">
            <div class="bracket-team-info">
              ${awayLogo ? `<img src="${awayLogo}" alt="${awayName}" class="bracket-team-logo" onerror="this.style.display='none'">` : `<i data-lucide="shield" style="width:18px;height:18px;color:var(--text-muted);flex-shrink:0;"></i>`}
              <span class="bracket-team-name-text" title="${awayName}">${awayName}</span>
            </div>
            <span class="bracket-score-badge ${awayWinner ? 'winner' : ''}">${played ? awayScore : '-'}</span>
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
}

// Fallback: Build bracket tree structure from flat matches list
function buildBracketFromMatches(matches) {
  const roundOrder = {
    'octav': 1,
    'cuart': 2,
    'semi': 3,
    'final': 4,
    'tercer': 5,
  };

  function getRoundWeight(name) {
    const n = (name || '').toLowerCase();
    for (const [k, w] of Object.entries(roundOrder)) {
      if (n.includes(k)) return w;
    }
    return 99;
  }

  const roundsMap = {};
  matches.forEach((m) => {
    const rName = m.round_name || 'Eliminatoria';
    if (!roundsMap[rName]) roundsMap[rName] = [];
    roundsMap[rName].push({
      bracket_label: rName,
      match_id: m.clupik_id,
      home_club: { name: m.home_club_name || m.home_club?.name },
      away_club: { name: m.away_club_name || m.away_club?.name },
      home_score: m.home_score,
      away_score: m.away_score,
      played: m.played,
      scheduled_at: m.scheduled_at,
      venue: m.venue,
    });
  });

  const sortedNames = Object.keys(roundsMap).sort((a, b) => getRoundWeight(a) - getRoundWeight(b));
  return {
    rounds: sortedNames.map((name) => ({
      round_name: name,
      matches: roundsMap[name],
    })),
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
    state.selectedCategory = 'ALL';
    state.selectedEdition = 'ALL';
    DOM.scopeTabMetro.classList.add('active');
    DOM.scopeTabMetro.setAttribute('aria-selected', 'true');
    DOM.scopeTabNacional.classList.remove('active');
    DOM.scopeTabNacional.setAttribute('aria-selected', 'false');
    populateCategories();
    renderTournamentsList();
  });

  DOM.scopeTabNacional.addEventListener('click', () => {
    if (state.currentScope === 'NACIONAL') return;
    state.currentScope = 'NACIONAL';
    state.selectedCategory = 'ALL';
    DOM.scopeTabNacional.classList.add('active');
    DOM.scopeTabNacional.setAttribute('aria-selected', 'true');
    DOM.scopeTabMetro.classList.remove('active');
    DOM.scopeTabMetro.setAttribute('aria-selected', 'false');
    populateCategories();
    renderTournamentsList();
  });

  // Season Picker
  DOM.seasonSelect.addEventListener('change', (e) => {
    state.selectedSeason = e.target.value;
    updateKPIs();
    renderTournamentsList();
  });

  // Category Pills
  DOM.categoryPills.addEventListener('click', (e) => {
    const pill = e.target.closest('.pill');
    if (!pill) return;
    document.querySelectorAll('.pill').forEach((p) => p.classList.remove('active'));
    pill.classList.add('active');
    state.selectedCategory = pill.dataset.category;
    renderTournamentsList();
  });

  // Search Input
  DOM.searchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.trim();
    renderTournamentsList();
  });

  // Edition Filter Buttons (Apertura / Clausura)
  DOM.editionFilters.addEventListener('click', (e) => {
    const btn = e.target.closest('.filter-btn');
    if (!btn) return;
    document.querySelectorAll('.filter-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    state.selectedEdition = btn.dataset.edition;
    renderTournamentsList();
  });

  // Only SITAS Toggle
  DOM.onlySitasToggle.addEventListener('change', (e) => {
    state.onlySitasMatches = e.target.checked;
    const tournament = state.data?.tournaments?.find((t) => t.id === state.selectedTournamentId);
    if (tournament) renderPhaseData(tournament);
  });

  // Tournament Sidebar Selection
  DOM.tournamentNavList.addEventListener('click', (e) => {
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

    if (matches[0] && roundInfo) {
      roundInfo.innerHTML = `<i data-lucide="calendar"></i> Fecha ${matches[0].round_num || ''} — ${matches[0].match_date || ''}`;
    }

    grid.innerHTML = matches.map((m) => {
      const isHome = m.home_team.toUpperCase().includes('SITAS');
      const venueStr = m.venue ? m.venue : (isHome ? 'SITAS' : m.home_team);

      return `
        <div class="upcoming-card">
          <div class="upcoming-card-header">
            <span class="upcoming-cat-badge">${m.category}</span>
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
            <div class="upcoming-team-line ${!isHome ? 'sitas' : ''}">
              <span style="display:inline-flex;align-items:center;gap:0.4rem;">${renderTeamBadge(m.away_team)}${m.away_team}</span>
              ${!isHome ? '<span class="tag tag-category" style="font-size:0.65rem;">VISITANTE</span>' : ''}
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
            <span class="news-date">📅 ${dateStr} ${p.author_name ? '· ' + p.author_name : ''}</span>
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
  const dateStr = post.published_at ? new Date(post.published_at).toLocaleDateString('es-AR', { day: 'numeric', month: 'long', year: 'numeric' }) : '';
  date.textContent = `${dateStr} ${post.author_name ? '· Publicado por ' + post.author_name : ''}`;

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

