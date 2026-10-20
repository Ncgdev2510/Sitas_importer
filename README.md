# SITAS Cestoball — Plataforma Web & CPanel Admin

Sistema integral para el Club SITAS Cestoball. Incluye extracción y sincronización automatizada desde Clupik, base de datos SQLite relacional, servidor web en Flask, panel de administración CPanel con autenticación, procesador de cronogramas semanales en PDF y módulo de noticias y galería de fotos.

---

## 🚀 Inicio Rápido

### 1. Iniciar Servidor Web y CPanel
```bash
python server.py
```
- 🌐 **Portal Web Público:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- 🔐 **Panel de Administración:** [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
- 🔑 **Credenciales por defecto:**
  - **Usuario:** `admin`
  - **Contraseña:** `sitas2026`

---

## 🛠️ Módulos Principales del CPanel (`/admin`)

### 1. 📌 Importador de Cronograma Semanal (PDF)
- Permite arrastrar o seleccionar el archivo PDF oficial emitido semanalmente por la Federación (con secciones de `MENORES` y `MAYORES`).
- El módulo de Inteligencia y parseo (`infrastructure/pdf/parser.py`) extrae automáticamente:
  - Número de Fecha y Día (ej. `26/09/2026`, `27/09/2026`).
  - Categorías (`SUB 10`, `SUB 12`, `SUB 14`, `SUB 17`, `SUB 20`, `PRIMERA A`, `PRIMERA B`, `PRIMERA MASCULINO`, etc.).
  - Equipos Local y Visitante, Sede, Horario, Árbitros y Observaciones (ej. cambios de localía o reprogramaciones).
  - Destaca y filtra automáticamente todos los partidos de **SITAS** en el portal público bajo la sección **"Próxima Fecha"**.

### 2. 📰 Noticias, Novedades y Galería de Fotos (Blog)
- Permite a los administradores redactar comunicados, crónicas de partidos, viajes o anuncios institucionales.
- Soporta subida de fotografías (guardadas automáticamente en `web/uploads/`) o URLs directas de imágenes.
- Modal de lectura interactivo y responsivo para los socios y familias en el portal web.

### 3. 🔄 Sincronizador One-Click con Clupik
- Botón interactivo en el CPanel para sincronizar posiciones y fixtures de todos los torneos 2026 (Metropolitanos y Nacionales).
- Resuelve automáticamente los desafíos antibot (Proof-of-Work SHA-256) sin intervención manual.
- Terminal interactiva en vivo con logs de progreso.

---

## 🌐 Portal Web Público (`/`)

1. **Próxima Fecha:** Muestra los partidos que juegan las divisiones de SITAS este fin de semana con fecha, horario, sede y rival.
2. **Noticias y Galería:** Publicaciones recientes con fotos y modal de lectura.
3. **Torneos y Posiciones:**
   - **Scope Switcher:** Separa **Torneos Metropolitanos (Capital)** vs **Competencias Nacionales (Confederación - Ligas Sub 14, Sub 17, Masculina y Campeonato Argentino)**.
   - **KPIs en tiempo real:** Partidos jugados, victorias, derrotas, efectividad y puntos acumulados.
   - **Selector de Categorías:** SUB 10, SUB 12, SUB 14, SUB 17, SUB 20, PRIMERA A, PRIMERA B, PRIMERA MASCULINO, MAXI 30.
   - **Tablas de Posiciones y Fixture:** Con buscador en vivo y switch para ver solo partidos de SITAS.


## Notas sobre el HTML de Clupik (para tener en cuenta al extender esto)

- Las URLs reales son `/es/tournament/{tournament_id}/ranking/{phase_id}`,
  `/es/tournament/{tournament_id}/calendar/{phase_id}` y
  `/es/manager/{manager_id}/tournaments` — no `/ranking/{id}` sueltas
  como se había asumido en un borrador inicial.
- Los números en la tabla de posiciones usan "." como separador de
  miles (ej "1.148") y el atributo `data-sort` trae el signo negativo
  pegado dentro del padding de ceros (ej `"0000...000-33"`), lo cual
  rompe `int()` directo — por eso el parser usa el texto visible, no
  `data-sort`, para esos números.
- En el calendario, la fecha/hora real de cada partido está en el
  atributo `data-sort` de la celda de resultado (formato
  `"<status> <fecha> <hora> <equipo>"`), no en el texto visible.
  Partidos sin fecha aún tienen el sentinela `"9999-99-99 99:99:99"`.
- Cestoball no tiene empates: PJ = PG + PP (no hay columna de empates
  en la tabla de posiciones).
- El listado de torneos del manager mezcla torneos de club (ej "MAXI 30
  | CLAUSURA", donde juega SITAS) con torneos de selecciones ("ARGENTINO
  MAYORES FEMENINO" — participan las selecciones de cada federación,
  no clubes). El modo `--manager-id` los filtra automáticamente porque
  simplemente chequea si SITAS aparece en la clasificación de cada uno.

## 🚀 Sincronización Rápida (1 solo comando)

Para actualizar **todo** (descargar novedades de Clupik, actualizar la base de datos `sitas.db` y refrescar la web al instante):
```bash
python sync.py
```

## 🛠️ Flujo Paso a Paso (Opcional)

Si deseas ejecutar cada paso por separado:

Actualizar solo un torneo específico rápido:
```bash
python sync.py --tournament-id 1339117
```

Actualizar para otro club o federación:
```bash
python sync.py --manager-id 260550 --club SITAS
```

### 1. Descargar datos desde Clupik (Scraper)
Descarga los torneos donde participa SITAS (con resolución automática de anti-bot Proof-of-Work y extracción de posiciones y partidos):
```bash
python main.py --manager-id 260550 --club SITAS
```
Esto genera `sitas_data.json`.

---

### 2. Cargar a Base de Datos (SQLite / PostgreSQL)
Ingesta la data en la base de datos relacional local (`sitas.db`) mediante `UPSERT` idempotente:
```bash
python load_to_db.py --file sitas_data.json
```
*Si tienes datos de años anteriores (ej. `2025.json`, `2024.json`), puedes cargarlos de la misma manera y se acumularán sin pisarse.*

---

### 3. Exportar datos optimizados para el Frontend
Genera el archivo `web/data.json` consolidado a partir de la base de datos:
```bash
python -c "from infrastructure.db.queries import export_data_for_frontend; export_data_for_frontend('web/data.json')"
```

---

### 4. Iniciar el Dashboard Web 
Abre la aplicación web en tu navegador local:
```bash
python serve.py
```
O visita `http://localhost:8000`.

---

## 📁 Estructura del Proyecto

```
sitas_importer/
├── main.py                     # Orquestador del scraping (Clupik -> JSON)
├── load_to_db.py               # Cargador a Base de Datos (JSON -> SQLite/Postgres)
├── serve.py                    # Servidor local para visualizar el dashboard
├── sitas.db                    # Base de datos relacional SQLite
├── sitas_data.json             # Export en JSON crudo
├── domain/
│   └── entities.py             # Modelos de dominio (Tournament, Standing, Match, Club)
├── infrastructure/
│   ├── clupik/
│   │   ├── client.py           # Cliente HTTP + Solucionador anti-bot PoW + Rate Limiting
│   │   └── parser.py           # Parsers HTML de rankings, fases y fixture de partidos
│   └── db/
│       ├── schema.sql          # Esquema relacional SQL
│       ├── database.py         # Conexión y transacciones de DB
│       └── queries.py          # Consultas analíticas y exportador para front
└── web/                        # Frontend Web (Single Page App)
    ├── index.html              # Estructura del Dashboard
    ├── styles.css              # Sistema de diseño, temas claro/oscuro y componentes
    ├── app.js                  # Lógica interactiva, filtros, buscador e historial H2H
    ├── data.json               # Torneos, posiciones y partidos consolidados
    ├── upcoming.json           # Partidos del cronograma semanal (estático)
    ├── posts.json              # Noticias y artículos (estático)
    └── uploads/                # Fotos de noticias y publicaciones
```

---

## 🚀 Publicación Gratuita en GitHub Pages (con Dominio Personalizado)

El proyecto está configurado para publicarse de forma **100% gratuita, ultrarrápida y con SSL automático** en GitHub Pages mediante GitHub Actions.

### 1. Activar GitHub Pages en el repositorio
1. Entra a tu repositorio en GitHub: [Sitas_importer](https://github.com/Ncgdev2510/Sitas_importer).
2. Ve a la pestaña **Settings** (Configuración) > **Pages** (en el menú lateral izquierdo).
3. En **Build and deployment > Source**, selecciona **GitHub Actions**.
4. ¡Listo! El flujo automatizado `.github/workflows/deploy.yml` desplegará la carpeta `web/` cada vez que hagas `git push` a `main`.

### 2. Configurar Dominio Personalizado
1. En **Settings > Pages > Custom domain**, ingresa tu dominio (ej: `cestoballsitas.com` o `cestoball.clubsitas.com.ar`) y haz clic en **Save**.
2. En el panel de control DNS de tu registrador de dominio (NIC Argentina, DonWeb, etc.):
   - Si usas un **subdominio** (ej. `cestoball.clubsitas.com.ar`): Crea un registro **CNAME** con valor `ncgdev2510.github.io`.
   - Si usas un **dominio raíz** (ej. `cestoballsitas.com`): Crea registros **A** con las 4 IPs de GitHub Pages:
     - `185.199.108.153`
     - `185.199.109.153`
     - `185.199.110.153`
     - `185.199.111.153`
3. Una vez propagado el DNS, activa la casilla **Enforce HTTPS** para contar con candado de seguridad SSL gratis.

### 3. Cómo actualizar los datos de la web pública
1. En tu máquina local, actualiza torneos, cronograma PDF o noticias desde el panel (`python server.py`).
2. Exporta o verifica los datos estáticos:
   ```bash
   python export_static.py
   ```
3. Sube los cambios a GitHub:
   ```bash
   git add .
   git commit -m "Actualizar datos y resultados"
   git push
   ```
   GitHub Pages se actualizará automáticamente en menos de 1 minuto.
