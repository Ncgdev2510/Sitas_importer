-- Esquema relacional para Importador SITAS / Cestoball
-- Compatible con SQLite y PostgreSQL

CREATE TABLE IF NOT EXISTS clubs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clupik_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS managers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clupik_id INTEGER UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clupik_id INTEGER UNIQUE NOT NULL,
    name TEXT,
    season TEXT NOT NULL,
    category TEXT,
    edition TEXT,
    modality TEXT,
    sex TEXT,
    status TEXT,
    manager_id INTEGER REFERENCES managers(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    clupik_phase_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tournament_id, clupik_phase_id)
);

CREATE TABLE IF NOT EXISTS standings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    phase_id INTEGER NOT NULL REFERENCES phases(id) ON DELETE CASCADE,
    club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    played INTEGER DEFAULT 0,
    won INTEGER DEFAULT 0,
    drawn INTEGER DEFAULT 0,
    lost INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goal_diff INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(phase_id, club_id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clupik_id INTEGER UNIQUE,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    phase_id INTEGER REFERENCES phases(id) ON DELETE CASCADE,
    round_name TEXT,
    scheduled_at TIMESTAMP,
    home_club_id INTEGER NOT NULL REFERENCES clubs(id),
    away_club_id INTEGER NOT NULL REFERENCES clubs(id),
    home_score INTEGER,
    away_score INTEGER,
    venue TEXT,
    played BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices de búsqueda y rendimiento
CREATE INDEX IF NOT EXISTS idx_tournaments_season ON tournaments(season);
CREATE INDEX IF NOT EXISTS idx_tournaments_category ON tournaments(category);
CREATE INDEX IF NOT EXISTS idx_standings_club ON standings(club_id);
CREATE INDEX IF NOT EXISTS idx_standings_phase ON standings(phase_id);
CREATE INDEX IF NOT EXISTS idx_matches_home_club ON matches(home_club_id);
CREATE INDEX IF NOT EXISTS idx_matches_away_club ON matches(away_club_id);
CREATE INDEX IF NOT EXISTS idx_matches_phase ON matches(phase_id);
CREATE INDEX IF NOT EXISTS idx_matches_scheduled ON matches(scheduled_at);

-- ==========================================
-- Módulo AdminPanel: Usuarios y Autenticación
-- ==========================================
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'admin',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================
-- Módulo Admin Panel: Blog y Noticias con Fotos
-- ==========================================
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT DEFAULT 'General',
    summary TEXT,
    content TEXT NOT NULL,
    image_url TEXT,
    author_id INTEGER REFERENCES users(id),
    published BOOLEAN DEFAULT 1,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published, published_at);

-- ==========================================
-- Módulo Admin Panel: Cronograma / Próximos Partidos (PDF)
-- ==========================================
CREATE TABLE IF NOT EXISTS upcoming_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    division TEXT,
    round_num INTEGER,
    match_date TEXT,
    time TEXT,
    category TEXT,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    venue TEXT,
    ref1 TEXT,
    ref2 TEXT,
    observations TEXT,
    is_sitas BOOLEAN DEFAULT 0,
    batch_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_upcoming_is_sitas ON upcoming_matches(is_sitas);
CREATE INDEX IF NOT EXISTS idx_upcoming_category ON upcoming_matches(category);

