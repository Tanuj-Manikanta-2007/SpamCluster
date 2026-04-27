function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

function csrfHeaders() {
  const token = getCookie('csrftoken');
  return token ? { 'X-CSRFToken': token } : {};
}

function getRoomCode() {
  const params = new URLSearchParams(window.location.search);
  return params.get('code');
}

const ROOMS_STORAGE_KEY = 'snap_rooms_v1';

const FAVORITE_PEOPLE_KEY_PREFIX = 'snap_favorite_people_v1:';

function favoritesStorageKey(roomCode) {
  return `${FAVORITE_PEOPLE_KEY_PREFIX}${(roomCode || '').trim()}`;
}

function getFavoritePeople(roomCode) {
  const code = (roomCode || '').trim();
  if (!code) return new Set();
  try {
    const raw = localStorage.getItem(favoritesStorageKey(code));
    const parsed = raw ? JSON.parse(raw) : [];
    const labels = Array.isArray(parsed) ? parsed.map((x) => String(x)) : [];
    return new Set(labels);
  } catch {
    return new Set();
  }
}

function setFavoritePeople(roomCode, favoritesSet) {
  const code = (roomCode || '').trim();
  if (!code) return;
  try {
    const arr = Array.from(favoritesSet || []).map((x) => String(x));
    localStorage.setItem(favoritesStorageKey(code), JSON.stringify(arr));
  } catch {
    // ignore
  }
}

function isPersonFavorite(roomCode, label) {
  return getFavoritePeople(roomCode).has(String(label));
}

function setPersonFavorite(roomCode, label, isFav) {
  const favorites = getFavoritePeople(roomCode);
  const key = String(label);
  if (isFav) favorites.add(key);
  else favorites.delete(key);
  setFavoritePeople(roomCode, favorites);
}

function getStoredRooms() {
  try {
    const raw = localStorage.getItem(ROOMS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string' && x.trim()) : [];
  } catch {
    return [];
  }
}

function setStoredRooms(rooms) {
  try {
    localStorage.setItem(ROOMS_STORAGE_KEY, JSON.stringify(rooms));
  } catch {
    // ignore
  }
}

function addStoredRoom(code) {
  const c = (code || '').trim();
  if (!c) return;
  const rooms = getStoredRooms().filter((x) => x !== c);
  rooms.unshift(c);
  setStoredRooms(rooms.slice(0, 30));
}

function removeStoredRoom(code) {
  const c = (code || '').trim();
  if (!c) return;
  const rooms = getStoredRooms().filter((x) => x !== c);
  setStoredRooms(rooms);
}

function renderStoredRooms() {
  const list = document.getElementById('yourRoomsList');
  const empty = document.getElementById('yourRoomsEmpty');
  if (!list) return;

  const rooms = getStoredRooms();
  list.innerHTML = '';

  if (empty) empty.style.display = rooms.length ? 'none' : 'block';
  if (!rooms.length) return;

  for (const code of rooms) {
    const card = document.createElement('div');
    card.className = 'card snap-room-card';

    const title = document.createElement('h2');
    const titleLabel = document.createElement('span');
    titleLabel.textContent = 'Room ';
    const codeEl = document.createElement('span');
    codeEl.className = 'snap-room-code';
    codeEl.textContent = code;
    title.appendChild(titleLabel);
    title.appendChild(codeEl);

    const actions = document.createElement('div');
    actions.className = 'snap-room-actions';

    const openBtn = document.createElement('button');
    openBtn.textContent = 'Open';
    openBtn.addEventListener('click', () => {
      window.location.href = `/room/?code=${encodeURIComponent(code)}`;
    });

    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = 'Delete';
    deleteBtn.className = 'snap-btn-danger';
    deleteBtn.addEventListener('click', async () => {
      await deleteRoom(code);
    });

    actions.appendChild(openBtn);
    actions.appendChild(deleteBtn);

    card.appendChild(title);
    card.appendChild(actions);
    list.appendChild(card);
  }
}

function initHomePage() {
  renderStoredRooms();
}

function initRoomPage() {
  const code = getRoomCode();
  const el = document.getElementById('roomCodeDisplay');
  if (el) el.textContent = code ? code : '';

  if (code) {
    addStoredRoom(code);
  }

  const imagesInput = document.getElementById('imagesInput');
  if (imagesInput && !imagesInput.dataset.bound) {
    imagesInput.dataset.bound = '1';
    imagesInput.addEventListener('change', async () => {
      if (imagesInput.files && imagesInput.files.length) {
        await uploadImages();
      }
    });
  }

  const zipInput = document.getElementById('zipInput');
  if (zipInput && !zipInput.dataset.bound) {
    zipInput.dataset.bound = '1';
    zipInput.addEventListener('change', async () => {
      if (zipInput.files && zipInput.files.length) {
        await uploadZip();
      }
    });
  }

  const searchInput = document.getElementById('searchInput');
  if (searchInput && !searchInput.dataset.bound) {
    searchInput.dataset.bound = '1';
    searchInput.addEventListener('change', async () => {
      if (searchInput.files && searchInput.files.length) {
        await searchMeInRoom();
      }
    });
  }

  bindSidebarTabs();

  if (code) {
    loadImages();
  } else {
    alert('Missing room code in URL. Use /room/?code=XXXX');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('yourRoomsList')) {
    initHomePage();
  }
});

function triggerImagePicker() {
  const input = document.getElementById('imagesInput');
  if (input) input.click();
}

function triggerZipPicker() {
  const input = document.getElementById('zipInput');
  if (input) input.click();
}

function triggerSearchPicker() {
  const input = document.getElementById('searchInput');
  if (input) input.click();
}

function bindSidebarTabs() {
  const items = Array.from(document.querySelectorAll('.snap-side-item'));
  if (!items.length) return;
  if (items.some((x) => x.dataset.bound === '1')) return;

  for (const item of items) {
    item.dataset.bound = '1';
    item.addEventListener('click', () => {
      for (const it of items) it.classList.remove('is-active');
      item.classList.add('is-active');
      const label = (item.textContent || '').trim().toLowerCase();
      if (label === 'people') {
        setView('people');
      } else if (label === 'favorites' || label === 'favourites') {
        setView('favorites');
      } else {
        // Default: All Photos
        setView('photos');
      }
    });
  }
}

function setView(view) {
  const gallery = document.getElementById('gallery');
  const peopleView = document.getElementById('peopleView');
  const favoritesView = document.getElementById('favoritesView');
  const uploadFab = document.querySelector('.snap-upload-fab');
  const uploadResults = document.getElementById('uploadResults');

  if (view === 'people') {
    if (gallery) gallery.style.display = 'none';
    if (peopleView) peopleView.hidden = false;
    if (favoritesView) favoritesView.hidden = true;
    if (uploadFab) uploadFab.style.display = 'none';
    if (uploadResults) uploadResults.hidden = true;
    return;
  }

  if (view === 'favorites') {
    if (gallery) gallery.style.display = 'none';
    if (peopleView) peopleView.hidden = true;
    if (favoritesView) favoritesView.hidden = false;
    if (uploadFab) uploadFab.style.display = 'none';
    if (uploadResults) uploadResults.hidden = true;
    renderFavorites();
    return;
  }

  // photos
  if (gallery) gallery.style.display = '';
  if (peopleView) peopleView.hidden = true;
  if (favoritesView) favoritesView.hidden = true;
  if (uploadFab) uploadFab.style.display = '';
  // uploadResults visibility is managed by renderUploadResults
}

async function fetchClusters(roomCode) {
  const code = (roomCode || '').trim();
  if (!code) throw new Error('Missing room code');

  const res = await fetch(`/cluster/?room_code=${encodeURIComponent(code)}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Cluster failed (${res.status})`);
  }

  const clusters = data && data.clusters && typeof data.clusters === 'object' ? data.clusters : {};
  const labels = Object.keys(clusters).sort((a, b) => Number(a) - Number(b));
  return { clusters, labels };
}

function renderPeopleClusters(containerEl, roomCode, clusters, labels, options) {
  if (!containerEl) return;
  const opts = options || {};

  containerEl.innerHTML = '';
  for (const label of labels) {
    const items = Array.isArray(clusters[label]) ? clusters[label] : [];
    if (!items.length) continue;

    const wrap = document.createElement('div');
    wrap.className = 'snap-results';

    const head = document.createElement('div');
    head.className = 'snap-results-head';

    const left = document.createElement('div');
    left.className = 'snap-person-head-left';

    const title = document.createElement('div');
    title.className = 'snap-results-title';
    const personNumber = Number(label) + 1;
    title.textContent = `Person ${personNumber}`;
    left.appendChild(title);

    if (opts.showFavoriteToggle) {
      const favWrap = document.createElement('label');
      favWrap.className = 'snap-fav-toggle';

      const fav = document.createElement('input');
      fav.type = 'checkbox';
      fav.checked = isPersonFavorite(roomCode, label);
      fav.ariaLabel = `Favourite person ${personNumber}`;

      fav.addEventListener('click', (e) => e.stopPropagation());
      fav.addEventListener('change', () => {
        setPersonFavorite(roomCode, label, fav.checked);
        if (typeof opts.onFavoriteChanged === 'function') {
          opts.onFavoriteChanged();
        }
      });

      const favText = document.createElement('span');
      favText.textContent = 'Favourite';

      favWrap.appendChild(fav);
      favWrap.appendChild(favText);
      left.appendChild(favWrap);
    }

    const meta = document.createElement('div');
    meta.className = 'snap-results-meta';
    meta.textContent = `${items.length} photo(s)`;

    head.appendChild(left);
    head.appendChild(meta);

    const grid = document.createElement('div');
    grid.className = 'snap-results-grid';

    for (const item of items) {
      if (!item || !item.url) continue;
      const id = item.id;

      const card = document.createElement('div');
      card.className = 'snap-result-card';

      const checkboxWrap = document.createElement('div');
      checkboxWrap.className = 'snap-check';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = selectedImageIds.has(id);
      checkbox.ariaLabel = 'Select image';

      checkbox.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleSelected(id);
        card.classList.toggle('is-selected', selectedImageIds.has(id));
      });

      checkboxWrap.appendChild(checkbox);

      const img = document.createElement('img');
      img.src = item.url;
      img.alt = 'person';
      img.loading = 'lazy';

      card.addEventListener('click', () => {
        toggleSelected(id);
        checkbox.checked = selectedImageIds.has(id);
        card.classList.toggle('is-selected', selectedImageIds.has(id));
      });

      if (selectedImageIds.has(id)) {
        card.classList.add('is-selected');
      }

      card.appendChild(checkboxWrap);
      card.appendChild(img);
      grid.appendChild(card);
    }

    wrap.appendChild(head);
    wrap.appendChild(grid);
    containerEl.appendChild(wrap);
  }
}

async function renderFavorites() {
  const code = getRoomCode();
  if (!code) return;

  const metaEl = document.getElementById('favoritesMeta');
  const clustersEl = document.getElementById('favoritesClusters');
  if (metaEl) metaEl.textContent = 'Loading...';
  if (clustersEl) clustersEl.innerHTML = '';

  const favorites = getFavoritePeople(code);
  if (!favorites.size) {
    if (metaEl) metaEl.textContent = 'No favorites yet. Mark people as Favourite in People tab.';
    return;
  }

  try {
    const { clusters, labels } = await fetchClusters(code);
    const favLabels = labels.filter((l) => favorites.has(String(l)));

    if (metaEl) {
      metaEl.textContent = favLabels.length
        ? `${favLabels.length} favourite person(s)`
        : 'No favourite people found in current clusters.';
    }

    renderPeopleClusters(clustersEl, code, clusters, favLabels, {
      showFavoriteToggle: true,
      onFavoriteChanged: () => renderFavorites(),
    });
  } catch (err) {
    if (metaEl) metaEl.textContent = '';
    alert(err && err.message ? err.message : 'Failed to load favourites');
  }
}

async function clusterPeople() {
  const code = getRoomCode();
  if (!code) {
    alert('Missing room code');
    return;
  }

  const metaEl = document.getElementById('peopleMeta');
  const clustersEl = document.getElementById('peopleClusters');
  if (metaEl) metaEl.textContent = 'Clustering...';
  if (clustersEl) clustersEl.innerHTML = '';

  try {
    const { clusters, labels } = await fetchClusters(code);
    if (metaEl) metaEl.textContent = labels.length ? `${labels.length} person cluster(s)` : 'No clusters found';
    renderPeopleClusters(clustersEl, code, clusters, labels, {
      showFavoriteToggle: true,
    });
  } catch (err) {
    if (metaEl) metaEl.textContent = '';
    alert(err && err.message ? err.message : 'Cluster failed');
  }
}

async function searchMeInRoom() {
  const code = getRoomCode();
  if (!code) {
    alert('Missing room code');
    return;
  }

  const input = document.getElementById('searchInput');
  const file = input && input.files && input.files[0] ? input.files[0] : null;
  if (!file) {
    alert('Select one image');
    return;
  }

  const resWrap = document.getElementById('searchResults');
  const metaEl = document.getElementById('searchResultsMeta');
  const grid = document.getElementById('searchResultsGrid');
  if (resWrap) resWrap.hidden = false;
  if (metaEl) metaEl.textContent = 'Searching...';
  if (grid) grid.innerHTML = '';

  const fd = new FormData();
  fd.append('room_code', code);
  fd.append('image', file);

  const res = await fetch('/search-person/', {
    method: 'POST',
    headers: {
      ...csrfHeaders(),
    },
    body: fd,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (metaEl) metaEl.textContent = '';
    alert(data.error || `Search failed (${res.status})`);
    return;
  }

  const matches = Array.isArray(data.matches) ? data.matches : [];
  if (metaEl) metaEl.textContent = `${matches.length} match(es) • threshold ${data.threshold}`;
  if (!grid) return;

  grid.innerHTML = '';
  for (const m of matches) {
    if (!m || !m.url) continue;

    const card = document.createElement('div');
    card.className = 'snap-result-card';

    const checkboxWrap = document.createElement('div');
    checkboxWrap.className = 'snap-check';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selectedImageIds.has(m.id);
    checkbox.ariaLabel = 'Select image';

    checkbox.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleSelected(m.id);
      card.classList.toggle('is-selected', selectedImageIds.has(m.id));
    });

    checkboxWrap.appendChild(checkbox);

    const img = document.createElement('img');
    img.src = m.url;
    img.alt = 'match';
    img.loading = 'lazy';

    const meta = document.createElement('div');
    meta.className = 'snap-result-meta';
    meta.textContent = `Score: ${m.score}`;

    card.addEventListener('click', () => {
      toggleSelected(m.id);
      card.classList.toggle('is-selected', selectedImageIds.has(m.id));
      checkbox.checked = selectedImageIds.has(m.id);
    });

    if (selectedImageIds.has(m.id)) {
      card.classList.add('is-selected');
    }

    card.appendChild(checkboxWrap);
    card.appendChild(img);
    card.appendChild(meta);
    grid.appendChild(card);
  }

  if (input) input.value = '';
}

let selectedImageIds = new Set();

function getSelectedIds() {
  return Array.from(selectedImageIds);
}

function setSelectionCount() {
  const countEl = document.getElementById('selectedCount');
  const deleteBtn = document.getElementById('deleteSelectedBtn');
  const downloadBtn = document.getElementById('downloadSelectedBtn');
  const peopleDownloadBtn = document.getElementById('peopleDownloadSelectedBtn');
  const peopleDeleteBtn = document.getElementById('peopleDeleteSelectedBtn');
  const n = selectedImageIds.size;

  if (countEl) countEl.textContent = String(n);
  if (deleteBtn) deleteBtn.disabled = n === 0;
  if (downloadBtn) downloadBtn.disabled = n === 0;
  if (peopleDownloadBtn) peopleDownloadBtn.disabled = n === 0;
  if (peopleDeleteBtn) peopleDeleteBtn.disabled = n === 0;
}

function toggleSelected(id) {
  if (selectedImageIds.has(id)) selectedImageIds.delete(id);
  else selectedImageIds.add(id);
  setSelectionCount();
}

function clearSelection() {
  selectedImageIds = new Set();
  setSelectionCount();
}

function renderUploadResults(payload) {
  const wrap = document.getElementById('uploadResults');
  const metaEl = document.getElementById('uploadResultsMeta');
  const grid = document.getElementById('uploadResultsGrid');
  if (!wrap || !grid) return;

  const processed = payload && Array.isArray(payload.processed) ? payload.processed : [];
  if (!processed.length) {
    wrap.hidden = true;
    grid.innerHTML = '';
    if (metaEl) metaEl.textContent = '';
    return;
  }

  const totalFaces = typeof payload.total_faces === 'number'
    ? payload.total_faces
    : processed.reduce((acc, x) => acc + (x && x.face_count ? x.face_count : 0), 0);

  wrap.hidden = false;
  if (metaEl) metaEl.textContent = `${processed.length} image(s) • ${totalFaces} face(s)`;
  grid.innerHTML = '';

  for (const item of processed) {
    if (!item || !item.url) continue;

    const card = document.createElement('div');
    card.className = 'snap-result-card';

    const img = document.createElement('img');
    img.src = item.url;
    img.alt = 'uploaded';
    img.loading = 'lazy';

    const meta = document.createElement('div');
    meta.className = 'snap-result-meta';
    const nFaces = item.face_count || 0;
    meta.textContent = `Faces: ${nFaces}`;

    card.appendChild(img);
    card.appendChild(meta);
    grid.appendChild(card);
  }
}

async function createRoom() {
  const nameEl = document.getElementById('createName');
  const payload = { name: nameEl ? nameEl.value : '' };

  const res = await fetch('/create_room/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify(payload),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || `Create failed (${res.status})`);
    return;
  }

  const code = data.room_code;
  if (!code) {
    alert('Create succeeded but room_code missing in response.');
    return;
  }

  addStoredRoom(code);
  renderStoredRooms();
  alert(`Room created! Code: ${code}`);

  window.location.href = `/room/?code=${encodeURIComponent(code)}`;
}

async function joinRoom() {
  const codeEl = document.getElementById('joinCode');
  const code = codeEl ? codeEl.value.trim() : '';
  if (!code) {
    alert('Enter a room code');
    return;
  }

  const res = await fetch('/join_room/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ code }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || `Join failed (${res.status})`);
    return;
  }

  addStoredRoom(code);
  renderStoredRooms();
  alert(`Joined room! Code: ${code}`);

  window.location.href = `/room/?code=${encodeURIComponent(code)}`;
}

async function deleteRoom(codeOverride) {
  const code = (codeOverride || getRoomCode() || '').trim();
  if (!code) {
    alert('Missing room code');
    return;
  }

  const ok = confirm(`Delete room ${code}? This will delete all images in the room.`);
  if (!ok) return;

  const res = await fetch('/delete-room/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ room_code: code }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || `Delete failed (${res.status})`);
    return;
  }

  removeStoredRoom(code);
  renderStoredRooms();

  // If called from the room page, go back home after deletion.
  if (getRoomCode() === code) {
    window.location.href = '/';
  }
}

async function loadImages() {
  const code = getRoomCode();
  if (!code) return;

  const res = await fetch(`/room-images/${encodeURIComponent(code)}/`);
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    alert(data.error || `Failed to load images (${res.status})`);
    return;
  }

  const gallery = document.getElementById('gallery');
  if (!gallery) return;

  gallery.innerHTML = '';
  const rawImages = Array.isArray(data.images) ? data.images : [];
  // Support both: ["url", ...] and [{id, url}, ...]
  const images = rawImages.map((x) => {
    if (typeof x === 'string') return { id: x, url: x };
    return x;
  });

  // Remove any selected IDs that no longer exist
  const idsInRoom = new Set(images.map((x) => x && x.id));
  selectedImageIds = new Set(Array.from(selectedImageIds).filter((id) => idsInRoom.has(id)));
  setSelectionCount();

  for (const item of images) {
    if (!item || !item.url) continue;

    const card = document.createElement('div');
    card.className = 'snap-card';
    card.dataset.imageId = String(item.id);

    const checkboxWrap = document.createElement('div');
    checkboxWrap.className = 'snap-check';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selectedImageIds.has(item.id);
    checkbox.ariaLabel = 'Select image';

    checkbox.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleSelected(item.id);
      card.classList.toggle('is-selected', selectedImageIds.has(item.id));
    });

    checkboxWrap.appendChild(checkbox);

    const img = document.createElement('img');
    img.src = item.url;
    img.alt = 'uploaded';
    img.loading = 'lazy';

    const overlay = document.createElement('div');
    overlay.className = 'snap-overlay';
    const fc = item.face_count || 0;
    overlay.textContent = `Room: ${code} • Faces: ${fc}`;

    card.addEventListener('click', () => {
      toggleSelected(item.id);
      checkbox.checked = selectedImageIds.has(item.id);
      card.classList.toggle('is-selected', selectedImageIds.has(item.id));
    });

    if (selectedImageIds.has(item.id)) {
      card.classList.add('is-selected');
    }

    card.appendChild(checkboxWrap);
    card.appendChild(img);
    card.appendChild(overlay);
    gallery.appendChild(card);
  }
}

async function deleteSelected() {
  const code = getRoomCode();
  const ids = getSelectedIds();
  if (!code || !ids.length) return;

  const ok = confirm(`Delete ${ids.length} selected image(s)?`);
  if (!ok) return;

  const res = await fetch('/delete-images/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ room_code: code, image_ids: ids }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || `Delete failed (${res.status})`);
    return;
  }

  clearSelection();
  await loadImages();

  // If the user is currently on the People view, refresh clusters.
  const peopleView = document.getElementById('peopleView');
  if (peopleView && peopleView.hidden === false) {
    await clusterPeople();
  }
}

async function downloadSelected() {
  const code = getRoomCode();
  const ids = getSelectedIds();
  if (!code || !ids.length) return;

  const res = await fetch('/download-images/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...csrfHeaders(),
    },
    body: JSON.stringify({ room_code: code, image_ids: ids }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    alert(data.error || `Download failed (${res.status})`);
    return;
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `room_${code}_images.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function uploadImages() {
  const code = getRoomCode();
  if (!code) {
    alert('Missing room code');
    return;
  }

  const input = document.getElementById('imagesInput');
  const files = input && input.files ? Array.from(input.files) : [];
  if (!files.length) {
    alert('Select one or more images');
    return;
  }

  const fd = new FormData();
  fd.append('room_code', code);
  for (const file of files) {
    fd.append('images', file);
  }

  const res = await fetch('/upload-images/', {
    method: 'POST',
    headers: {
      ...csrfHeaders(),
    },
    body: fd,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || `Upload failed (${res.status})`);
    return;
  }

  renderUploadResults(data);
  await loadImages();
  if (input) input.value = '';
}

async function uploadZip() {
  const code = getRoomCode();
  if (!code) {
    alert('Missing room code');
    return;
  }

  const input = document.getElementById('zipInput');
  const file = input && input.files && input.files[0] ? input.files[0] : null;
  if (!file) {
    alert('Select a zip file');
    return;
  }

  const fd = new FormData();
  fd.append('room_code', code);
  fd.append('zip_file', file);

  const res = await fetch('/upload-zip/', {
    method: 'POST',
    headers: {
      ...csrfHeaders(),
    },
    body: fd,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || `ZIP upload failed (${res.status})`);
    return;
  }

  renderUploadResults(data);
  await loadImages();
  if (input) input.value = '';
}

function copyLink() {
  const code = getRoomCode();
  const url = window.location.origin + '/room/?code=' + code;

  navigator.clipboard.writeText(url);
  alert('Room link copied!');
}
