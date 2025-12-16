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
      <div class="delete" onclick="removeImage(${i})">×</div>
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
  // 只校验必填项：标题和价格
  if (!title) return alert('请填写商品标题');
  if (!price || price <= 0) return alert('请填写正确的价格');

  // 图片完全可选 → 如果没图就直接发布（后端会补默认图）
  if (images.length === 0) {
    if (!confirm('您没有上传任何图片，商品将使用默认封面图发布，确定要继续吗？')) {
      return;
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
  btn.onclick = null; ;

  try {
    const res = await fetch('/api/goods/publish', { method: 'POST', body: form });
    const d = await res.json();
    alert(d.msg);
    if (d.code === 200) {
      location.href = '/goods/' + d.goods_id;
    } else {
      btn.textContent = '发布商品';
      btn.onclick = publishGoods;
    }
  } catch (e) {
    alert('网络错误');
    btn.textContent = '发布商品';
    btn.style.opacity = '1';
  }
}