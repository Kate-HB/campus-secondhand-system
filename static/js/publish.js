// static/js/publish.js

let newImages = [];  // 只存放本次新上传的图片文件 { file, url }

// 页面加载时，如果是编辑模式，已有图片会直接渲染在 preview-grid 中（HTML 已注入）
const previewGrid = document.getElementById('preview-grid');
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');

// ========== 上传相关 ==========
uploadArea.addEventListener('click', () => fileInput.click());

uploadArea.addEventListener('dragover', e => {
  e.preventDefault();
  uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
  uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', e => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', e => handleFiles(e.target.files));

function handleFiles(files) {
  [...files].filter(file => file.type.startsWith('image/')).forEach(file => {
    if (newImages.length + getExistingImageCount() >= 9) {
      alert('最多只能上传9张图片');
      return;
    }
    const reader = new FileReader();
    reader.onload = ev => {
      newImages.push({ file, url: ev.target.result, isNew: true });
      renderPreview();
    };
    reader.readAsDataURL(file);
  });
}

// ========== 预览与操作 ==========
function getExistingImageCount() {
  // 已有图片是通过 HTML 注入的，带有 data-url 属性
  return previewGrid.querySelectorAll('.preview-item[data-url]').length;
}

function renderPreview() {
  // 先清空（保留已有图片的 DOM，因为它们是服务器图片）
  const existingItems = [...previewGrid.querySelectorAll('.preview-item[data-url]')];
  const newItemsHTML = newImages.map((img, i) => `
    <div class="preview-item" data-index="${i}">
      <img src="${img.url}">
      <div class="delete" onclick="removeNewImage(${i})">×</div>
    </div>
  `).join('');

  // 如果有新图片，追加到已有图片后面
  if (newImages.length > 0) {
    // 先放已有图片（保持原有顺序）
    previewGrid.innerHTML = '';
    existingItems.forEach(item => previewGrid.appendChild(item));
    // 再追加新图片的 HTML
    previewGrid.insertAdjacentHTML('beforeend', newItemsHTML);
  } else {
    // 没有新图片，只保留已有
    if (existingItems.length === 0) {
      previewGrid.innerHTML = '';
    }
  }

  // 重新绑定拖拽（支持新旧混合排序）
  bindDragEvents();
}

function bindDragEvents() {
  const items = previewGrid.querySelectorAll('.preview-item');
  items.forEach((item, index) => {
    item.draggable = true;
    item.ondragstart = e => {
      e.dataTransfer.setData('text/plain', index);
      e.dataTransfer.setData('item-type', item.hasAttribute('data-url') ? 'existing' : 'new');
    };
    item.ondragover = e => e.preventDefault();
    item.ondrop = e => {
      e.preventDefault();
      const fromIndex = parseInt(e.dataTransfer.getData('text/plain'));
      const fromItem = items[fromIndex];
      const toItem = item;

      // 交换 DOM 位置
      if (fromIndex < index) {
        previewGrid.insertBefore(fromItem, toItem.nextSibling);
      } else {
        previewGrid.insertBefore(fromItem, toItem);
      }

      // 如果是新图片，还要同步 newImages 数组顺序
      if (!fromItem.hasAttribute('data-url') && !toItem.hasAttribute('data-url')) {
        const fromNewIndex = parseInt(fromItem.dataset.index);
        const toNewIndex = parseInt(toItem.dataset.index);
        [newImages[fromNewIndex], newImages[toNewIndex]] = [newImages[toNewIndex], newImages[fromNewIndex]];
        // 更新 data-index
        renderPreview(); // 简单起见直接重新渲染
      }
    };
  });
}

// 删除已有图片（仅移除 DOM，不发请求，后端会根据最终上传情况覆盖）
function removeExistingImage(btn) {
  btn.parentElement.remove();
}

// 删除新上传的图片
function removeNewImage(index) {
  newImages.splice(index, 1);
  renderPreview();
}

// ========== 保存商品（发布 / 编辑）==========
async function saveGoods() {
  const title = document.getElementById('title').value.trim();
  const price = document.getElementById('price').value;

  if (!title) return alert('请填写商品标题');
  if (!price || price <= 0) return alert('请填写正确的价格');

  const totalImages = getExistingImageCount() + newImages.length;
  if (totalImages === 0) {
    if (!confirm('您没有上传任何图片，商品将使用默认封面图，确定继续吗？')) {
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

  // 只上传本次新选择的图片（编辑时已有图片会被后端覆盖逻辑处理）
  newImages.forEach(img => form.append('images', img.file));

  // 判断是编辑还是新建
  const isEdit = !!document.getElementById('goods_id');
  const url = isEdit ? '/api/goods/update' : '/api/goods/publish';

  if (isEdit) {
    form.append('goods_id', document.getElementById('goods_id').value);
  }

  const btn = document.querySelector('.btn-publish');
  const originalText = btn.textContent;
  btn.textContent = '保存中...';
  btn.onclick = null;

  try {
    const res = await fetch(url, {
      method: 'POST',
      body: form
    });
    const data = await res.json();

    alert(data.msg || (data.code === 200 ? '操作成功！' : '操作失败'));

    if (data.code === 200) {
      // 成功后跳转到商品详情页
      location.href = '/goods/' + (data.goods_id || document.getElementById('goods_id').value);
    } else {
      btn.textContent = originalText;
      btn.onclick = saveGoods;
    }
  } catch (err) {
    console.error(err);
    alert('网络错误，请重试');
    btn.textContent = originalText;
    btn.onclick = saveGoods;
  }
}

// 页面加载完成后初始化（绑定已有图片的删除事件 + 拖拽）
document.addEventListener('DOMContentLoaded', () => {
  // 为 HTML 中注入的已有图片绑定删除事件
  document.querySelectorAll('.preview-item[data-url] .delete').forEach(btn => {
    btn.onclick = () => removeExistingImage(btn);
  });
  bindDragEvents(); // 绑定拖拽（即使目前只有旧图片）
});