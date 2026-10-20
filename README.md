# SITAS Cestoball — Plataforma Web & CPanel Admin

Sistema integral para el Club SITAS Cestoball. Incluye extracción y sincronización automatizada desde Clupik, base de datos SQLite relacional, servidor web en Flask, panel de administración CPanel con autenticación, procesador de cronogramas semanales en PDF y módulo de noticias y galería de fotos.

---

## 🚀 Inicio Rápido

### 1. Iniciar Servidor Web y CPanel
```bash
python server.py
```
- 🌐 **Portal Web Público:** 
- 🔐 **Panel de Administración:** 
- 🔑 **Credenciales por defecto:**
  - **Usuario:** `xxxx`
  - **Contraseña:** `xxxxx`

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
