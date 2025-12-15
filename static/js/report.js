let reportGoodsId = 0;
let reportSellerId = 0;

function reportModal(goods_id, seller_id) {
  reportGoodsId = goods_id;
  reportSellerId = seller_id;
  document.getElementById('report-modal').style.display = 'flex';
  document.getElementById('report-reason').value = '';
  document.getElementById('report-desc').value = '';
}

function closeReportModal() {
  document.getElementById('report-modal').style.display = 'none';
}

async function submitReport() {
  const reason = document.getElementById('report-reason').value.trim();
  const desc = document.getElementById('report-desc').value.trim();

  if (!reason) {
    alert('请选择举报原因');
    return;
  }

  const btn = document.getElementById('report-submit-btn');
  btn.textContent = '提交中...';
  btn.disabled = true;

  try {
    const res = await fetch('/api/report/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        target_type: 'goods',
        target_id: reportGoodsId,
        reason: reason,
        description: desc
      })
    });
    const d = await res.json();
    alert(d.msg || '举报成功，感谢您的反馈！');

    if (d.code === 200) {
      closeReportModal();
    }
  } catch (err) {
    alert('网络错误，请检查网络后重试');
  } finally {
    btn.textContent = '提交举报';
    btn.disabled = false;
  }
}