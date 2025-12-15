// main.js - 所有页面通用
// 说明：本文件包含整个校园二手交易系统的前端交互逻辑，适用于登录、注册、个人中心等页面

/**
 * 简易 DOM 查询函数：通过 ID 获取元素
 * 用法：$('myId') 等价于 document.getElementById('myId')
 * 目的：减少重复代码，提升可读性
 */
function $(id) { 
  return document.getElementById(id); 
}

/**
 * 用户登录函数
 * 触发时机：用户在登录页点击“登录”按钮
 * 功能：收集账号密码，发送 POST 请求到 /login 接口，根据返回结果跳转或提示
 */
async function login() {
  // 发送异步请求到后端登录接口
  const res = await fetch('/login', {
    method: 'POST',                          // 使用 POST 方法提交数据
    headers: {'Content-Type': 'application/json'}, // 声明请求体为 JSON 格式
    body: JSON.stringify({                   // 将表单数据序列化为 JSON 字符串
      account: $('account').value,           // 获取账号输入框的值（学号/手机号/邮箱）
      password: $('password').value          // 获取密码输入框的值
    })
  });
  
  // 解析后端返回的 JSON 数据
  const data = await res.json();
  
  // 弹出后端返回的消息（如“登录成功”或“账号不存在”）
  alert(data.msg);
  
  // 如果登录成功（code === 200），则跳转到首页 '/'
  // 登录成功后：如果有跳转回来地址，就跳回去，否则去首页
const redirect = sessionStorage.getItem('redirect_after_login') || '/';
sessionStorage.removeItem('redirect_after_login');
location.href = redirect;
}

/**
 * 用户注册函数
 * 触发时机：用户在注册页点击“注册”按钮
 * 功能：校验输入合法性，提交注册信息，成功后询问是否跳转登录页
 */
async function register() {
  // 获取并清理用户输入
  const account = $('account').value.trim();        // 账号（去首尾空格）
  const password = $('password').value;             // 密码
  const nickname = $('nickname').value || '校园用户'; // 昵称（若为空则默认“校园用户”）
  const email = $('email').value.trim();            // 邮箱（去首尾空格）

  // 基础校验：账号和密码不能为空
  if (!account || !password) {
    return alert('账号和密码必填！');
  }
  // 密码长度校验：至少6位
  if (password.length < 6) {
    return alert('密码至少6位');
  }

  try {
    // 发送注册请求到后端
    const res = await fetch('/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account, password, nickname, email }) // 简写对象字面量
    });
    
    const data = await res.json();
    alert(data.msg); // 提示注册结果
    
    // 如果注册成功
    if (data.code === 200) {
      // 弹出确认框，询问是否立即跳转登录页
      if (confirm('注册成功！现在去登录？')) {
        location.href = '/login'; // 跳转到登录页面
      }
    }
  } catch (err) {
    // 捕获网络错误（如断网、跨域等）
    alert('网络错误：' + err.message);
  }
}

/**
 * 学籍认证函数
 * 触发时机：用户在个人中心点击“提交认证”按钮
 * 功能：提交学号和是否应届状态，完成身份认证
 */
async function authStudent() {
  const res = await fetch('/api/auth/student', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      stu_id: $('stu_id_input').value,              // 获取用户输入的学号
      is_graduating: $('is_graduating').checked     // 获取复选框是否勾选（true/false）
    })
  });
  
  const data = await res.json();
  alert(data.msg); // 提示认证结果
  
  // 如果认证成功，刷新当前页面以更新用户信息（如显示“已认证”状态）
  if (data.code === 200) location.reload();
}

/**
 * 上传头像函数
 * 触发时机：用户选择图片文件后（通过 input[type=file] 的 onchange 事件）
 * 功能：将选中的图片上传到服务器，并更新页面上的头像预览
 */
function uploadAvatar() {
  const file = $('avatar-input').files[0]; // 获取用户选择的第一个文件
  if (!file) return alert('请选择图片');   // 安全校验

  // 创建 FormData 对象，用于上传二进制文件
  const form = new FormData();
  form.append('file', file); // 添加文件字段，键名为 'file'

  // 发送上传请求（使用传统 Promise 链，因无需 async/await）
  fetch('/api/upload/avatar', { 
    method: 'POST', 
    body: form // 注意：上传文件时不要设置 Content-Type，浏览器会自动设置 multipart/form-data
  })
    .then(r => r.json())        // 将响应解析为 JSON
    .then(d => {
      if (d.code === 200) {
        // 上传成功：更新头像图片的 src
        // 添加时间戳 '?t=' + Date.now() 是为了绕过浏览器缓存，确保显示新头像
        $('avatar-img').src = d.url + '?t=' + Date.now();
        alert('上传成功');
      } else {
        // 上传失败：提示错误信息
        alert(d.msg);
      }
    });
}

/**
 * 页面加载完成后执行的初始化逻辑
 * 功能：
 *   1. 点击头像图片时，触发隐藏的文件选择框
 *   2. 当用户选择文件后，自动调用 uploadAvatar 上传
 */
document.addEventListener('DOMContentLoaded', () => {
  // 获取头像图片元素
  const img = document.getElementById('avatar-img');
  // 如果页面存在该元素（如个人中心页），绑定点击事件
  if (img) img.onclick = () => $('avatar-input').click();

  // 获取文件输入框
  const input = $('avatar-input');
  // 如果存在，绑定 onchange 事件（用户选择文件后自动上传）
  if (input) input.onchange = uploadAvatar;
});