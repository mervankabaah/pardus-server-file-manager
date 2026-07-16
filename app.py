import os
import shutil
import zipfile
import datetime
import urllib.parse
from functools import wraps
from flask import Flask, request, render_template_string, redirect, url_for, session, send_file, jsonify, make_response
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.secret_key = 'cok_guvenli_gizli_anahtar_degistirilebilir'
app.config['MAX_CONTENT_LENGTH'] = 1000 * 1024 * 1024 # 1GB Upload Limiti

# --- AYARLAR ---
BASE_DIR = '/var/www/html'
USERNAME = 'admin'
PASSWORD = 'admin'

def get_safe_path(req_path):
    base_dir = os.path.abspath(BASE_DIR)
    if not req_path:
        return base_dir
    target = os.path.abspath(os.path.join(base_dir, req_path.strip('/')))
    try:
        if os.path.commonpath([base_dir, target]) != base_dir:
            return base_dir
    except ValueError:
        return base_dir
    return target

def get_safe_upload_path(upload_root, filename):
    clean_name = filename.replace('\\', '/').strip('/')
    parts = [part for part in clean_name.split('/') if part and part != '.']
    if not parts or any(part == '..' for part in parts):
        raise ValueError('Gecersiz dosya yolu')

    upload_root = os.path.abspath(upload_root)
    target = os.path.abspath(os.path.join(upload_root, *parts))
    if os.path.commonpath([upload_root, target]) != upload_root:
        raise ValueError('Gecersiz dosya yolu')
    return target

@app.before_request
def check_lockout():
    lockout_cookie = request.cookies.get('lockout_time')
    if lockout_cookie:
        try:
            lockout_end = datetime.datetime.fromisoformat(lockout_cookie)
            if datetime.datetime.now() < lockout_end:
                return "5 kez hatalı şifre girdiniz. Tarayıcınız 5 saat boyunca bu sayfaya erişimi engellenmiştir.", 403
        except:
            pass

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- HTML/JS ŞABLONLARI ---
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Giriş Yap</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-dark text-light d-flex align-items-center justify-content-center" style="height: 100vh;">
    <div class="card bg-secondary text-light p-4 shadow" style="width: 350px;">
        <h3 class="text-center mb-4">File Manager</h3>
        {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
        <form method="POST">
            <div class="mb-3">
                <input type="text" name="username" class="form-control" placeholder="Kullanıcı Adı" required>
            </div>
            <div class="mb-3">
                <input type="password" name="password" class="form-control" placeholder="Şifre" required>
            </div>
            <button type="submit" class="btn btn-primary w-100">Giriş Yap</button>
        </form>
    </div>
</body>
</html>
"""

APP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>File Manager ({{ current_path }})</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .dropzone { border: 2px dashed #6c757d; border-radius: 10px; padding: 30px; text-align: center; cursor: pointer; transition: 0.3s; background: #2b3035; color:#fff;}
        .dropzone:hover, .dropzone.dragover { background: #343a40; border-color: #0d6efd; }
        .action-btn { margin-right: 5px; cursor:pointer;}
        .clickable-row { cursor: pointer; user-select: none; }
        
        /* SEÇİLEN SATIRLAR İÇİN NET GÖRSEL (Hover ve Bootstrap ezildi) */
        .table-dark tbody tr.selected-row td {
            background-color: #0d6efd !important;
            color: #ffffff !important;
        }
        .table-dark tbody tr.selected-row td a {
            color: #ffffff !important;
        }
        .table-dark tbody tr.selected-row:hover td {
            background-color: #0b5ed7 !important;
        }
    </style>
</head>
<body class="bg-dark text-light">
    <div class="container mt-4">
        
        <div class="d-flex justify-content-between mb-3 align-items-center">
            <h4 class="m-0"><i class="fas fa-folder-open text-warning"></i> {{ current_path }}</h4>
            <a href="/logout" class="btn btn-sm btn-danger">Çıkış Yap</a>
        </div>

        <!-- ÜST İŞLEM MENÜSÜ (TOPLU İŞLEMLER) -->
        <div class="card bg-secondary p-2 mb-3 d-flex flex-row flex-wrap gap-2 align-items-center">
            <button class="btn btn-sm btn-light fw-bold" onclick="createFolder()"><i class="fas fa-folder-plus"></i> Yeni Klasör</button>
            <div class="vr mx-1 text-light"></div>
            <button class="btn btn-sm btn-primary" id="topBtnCopy" disabled onclick="bulkAction('copy')"><i class="fas fa-copy"></i> Kopyala</button>
            <button class="btn btn-sm btn-warning" id="topBtnCut" disabled onclick="bulkAction('cut')"><i class="fas fa-cut"></i> Kes</button>
            <button class="btn btn-sm btn-info" id="topBtnPaste" style="display:none;" onclick="pasteItems()"><i class="fas fa-paste"></i> Yapıştır</button>
            <button class="btn btn-sm btn-danger" id="topBtnDelete" disabled onclick="bulkAction('delete')"><i class="fas fa-trash"></i> Sil</button>
            <div class="vr mx-1 text-light"></div>
            <!-- SEÇİLİLERİ ZİPLEME VE ZIPLERİ AÇMA BUTONLARI -->
            <button class="btn btn-sm btn-secondary" id="topBtnZip" disabled onclick="bulkAction('zip')"><i class="fas fa-file-archive"></i> Seçilileri Zip Yap</button>
            <button class="btn btn-sm btn-dark" id="topBtnUnzip" disabled onclick="bulkAction('unzip')"><i class="fas fa-box-open"></i> Seçili Ziplerden Çıkar</button>
            <div class="vr mx-1 text-light"></div>
            <button class="btn btn-sm btn-success" onclick="toggleUpload()"><i class="fas fa-cloud-upload-alt"></i> Yükle</button>
        </div>

        <!-- YÜKLEME KUTUSU -->
        <div id="dropzone" class="dropzone mb-4" style="display:none;" onclick="openFilePicker()">
            <i class="fas fa-cloud-upload-alt fa-3x mb-2 text-primary"></i>
            <h5>Dosya veya klasörleri buraya sürükleyin</h5>
            <div class="d-flex justify-content-center gap-2 flex-wrap mt-3" onclick="event.stopPropagation()">
                <button type="button" class="btn btn-sm btn-primary" onclick="openFilePicker()"><i class="fas fa-file-upload"></i> Dosya Seç</button>
                <button type="button" class="btn btn-sm btn-warning" onclick="openFolderPicker()"><i class="fas fa-folder-plus"></i> Klasör Seç</button>
            </div>
            <input type="file" id="fileInput" multiple style="display:none;" onchange="handleFiles(this.files); this.value = '';">
            <input type="file" id="folderInput" multiple webkitdirectory directory style="display:none;" onchange="handleFiles(this.files); this.value = '';">
        </div>

        <div id="uploadProgress" class="progress mb-4" style="display:none;">
            <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 100%">Yükleniyor...</div>
        </div>

        <table class="table table-dark table-hover align-middle" id="fileTable">
            <thead>
                <tr>
                    <th>Ad</th>
                    <th>Boyut</th>
                    <th class="text-end">İşlemler</th>
                </tr>
            </thead>
            <tbody>
                {% if current_path != '/' %}
                <tr>
                    <td colspan="3"><a href="?path={{ parent_path }}" class="text-light text-decoration-none"><i class="fas fa-level-up-alt"></i> Bir üst klasör...</a></td>
                </tr>
                {% endif %}
                {% for item in items %}
                <tr class="clickable-row file-row" data-path="{{ item.rel_path }}">
                    <td>
                        {% if item.is_dir %}
                            <a href="?path={{ item.rel_path }}" class="text-warning text-decoration-none folder-link"><i class="fas fa-folder"></i> {{ item.name }}</a>
                        {% else %}
                            <i class="fas fa-file text-secondary"></i> {{ item.name }}
                        {% endif %}
                    </td>
                    <td>{{ item.size }}</td>
                    <td class="text-end">
                        {% if not item.is_dir %}
                            <a href="/download?path={{ item.rel_path }}" class="btn btn-sm btn-success action-btn" title="İndir"><i class="fas fa-download"></i></a>
                        {% endif %}
                        <button class="btn btn-sm btn-secondary action-btn" onclick="renameItem('{{ item.rel_path }}', '{{ item.name }}')" title="Yeniden Adlandır"><i class="fas fa-edit"></i></button>
                        
                        <!-- SATIR İÇİ BUTONLAR GERİ GELDİ -->
                        <button class="btn btn-sm btn-primary action-btn" onclick="copyItem('{{ item.rel_path }}')" title="Kopyala"><i class="fas fa-copy"></i></button>
                        <button class="btn btn-sm btn-warning action-btn" onclick="cutItem('{{ item.rel_path }}')" title="Kes"><i class="fas fa-cut"></i></button>
                        
                        {% if item.name.endswith('.zip') %}
                            <button class="btn btn-sm btn-info action-btn" onclick="unzipItem('{{ item.rel_path }}')" title="Zipten Çıkar"><i class="fas fa-box-open"></i></button>
                        {% else %}
                            <button class="btn btn-sm btn-info action-btn" onclick="zipItem('{{ item.rel_path }}')" title="Ziple"><i class="fas fa-file-archive"></i></button>
                        {% endif %}
                        <button class="btn btn-sm btn-danger action-btn" onclick="deleteItem('{{ item.rel_path }}')" title="Sil"><i class="fas fa-trash"></i></button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <script>
        const CURRENT_PATH = "{{ current_path }}";
        let lastSelectedRowIndex = -1;

        // CTRL / SHIFT Tıklama Mantığı
        document.querySelectorAll('.file-row').forEach((row, index) => {
            row.addEventListener('click', function(e) {
                // Eğer buton, link veya ikonlara tıklandıysa satır seçimini tetikleme
                if(e.target.closest('button') || e.target.closest('a') || e.target.closest('i')) return;

                if(e.shiftKey && lastSelectedRowIndex !== -1) {
                    document.getSelection().removeAllRanges(); // Metin seçimini engelle
                    let rows = document.querySelectorAll('.file-row');
                    let start = Math.min(lastSelectedRowIndex, index);
                    let end = Math.max(lastSelectedRowIndex, index);
                    
                    if(!e.ctrlKey) rows.forEach(r => r.classList.remove('selected-row'));
                    
                    for(let i = start; i <= end; i++) {
                        rows[i].classList.add('selected-row');
                    }
                } else if(e.ctrlKey || e.metaKey) {
                    this.classList.toggle('selected-row');
                    lastSelectedRowIndex = index;
                } else {
                    document.querySelectorAll('.file-row').forEach(r => r.classList.remove('selected-row'));
                    this.classList.add('selected-row');
                    lastSelectedRowIndex = index;
                }
                updateTopButtons();
            });
        });

        // Seçili Dosya Yollarını Alır
        function getSelectedPaths() {
            let selected = [];
            document.querySelectorAll('.file-row.selected-row').forEach(row => {
                selected.push(row.getAttribute('data-path'));
            });
            return selected;
        }

        // Tepe Menü Butonlarının Aktiflik Durumu
        function updateTopButtons() {
            let count = getSelectedPaths().length;
            let disabled = count === 0;
            document.getElementById('topBtnCopy').disabled = disabled;
            document.getElementById('topBtnCut').disabled = disabled;
            document.getElementById('topBtnDelete').disabled = disabled;
            document.getElementById('topBtnZip').disabled = disabled;
            document.getElementById('topBtnUnzip').disabled = disabled;
        }

        // Toplu İşlemler (Kes, Kopyala, Sil, Zip, Unzip)
        function bulkAction(actionType) {
            let paths = getSelectedPaths();
            if(paths.length === 0) return;

            if(actionType === 'delete') {
                if(confirm(paths.length + " adet öğeyi silmek istediğinize emin misiniz?")) {
                    apiCall('delete_bulk', CURRENT_PATH, { paths: paths });
                }
            } else if(actionType === 'copy' || actionType === 'cut') {
                localStorage.setItem('fm_clip_paths', JSON.stringify(paths));
                localStorage.setItem('fm_clip_act', actionType);
                checkClipboard();
                document.querySelectorAll('.file-row.selected-row').forEach(r => r.classList.remove('selected-row'));
                updateTopButtons();
            } else if(actionType === 'zip') {
                apiCall('zip_bulk', CURRENT_PATH, { paths: paths });
            } else if(actionType === 'unzip') {
                apiCall('unzip_bulk', CURRENT_PATH, { paths: paths });
            }
        }

        // Satır içi Tekil İşlemleri Toplu Yapısıyla Çalıştırma
        function copyItem(path) {
            localStorage.setItem('fm_clip_paths', JSON.stringify([path]));
            localStorage.setItem('fm_clip_act', 'copy');
            checkClipboard();
        }

        function cutItem(path) {
            localStorage.setItem('fm_clip_paths', JSON.stringify([path]));
            localStorage.setItem('fm_clip_act', 'cut');
            checkClipboard();
        }

        function deleteItem(path) {
            if(confirm("Silmek istediğinize emin misiniz?")) {
                apiCall('delete_bulk', CURRENT_PATH, { paths: [path] });
            }
        }

        function pasteItems() {
            let pathsStr = localStorage.getItem('fm_clip_paths');
            let act = localStorage.getItem('fm_clip_act');
            if(pathsStr && act) {
                let paths = JSON.parse(pathsStr);
                apiCall('paste_bulk', CURRENT_PATH, { source_paths: paths, paste_action: act });
                if(act === 'cut') {
                    localStorage.removeItem('fm_clip_paths');
                    localStorage.removeItem('fm_clip_act');
                }
            }
        }

        function createFolder() {
            let name = prompt("Yeni klasör adı:");
            if(name) {
                apiCall('create_folder', CURRENT_PATH, { folder_name: name });
            }
        }

        function checkClipboard() {
            let clip = localStorage.getItem('fm_clip_paths');
            if(clip && JSON.parse(clip).length > 0) {
                let btn = document.getElementById('topBtnPaste');
                btn.style.display = 'inline-block';
                let act = localStorage.getItem('fm_clip_act');
                btn.innerHTML = `<i class="fas fa-paste"></i> Yapıştır (${JSON.parse(clip).length} öğe)`;
            }
        }

        // Yükleme Kutusunu Aç/Kapat Fonksiyonu
        function toggleUpload() {
            const dz = document.getElementById('dropzone');
            dz.style.display = dz.style.display === 'none' ? 'block' : 'none';
        }

        function openFilePicker() {
            document.getElementById('fileInput').click();
        }

        function openFolderPicker() {
            document.getElementById('folderInput').click();
        }

        // Sürükle ve Bırak Upload
        const dropzone = document.getElementById('dropzone');
        dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
        dropzone.addEventListener('drop', async (e) => {
            e.preventDefault(); dropzone.classList.remove('dragover');
            if(e.dataTransfer.items && e.dataTransfer.items.length > 0 && e.dataTransfer.items[0].webkitGetAsEntry) {
                try {
                    const droppedFiles = await collectDroppedFiles(e.dataTransfer.items);
                    handleFiles(droppedFiles);
                    return;
                } catch(err) {
                    alert('Yükleme hatası');
                    return;
                }
            }
            handleFiles(e.dataTransfer.files);
        });

        function readDirectoryEntries(reader) {
            return new Promise((resolve, reject) => {
                const entries = [];
                function readBatch() {
                    reader.readEntries((batch) => {
                        if(batch.length === 0) {
                            resolve(entries);
                            return;
                        }
                        entries.push(...batch);
                        readBatch();
                    }, reject);
                }
                readBatch();
            });
        }

        async function entryToFiles(entry, parentPath='') {
            if(entry.isFile) {
                return new Promise((resolve) => {
                    entry.file(
                        (file) => resolve([{ file: file, path: parentPath + file.name }]),
                        () => resolve([])
                    );
                });
            }
            if(entry.isDirectory) {
                const entries = await readDirectoryEntries(entry.createReader());
                const groups = await Promise.all(entries.map((child) => entryToFiles(child, parentPath + entry.name + '/')));
                return groups.reduce((all, group) => all.concat(group), []);
            }
            return [];
        }

        async function collectDroppedFiles(dataTransferItems) {
            const entries = [];
            for(const item of Array.from(dataTransferItems)) {
                if(item.kind !== 'file') continue;
                const entry = item.webkitGetAsEntry();
                if(entry) entries.push(entry);
            }
            const groups = await Promise.all(entries.map((entry) => entryToFiles(entry)));
            return groups.reduce((all, group) => all.concat(group), []);
        }

        function handleFiles(files) {
            const uploadItems = Array.from(files).map((item) => {
                if(item.file) return item;
                return {
                    file: item,
                    path: item.webkitRelativePath || item.relativePath || item.name
                };
            }).filter((item) => item.file);

            if(uploadItems.length === 0) return;
            let formData = new FormData();
            uploadItems.forEach((item) => {
                formData.append('files', item.file, item.path || item.file.name);
            });
            formData.append('path', CURRENT_PATH);

            document.getElementById('uploadProgress').style.display = 'flex';
            fetch('/upload', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => { if(data.status==='ok') location.reload(); else alert('Hata: '+data.error); })
            .catch(err => alert('Yükleme hatası'))
            .finally(() => document.getElementById('uploadProgress').style.display = 'none');
        }

        // Genel API Çağrı Fonksiyonu
        function apiCall(action, path, extra={}) {
            fetch('/api/action', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action, path: path, ...extra })
            })
            .then(res => res.json())
            .then(data => { if(data.status==='ok') location.reload(); else alert('Hata: '+data.error); });
        }

        function renameItem(path, oldName) {
            let newName = prompt("Yeni isim:", oldName);
            if(newName && newName !== oldName) apiCall('rename', path, { new_name: newName });
        }
        function zipItem(path) { apiCall('zip', path); }
        function unzipItem(path) { apiCall('unzip', path); }

        checkClipboard();
    </script>
</body>
</html>
"""

# --- ROUTELER ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == USERNAME and password == PASSWORD:
            session['logged_in'] = True
            session.pop('attempts', None)
            return redirect(url_for('index'))
        else:
            attempts = session.get('attempts', 0) + 1
            session['attempts'] = attempts
            if attempts >= 5:
                lockout_time = (datetime.datetime.now() + datetime.timedelta(hours=5)).isoformat()
                resp = make_response(render_template_string(LOGIN_HTML, error="5 kez hatalı girdiniz. Tarayıcınız 5 saat engellendi."))
                resp.set_cookie('lockout_time', lockout_time, max_age=5*3600)
                return resp
            return render_template_string(LOGIN_HTML, error=f"Hatalı şifre. Kalan deneme: {5 - attempts}")
    return render_template_string(LOGIN_HTML, error="")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    req_path = request.args.get('path', '')
    safe_path = get_safe_path(req_path)
    
    rel_path = os.path.relpath(safe_path, BASE_DIR)
    if rel_path == '.': rel_path = '/'
    else: rel_path = '/' + rel_path

    parent_path = '/' if rel_path == '/' else os.path.dirname(rel_path)

    items = []
    if os.path.exists(safe_path) and os.path.isdir(safe_path):
        for f in sorted(os.listdir(safe_path)):
            full_item_path = os.path.join(safe_path, f)
            is_dir = os.path.isdir(full_item_path)
            size = "-" if is_dir else f"{os.path.getsize(full_item_path) / 1024:.1f} KB"
            items.append({
                'name': f,
                'is_dir': is_dir,
                'size': size,
                'rel_path': os.path.relpath(full_item_path, BASE_DIR)
            })
    
    items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
    return render_template_string(APP_HTML, items=items, current_path=rel_path, parent_path=parent_path)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    req_path = request.form.get('path', '')
    safe_target = get_safe_path(req_path)
    files = request.files.getlist('files')
    try:
        for f in files:
            if f.filename:
                destination = get_safe_upload_path(safe_target, f.filename)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                f.save(destination)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/download')
@login_required
def download():
    req_path = request.args.get('path', '')
    safe_target = get_safe_path(req_path)
    if os.path.isfile(safe_target):
        return send_file(safe_target, as_attachment=True)
    return "Dosya bulunamadı", 404

@app.route('/api/action', methods=['POST'])
@login_required
def api_action():
    data = request.json
    action = data.get('action')
    req_path = data.get('path', '')
    target = get_safe_path(req_path)

    try:
        # Yeni Klasör Oluşturma
        if action == 'create_folder':
            folder_name = data.get('folder_name')
            new_dir = os.path.join(target, folder_name)
            os.makedirs(new_dir, exist_ok=True)

        # Çoklu / Tekil Silme
        elif action == 'delete_bulk':
            paths = data.get('paths', [])
            for p in paths:
                del_target = get_safe_path(p)
                if os.path.isdir(del_target): shutil.rmtree(del_target)
                else: os.remove(del_target)

        # Çoklu / Tekil Yapıştırma
        elif action == 'paste_bulk':
            sources = data.get('source_paths', [])
            paste_action = data.get('paste_action')
            for src_rel in sources:
                src = get_safe_path(src_rel)
                dest = os.path.join(target, os.path.basename(src))
                if not os.path.exists(src): continue
                
                if paste_action == 'copy':
                    if os.path.isdir(src): shutil.copytree(src, dest)
                    else: shutil.copy2(src, dest)
                elif paste_action == 'cut':
                    shutil.move(src, dest)

        # Çoklu Zipleme
        elif action == 'zip_bulk':
            paths = data.get('paths', [])
            for p in paths:
                t_path = get_safe_path(p)
                if not os.path.exists(t_path): continue
                base_name = os.path.basename(t_path)
                zip_target = t_path + '.zip'
                if os.path.isdir(t_path):
                    shutil.make_archive(t_path, 'zip', os.path.dirname(t_path), base_name)
                else:
                    with zipfile.ZipFile(zip_target, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        zipf.write(t_path, arcname=base_name)

        # Çoklu Zipten Çıkarma
        elif action == 'unzip_bulk':
            paths = data.get('paths', [])
            for p in paths:
                t_path = get_safe_path(p)
                if not os.path.exists(t_path) or not p.endswith('.zip'): continue
                extract_dir = os.path.dirname(t_path)
                with zipfile.ZipFile(t_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

        # Tekil Yeniden Adlandırma
        elif action == 'rename':
            new_name = data.get('new_name')
            new_target = os.path.join(os.path.dirname(target), new_name)
            os.rename(target, new_target)
                
        # Tekil Zipleme
        elif action == 'zip':
            base_name = os.path.basename(target)
            zip_target = target + '.zip'
            if os.path.isdir(target):
                shutil.make_archive(target, 'zip', os.path.dirname(target), base_name)
            else:
                with zipfile.ZipFile(zip_target, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(target, arcname=base_name)
                    
        # Tekil Zipten Çıkarma
        elif action == 'unzip':
            extract_dir = os.path.dirname(target)
            with zipfile.ZipFile(target, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5050)
