/**
 * SITAS Cestoball - Panel Admin Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // State
  let currentUser = null;
  let allScheduleMatches = [];
  let selectedPdfFile = null;

  // DOM Elements
  const loginScreen = document.getElementById("login-screen");
  const loginForm = document.getElementById("login-form");
  const loginError = document.getElementById("login-error");
  const adminApp = document.getElementById("admin-app");
  const btnLogout = document.getElementById("btn-logout");
  const userRoleBadge = document.getElementById("user-role-badge");

  // Tabs
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  // PDF Uploader
  const pdfDropzone = document.getElementById("pdf-dropzone");
  const pdfFileInput = document.getElementById("pdf-file-input");
  const selectedFileInfo = document.getElementById("selected-file-info");
  const fileNameLabel = document.getElementById("file-name-label");
  const btnRemoveFile = document.getElementById("btn-remove-file");
  const btnProcessPdf = document.getElementById("btn-process-pdf");
  const pdfUploadForm = document.getElementById("pdf-upload-form");
  const publishImmediately = document.getElementById("publish-immediately");

  // Schedule Stats & Table
  const statSitasMatches = document.getElementById("stat-sitas-matches");
  const statTotalMatches = document.getElementById("stat-total-matches");
  const scheduleTbody = document.getElementById("schedule-tbody");
  const filterSitasOnly = document.getElementById("filter-sitas-only");
  const filterDivision = document.getElementById("filter-division");
  const btnClearSchedule = document.getElementById("btn-clear-schedule");

  // Posts Form & List
  const postCreateForm = document.getElementById("post-create-form");
  const postsAdminList = document.getElementById("posts-admin-list");
  const postsCount = document.getElementById("posts-count");

  // Clupik Sync
  const btnTriggerSync = document.getElementById("btn-trigger-sync");
  const syncStatusIndicator = document.getElementById("sync-status-indicator");
  const syncLoadingCard = document.getElementById("sync-loading-card");
  const syncLiveTimer = document.getElementById("sync-live-timer");
  const syncSeasonSelect = document.getElementById("sync-season-select");
  const syncEditionSelect = document.getElementById("sync-edition-select");
  const syncTerminal = document.getElementById("sync-terminal");
  const syncOutput = document.getElementById("sync-output");
  const syncTimer = document.getElementById("sync-timer");

  let syncTimerInterval = null;
  let syncStatusPollTimer = null;
  let isSyncing = false;

  // Toast Container
  const toastContainer = document.getElementById("toast-container");

  // ==========================================
  // Toast Helper
  // ==========================================
  function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    let icon = "✅";
    if (type === "error") icon = "❌";
    if (type === "warning") icon = "⚠️";
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // ==========================================
  // Auth & Session
  // ==========================================
  async function checkSession() {
    try {
      const res = await fetch("/api/auth/me");
      if (res.ok) {
        const data = await res.json();
        if (data.authenticated && data.user) {
          currentUser = data.user;
          onLoginSuccess(currentUser);
          return;
        }
      }
    } catch (e) {
      console.warn("No active session:", e);
    }
    showLoginScreen();
  }

  function showLoginScreen() {
    loginScreen.style.display = "flex";
    adminApp.style.display = "none";
  }

  function onLoginSuccess(user) {
    currentUser = user;
    loginScreen.style.display = "none";
    adminApp.style.display = "flex";
    userRoleBadge.textContent = `${user.username} (${user.role.toUpperCase()})`;
    loadScheduleData();
    loadPostsData();
    checkBackendSyncStatus();
  }

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.style.display = "none";
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;

    const btnLogin = document.getElementById("btn-login");
    btnLogin.disabled = true;
    btnLogin.innerText = "Ingresando...";

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast("¡Bienvenido al Admin Panel de SITAS!", "success");
        onLoginSuccess(data.user);
      } else {
        loginError.textContent = data.error || "Credenciales incorrectas";
        loginError.style.display = "block";
      }
    } catch (err) {
      loginError.textContent = "Error de conexión con el servidor";
      loginError.style.display = "block";
    } finally {
      btnLogin.disabled = false;
      btnLogin.innerHTML = "<span>Ingresar al Admin Panel</span>";
    }
  });

  btnLogout.addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      showToast("Sesión cerrada", "warning");
      currentUser = null;
      showLoginScreen();
    } catch (e) {
      console.error(e);
    }
  });

  // ==========================================
  // Navigation Tabs
  // ==========================================
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      tabButtons.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));

      btn.classList.add("active");
      const contentEl = document.getElementById(targetTab);
      if (contentEl) contentEl.classList.add("active");
      if (targetTab === "tab-clupik") {
        checkBackendSyncStatus();
      }
    });
  });

  // ==========================================
  // PDF Drag & Drop & Upload
  // ==========================================
  pdfDropzone.addEventListener("click", () => pdfFileInput.click());

  pdfDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    pdfDropzone.classList.add("dragover");
  });

  pdfDropzone.addEventListener("dragleave", () => {
    pdfDropzone.classList.remove("dragover");
  });

  pdfDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    pdfDropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  pdfFileInput.addEventListener("change", () => {
    if (pdfFileInput.files && pdfFileInput.files.length > 0) {
      handleFileSelected(pdfFileInput.files[0]);
    }
  });

  function handleFileSelected(file) {
    const validExtensions = [".pdf", ".png", ".jpg", ".jpeg", ".webp"];
    const isValid = validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
    if (!isValid) {
      showToast("Por favor seleccioná un archivo PDF o una imagen (.png, .jpg, .webp)", "error");
      return;
    }
    selectedPdfFile = file;
    fileNameLabel.textContent = file.name;
    selectedFileInfo.style.display = "flex";
    btnProcessPdf.disabled = false;
  }

  btnRemoveFile.addEventListener("click", () => {
    selectedPdfFile = null;
    pdfFileInput.value = "";
    selectedFileInfo.style.display = "none";
    btnProcessPdf.disabled = true;
  });

  pdfUploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedPdfFile) return;

    btnProcessPdf.disabled = true;
    btnProcessPdf.innerHTML = `<span>⏳ Procesando fixture con OCR e Inteligencia...</span>`;

    const formData = new FormData();
    formData.append("pdf", selectedPdfFile);
    formData.append("publish", publishImmediately.checked ? "1" : "0");
    const uploadMode = document.querySelector('input[name="upload-mode"]:checked')?.value || "replace";
    formData.append("mode", uploadMode);

    try {
      const res = await fetch("/api/schedule/upload-pdf", {
        method: "POST",
        body: formData
      });
      const data = await res.json();

      if (res.ok && data.success) {
        showToast(`¡Éxito! Se procesaron ${data.total_parsed} partidos (${data.sitas_matches_count} de SITAS)`, "success");
        loadScheduleData();
        // Reset file
        selectedPdfFile = null;
        pdfFileInput.value = "";
        selectedFileInfo.style.display = "none";
      } else {
        showToast(data.error || "Error al procesar el archivo PDF", "error");
      }
    } catch (err) {
      showToast("Error de comunicación al subir PDF", "error");
    } finally {
      btnProcessPdf.disabled = !selectedPdfFile;
      btnProcessPdf.innerHTML = `<span>⚡ Procesar y Publicar Partidos</span>`;
    }
  });

  // ==========================================
  // Schedule Table & Filter Logic
  // ==========================================
  function formatAdminRound(r) {
    if (!r && r !== 0) return '';
    let str = String(r).trim();
    if (!str) return '';
    if (/^\d+$/.test(str)) return `Fecha ${str}`;
    return str
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
  }
  async function loadScheduleData() {
    try {
      const res = await fetch("/api/schedule/upcoming?sitas_only=0");
      if (res.ok) {
        const data = await res.json();
        allScheduleMatches = data.matches || [];
        renderScheduleStats();
        renderScheduleTable();
      }
    } catch (e) {
      console.error("Error loading schedule:", e);
    }
  }

  function renderScheduleStats() {
    const sitasMatches = allScheduleMatches.filter(m => m.is_sitas);
    statSitasMatches.textContent = sitasMatches.length;
    statTotalMatches.textContent = allScheduleMatches.length;
  }

  function renderScheduleTable() {
    const sitasOnly = filterSitasOnly.checked;
    const division = filterDivision.value;

    let filtered = allScheduleMatches;
    if (sitasOnly) {
      filtered = filtered.filter(m => m.is_sitas);
    }
    if (division) {
      filtered = filtered.filter(m => m.division === division);
    }

    if (filtered.length === 0) {
      scheduleTbody.innerHTML = `
        <tr>
          <td colspan="8" class="text-center text-muted" style="padding:32px;">
            No hay partidos en el cronograma para los filtros seleccionados.
          </td>
        </tr>
      `;
      return;
    }

    scheduleTbody.innerHTML = filtered.map(m => {
      const isSitas = m.is_sitas;
      const homeClass = /sitas|sita5/i.test(m.home_team) ? "team-highlight" : "";
      const awayClass = /sitas|sita5/i.test(m.away_team) ? "team-highlight" : "";
      const stageStr = formatAdminRound(m.round_num);

      return `
        <tr class="${isSitas ? 'sitas-row' : ''}">
          <td><span class="badge-div">${m.division}</span></td>
          <td><span class="badge-cat">${m.category}</span></td>
          <td><span class="badge-stage">${stageStr || '-'}</span></td>
          <td>
            <strong>${m.match_date}</strong><br>
            <span class="text-muted" style="font-size:0.8rem;">⏰ ${m.time} hs</span>
          </td>
          <td>
            <span class="${homeClass}">${m.home_team}</span> 
            <span class="text-muted">vs</span> 
            <span class="${awayClass}">${m.away_team}</span>
          </td>
          <td><strong>${m.venue || '-'}</strong></td>
          <td>
            ${(() => {
              let r1 = (m.ref1 || '').trim();
              let r2 = (m.ref2 || '').trim();
              let obs = (m.observations || '').trim();
              if (!r2 && obs && /[\(\[\{][A-Za-z0-9\u03b2][\)\]\}]\s*$/.test(obs) && !/(localia|horarios|disponibilidad|presenta|gana|torneo|sede|lleguen|jugadoras)/i.test(obs)) {
                r2 = obs;
                obs = '';
              }
              const refs = [r1, r2].filter(Boolean);
              return `
                ${obs ? `<span class="badge-div" style="background:rgba(245,158,11,0.15); color:#F59E0B;">${obs}</span>` : '-'}
                ${refs.length ? `<div style="font-size:0.75rem; color:#94A3B8; margin-top:2px;">Árbitros: ${refs.join(' / ')}</div>` : ''}
              `;
            })()}
          </td>
          <td style="text-align:center;">
            <button type="button" class="btn btn-outline-danger btn-xs btn-delete-match" data-id="${m.id}" title="Eliminar partido del cronograma" style="padding:3px 7px; font-size:0.75rem; cursor:pointer;">
              🗑️
            </button>
          </td>
        </tr>
      `;
    }).join("");
  }

  filterSitasOnly.addEventListener("change", renderScheduleTable);
  filterDivision.addEventListener("change", renderScheduleTable);

  scheduleTbody.addEventListener("click", async (e) => {
    const btn = e.target.closest(".btn-delete-match");
    if (!btn) return;
    const matchId = btn.dataset.id;
    if (!matchId) return;

    if (!confirm("¿Deseas eliminar este partido del cronograma activo?")) return;

    try {
      btn.disabled = true;
      const res = await fetch(`/api/schedule/matches/${matchId}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast("Partido eliminado con éxito", "success");
        loadScheduleData();
      } else {
        showToast(data.error || "Error al eliminar partido", "error");
      }
    } catch (err) {
      showToast("Error de conexión al eliminar partido", "error");
    }
  });

  btnClearSchedule.addEventListener("click", async () => {
    if (!confirm("¿Estás seguro de que deseás borrar todo el cronograma actual?")) return;
    try {
      const res = await fetch("/api/schedule/clear", { method: "POST" });
      if (res.ok) {
        showToast("Cronograma eliminado correctamente", "warning");
        loadScheduleData();
      }
    } catch (e) {
      showToast("Error al borrar cronograma", "error");
    }
  });

  // ==========================================
  // Posts / News Management
  // ==========================================
  let localAdminPosts = [];
  const postIdInput = document.getElementById("post-id");
  const postFormTitle = document.getElementById("post-form-title");
  const btnCancelEdit = document.getElementById("btn-cancel-edit");
  const postPublishedSelect = document.getElementById("post-published");

  async function loadPostsData() {
    try {
      const res = await fetch("/api/posts?limit=50");
      if (res.ok) {
        const data = await res.json();
        localAdminPosts = data.posts || [];
        postsCount.textContent = localAdminPosts.length;
        renderPostsList(localAdminPosts);
      }
    } catch (e) {
      console.error("Error loading posts:", e);
    }
  }


  function renderPostsList(posts) {
    if (posts.length === 0) {
      postsAdminList.innerHTML = `<p class="text-muted text-center" style="padding:24px;">No hay publicaciones creadas aún.</p>`;
      return;
    }

    postsAdminList.innerHTML = posts.map(p => {
      const dateStr = p.published_at ? new Date(p.published_at).toLocaleDateString("es-AR") : "";
      const thumb = p.image_url || "https://images.unsplash.com/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=150&q=80";
      const isPublished = Boolean(p.published);

      return `
        <div class="post-admin-card ${!isPublished ? 'post-draft-card' : ''}" id="post-item-${p.id}">
          <img src="${thumb}" alt="Foto" class="post-admin-thumb" onerror="this.src='https://images.unsplash.com/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=150&q=80'">
          <div class="post-admin-content">
            <div class="post-admin-meta">
              <span class="badge-cat">${p.category}</span>
              <span class="post-status-pill ${isPublished ? 'status-active' : 'status-draft'}">
                ${isPublished ? '🟢 Activo' : '⚪ Borrador / Inactivo'}
              </span>
              <span class="text-muted" style="font-size:0.75rem;">📅 ${dateStr}</span>
              ${p.author_name ? `<span class="text-muted" style="font-size:0.75rem;">✍️ ${p.author_name}</span>` : ''}
            </div>
            <div class="post-admin-title">${p.title}</div>
            <div class="post-admin-excerpt">${p.summary || p.content}</div>
          </div>
          <div class="post-admin-actions">
            <button class="btn btn-ghost btn-sm" onclick="window.editPostById(${p.id})" title="Editar publicación">
              ✏️ Editar
            </button>
            <button class="btn btn-danger btn-sm" onclick="window.deletePostById(${p.id})" title="Eliminar publicación">
              🗑️
            </button>
          </div>
        </div>
      `;
    }).join("");
  }

  // ==========================================
  // Image Live Preview
  // ==========================================
  const postImageFile = document.getElementById("post-image-file");
  const postImageUrl = document.getElementById("post-image-url");
  const postCategorySelect = document.getElementById("post-category");
  const imagePreviewContainer = document.getElementById("image-preview-container");
  const imgLivePreview = document.getElementById("img-live-preview");
  const previewCatTag = document.getElementById("preview-cat-tag");

  function updateImagePreview(src) {
    if (src) {
      imgLivePreview.src = src;
      imagePreviewContainer.style.display = "flex";
    } else {
      imagePreviewContainer.style.display = "none";
      imgLivePreview.src = "";
    }
  }

  if (postImageFile) {
    postImageFile.addEventListener("change", () => {
      if (postImageFile.files && postImageFile.files[0]) {
        const file = postImageFile.files[0];
        const reader = new FileReader();
        reader.onload = (e) => {
          updateImagePreview(e.target.result);
        };
        reader.readAsDataURL(file);
      } else if (!postImageUrl.value) {
        updateImagePreview(null);
      }
    });
  }

  if (postImageUrl) {
    postImageUrl.addEventListener("input", () => {
      const val = postImageUrl.value.trim();
      if (val) {
        updateImagePreview(val);
      } else if (!postImageFile.files || !postImageFile.files[0]) {
        updateImagePreview(null);
      }
    });
  }

  if (postCategorySelect && previewCatTag) {
    postCategorySelect.addEventListener("change", () => {
      previewCatTag.textContent = postCategorySelect.value || "General";
    });
  }

  // Editar Publicación
  window.editPostById = function(postId) {
    const post = localAdminPosts.find(p => p.id === postId);
    if (!post) return;

    postIdInput.value = post.id;
    document.getElementById("post-title").value = post.title || "";
    document.getElementById("post-category").value = post.category || "General";
    if (previewCatTag) previewCatTag.textContent = post.category || "General";
    postPublishedSelect.value = post.published ? "1" : "0";
    document.getElementById("post-image-url").value = post.image_url || "";
    document.getElementById("post-content").value = post.content || "";

    if (post.image_url) {
      updateImagePreview(post.image_url);
    } else {
      updateImagePreview(null);
    }

    postFormTitle.textContent = `✏️ Editando Publicación (#${post.id})`;
    btnCancelEdit.style.display = "inline-flex";
    document.getElementById("btn-publish-post").innerHTML = `<span>💾 Actualizar Publicación</span>`;

    // Scroll suave al formulario
    document.getElementById("post-form-card").scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Cancelar Edición
  btnCancelEdit.addEventListener("click", () => {
    resetPostForm();
  });

  function resetPostForm() {
    postCreateForm.reset();
    postIdInput.value = "";
    postFormTitle.textContent = "✍️ Crear Nueva Publicación";
    btnCancelEdit.style.display = "none";
    updateImagePreview(null);
    document.getElementById("btn-publish-post").innerHTML = `<span>🚀 Guardar Publicación</span>`;
  }


  postCreateForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btnPublish = document.getElementById("btn-publish-post");
    const editId = postIdInput.value;
    const isEditing = Boolean(editId);

    btnPublish.disabled = true;
    btnPublish.innerHTML = isEditing ? `<span>⏳ Guardando cambios...</span>` : `<span>⏳ Creando publicación...</span>`;

    const formData = new FormData(postCreateForm);

    try {
      const url = isEditing ? `/api/posts/${editId}` : "/api/posts";
      const res = await fetch(url, {
        method: "POST",
        body: formData
      });
      const data = await res.json();

      if (res.ok && data.success) {
        showToast(data.message || (isEditing ? "¡Publicación actualizada con éxito!" : "¡Publicación creada con éxito!"), "success");
        resetPostForm();
        loadPostsData();
      } else {
        showToast(data.error || "Error al procesar la publicación", "error");
      }
    } catch (err) {
      showToast("Error de conexión al guardar la publicación", "error");
    } finally {
      btnPublish.disabled = false;
      btnPublish.innerHTML = isEditing ? `<span>💾 Actualizar Publicación</span>` : `<span>🚀 Guardar Publicación</span>`;
    }
  });

  window.deletePostById = async function(postId) {
    if (!confirm("¿Seguro que deseás eliminar esta publicación?")) return;
    try {
      const res = await fetch(`/api/posts/${postId}`, { method: "DELETE" });
      if (res.ok) {
        showToast("Publicación eliminada", "warning");
        if (postIdInput.value == postId) {
          resetPostForm();
        }
        loadPostsData();
      } else {
        showToast("No se pudo eliminar la publicación", "error");
      }
    } catch (e) {
      showToast("Error de red al eliminar", "error");
    }
  };


  // ==========================================
  // Clupik Sync Management & Status
  // ==========================================
  function formatSyncTime(totalSeconds) {
    const m = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
    const s = String(totalSeconds % 60).padStart(2, '0');
    return `${m}:${s}`;
  }

  function startSyncUI(initialSeconds = 0, season = "2026", edition = "CLAUSURA") {
    isSyncing = true;

    if (btnTriggerSync) {
      btnTriggerSync.disabled = true;
      btnTriggerSync.classList.add("is-loading");
      btnTriggerSync.innerHTML = `
        <svg class="spinner-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" stroke-opacity="0.25"/>
          <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        </svg>
        <span>Sincronizando ${season} (${edition})...</span>
      `;
    }

    if (syncSeasonSelect) syncSeasonSelect.disabled = true;
    if (syncEditionSelect) syncEditionSelect.disabled = true;

    if (syncLoadingCard) syncLoadingCard.style.display = "block";
    if (syncTerminal) syncTerminal.style.display = "block";

    if (syncStatusIndicator) {
      syncStatusIndicator.innerHTML = `
        <span class="status-dot loading"></span>
        <span style="color:var(--accent-gold); font-weight:600;">Sincronizando torneos activos (${edition})...</span>
      `;
    }

    let seconds = initialSeconds;
    const initialFormatted = formatSyncTime(seconds);
    if (syncTimer) syncTimer.textContent = initialFormatted;
    if (syncLiveTimer) syncLiveTimer.textContent = `⏱ ${initialFormatted}`;

    clearInterval(syncTimerInterval);
    syncTimerInterval = setInterval(() => {
      seconds++;
      const formatted = formatSyncTime(seconds);
      if (syncTimer) syncTimer.textContent = formatted;
      if (syncLiveTimer) syncLiveTimer.textContent = `⏱ ${formatted}`;
    }, 1000);
  }

  function stopSyncUI(success = true) {
    isSyncing = false;
    clearInterval(syncTimerInterval);
    clearInterval(syncStatusPollTimer);

    if (btnTriggerSync) {
      btnTriggerSync.disabled = false;
      btnTriggerSync.classList.remove("is-loading");
      btnTriggerSync.innerHTML = `<span class="btn-icon">🔄</span><span>Sincronizar Datos Ahora</span>`;
    }

    if (syncSeasonSelect) syncSeasonSelect.disabled = false;
    if (syncEditionSelect) syncEditionSelect.disabled = false;

    if (syncLoadingCard) syncLoadingCard.style.display = "none";

    if (syncStatusIndicator) {
      if (success) {
        syncStatusIndicator.innerHTML = `
          <span class="status-dot online"></span>
          <span>Última sincronización exitosa: ${new Date().toLocaleTimeString()}</span>
        `;
      } else {
        syncStatusIndicator.innerHTML = `
          <span class="status-dot" style="background:#EF4444; box-shadow:0 0 8px #EF4444;"></span>
          <span style="color:#EF4444; font-weight:600;">Error en la sincronización</span>
        `;
      }
    }
  }

  function startStatusPolling() {
    clearInterval(syncStatusPollTimer);
    syncStatusPollTimer = setInterval(async () => {
      try {
        const res = await fetch("/api/sync-clupik/status");
        if (!res.ok) return;
        const data = await res.json();
        if (!data.running) {
          clearInterval(syncStatusPollTimer);
          if (data.last_success) {
            stopSyncUI(true);
            if (syncOutput && data.last_output) {
              syncOutput.textContent += "\n" + data.last_output;
            }
            showToast("¡Base de datos actualizada con éxito desde Clupik!", "success");
          } else {
            stopSyncUI(false);
            if (syncOutput && data.last_error) {
              syncOutput.textContent += "\n[ERROR]: " + data.last_error;
            }
            showToast("Ocurrió un error al sincronizar con Clupik", "error");
          }
        }
      } catch (err) {
        console.warn("Error en polling de sincronización:", err);
      }
    }, 2000);
  }

  async function checkBackendSyncStatus() {
    try {
      const res = await fetch("/api/sync-clupik/status");
      if (!res.ok) return;
      const data = await res.json();

      if (data.running) {
        if (!isSyncing) {
          startSyncUI(data.elapsed_seconds || 0, data.season || "2026", data.edition || "CLAUSURA");
          if (syncOutput && !syncOutput.textContent.trim()) {
            syncOutput.textContent = `[SISTEMA]: Sincronización en segundo plano detectada.\nTemporada: ${data.season || '2026'} | Edición: ${data.edition || 'CLAUSURA'}\nTiempo transcurrido: ${data.elapsed_seconds || 0}s\nAguardando finalización...\n`;
          }
          startStatusPolling();
        }
      } else if (isSyncing) {
        stopSyncUI(data.last_success !== false);
        if (data.last_output && syncOutput) {
          syncOutput.textContent += "\n" + data.last_output;
        }
      }
    } catch (e) {
      console.warn("No se pudo verificar el estado de sincronización:", e);
    }
  }

  if (btnTriggerSync) {
    btnTriggerSync.addEventListener("click", async () => {
      if (isSyncing || btnTriggerSync.disabled) return;

      const season = syncSeasonSelect ? syncSeasonSelect.value : "2026";
      const edition = syncEditionSelect ? syncEditionSelect.value : "CLAUSURA";

      startSyncUI(0, season, edition);
      syncOutput.textContent = `Iniciando proceso de sincronización con Clupik...\nTemporada: ${season} | Filtro: ${edition}\nExtrayendo torneos ${edition} y Competencias Nacionales...\n`;

      try {
        const res = await fetch("/api/sync-clupik", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ season, edition })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          showToast(data.message || `Sincronización (${edition}) iniciada en segundo plano`, "info");
          syncOutput.textContent += `[SISTEMA]: Tarea en segundo plano iniciada correctamente.\nTemporada: ${season} | Edición: ${edition}\nMonitoreando avance y conexión con Clupik...\n`;
          startStatusPolling();
        } else if (res.status === 409) {
          showToast(data.error || "Ya hay una sincronización en curso.", "warning");
          startStatusPolling();
        } else {
          stopSyncUI(false);
          syncOutput.textContent += "\n[ERROR]: " + (data.error || "Falló al iniciar la sincronización") + "\n" + (data.details || "");
          showToast(data.error || "Ocurrió un error al sincronizar con Clupik", "error");
        }
      } catch (err) {
        stopSyncUI(false);
        syncOutput.textContent += "\n[ERROR DE RED]: " + err.message;
        showToast("Error de conexión durante la sincronización", "error");
      }
    });
  }

  // Run Session check on load
  checkSession();
});
