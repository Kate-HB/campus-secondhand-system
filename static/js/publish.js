// static/js/publish.js
let images = [];

const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const previewGrid = document.getElementById('preview-grid');

// 拖拽上传
uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.style.borderColor = '#ffce00'; });
uploadArea.addEventListener('dragleave', () => uploadArea.style.borderColor = '#ddd');
uploadArea.addEventListener('drop', e => {
  e.preventDefault();
  uploadArea.style.borderColor = '#ddd';
  handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', e => handleFiles(e.target.files));

function handleFiles(files) {
  [...files].forEach(file => {
    if (!file.type.startsWith('image/')) return;
    if (images.length >= 9) { alert('最多9张图片'); return; }
    const reader = new FileReader();
    reader.onload = e => {
      images.push({ file, url: e.target.result });
      renderPreview();
    };
    reader.readAsDataURL(file);
  });
}

function renderPreview() {
  previewGrid.innerHTML = '';
  images.forEach((img, i) => {
    const div = document.createElement('div');
    div.className = 'preview-item';
    div.innerHTML = `
      <img src="${img.url}">
      <div class="delete" onclick="images.splice(${i},1); renderPreview()">×</div>
    `;
    div.draggable = true;
    div.ondragstart = e => e.dataTransfer.setData('index', i);
    div.ondragover = e => e.preventDefault();
    div.ondrop = e => {
      e.preventDefault();
      const from = e.dataTransfer.getData('index');
      [images[i], images[from]] = [images[from], images[i]];
      renderPreview();
    };
    previewGrid.appendChild(div);
  });
}

async function publishGoods() {
  const title = document.getElementById('title').value.trim();
  const price = document.getElementById('price').value;
  // 修改这里：去掉 images.length === 0 的强制要求
  if (!title || !price) return alert('请填写标题、价格并上传图片');

  // 如果一张图片都没上传，给个友好提示，但不阻止发布
  if (images.length === 0) {
    if (!confirm('您还没有上传商品图片，确定要发布吗？\n（无图商品吸引力会降低哦~）')) {
      return;  // 用户取消，就不继续发布
    }
  }

  const form = new FormData();
  form.append('title', title);
  form.append('price', price);
  form.append('cate_id', document.getElementById('cate_id').value);
  form.append('degree', document.getElementById('degree').value);
  form.append('description', document.getElementById('description').value);
  form.append('is_batch', document.getElementById('batch-mode')?.checked ? 1 : 0);
  images.forEach((img, i) => form.append('images', img.file));

  const btn = document.querySelector('.btn-publish');
  btn.textContent = '发布中...';
  btn.style.opacity = '0.7';

  try {
    const res = await fetch('/api/goods/publish', { method: 'POST', body: form });
    const d = await res.json();
    alert(d.msg);
    if (d.code === 200) location.href = '/goods/' + d.goods_id;
  } catch (e) {
    alert('网络错误');
    btn.textContent = '发布商品';
    btn.style.opacity = '1';
  }
}