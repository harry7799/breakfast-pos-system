/* ========================================
   共用側邊導覽列組件
   ======================================== */

function createSidebar(currentPage) {
  const navItems = [
    { id: 'pos', icon: '🛒', label: '收銀點餐', href: '/pos' },
    { id: 'kds', icon: '🍳', label: '廚房看板', href: '/kds' },
    { id: 'pickup', icon: '📢', label: '取餐叫號', href: '/pickup' },
    { id: 'admin', icon: '📊', label: '後台管理', href: '/admin' },
    { id: 'home', icon: '🏠', label: '系統首頁', href: '/' },
  ];

  const sidebar = document.createElement('aside');
  sidebar.className = 'sidebar';
  sidebar.setAttribute('role', 'navigation');
  sidebar.setAttribute('aria-label', '主要導覽');

  // Logo
  const logo = document.createElement('div');
  logo.className = 'sidebar-logo';
  logo.textContent = '早';
  logo.title = '青青草原廚房';
  sidebar.appendChild(logo);

  // 導覽項目
  const nav = document.createElement('nav');
  nav.className = 'sidebar-nav';

  navItems.forEach(item => {
    const link = document.createElement('a');
    link.className = 'sidebar-item';
    link.href = item.href;
    if (item.id === currentPage) {
      link.classList.add('active');
      link.setAttribute('aria-current', 'page');
    }

    const icon = document.createElement('span');
    icon.className = 'sidebar-icon';
    icon.textContent = item.icon;
    icon.setAttribute('aria-hidden', 'true');

    const label = document.createElement('span');
    label.className = 'sidebar-label';
    label.textContent = item.label;

    link.appendChild(icon);
    link.appendChild(label);
    nav.appendChild(link);
  });

  sidebar.appendChild(nav);

  // 收合按鈕
  const toggleBtn = document.createElement('button');
  toggleBtn.className = 'sidebar-toggle';
  toggleBtn.type = 'button';
  toggleBtn.title = '收合/展開導覽列';
  toggleBtn.innerHTML = '◀';
  toggleBtn.setAttribute('aria-label', '收合導覽列');
  sidebar.appendChild(toggleBtn);

  // 鎖定按鈕
  const lockBtn = document.createElement('button');
  lockBtn.className = 'sidebar-lock';
  lockBtn.type = 'button';
  lockBtn.title = '鎖定/解鎖導覽列';
  lockBtn.innerHTML = '🔓';
  lockBtn.setAttribute('aria-label', '鎖定導覽列');
  sidebar.appendChild(lockBtn);

  // 登出按鈕
  const footer = document.createElement('div');
  footer.className = 'sidebar-footer';

  const logoutBtn = document.createElement('button');
  logoutBtn.className = 'sidebar-logout';
  logoutBtn.type = 'button';
  logoutBtn.onclick = () => {
    if (confirm('確定要登出嗎？')) {
      localStorage.removeItem('auth_token');
      window.location.href = '/';
    }
  };

  const logoutIcon = document.createElement('span');
  logoutIcon.className = 'sidebar-icon';
  logoutIcon.textContent = '🚪';
  logoutIcon.setAttribute('aria-hidden', 'true');

  const logoutLabel = document.createElement('span');
  logoutLabel.className = 'sidebar-label';
  logoutLabel.textContent = '登出';

  logoutBtn.appendChild(logoutIcon);
  logoutBtn.appendChild(logoutLabel);
  footer.appendChild(logoutBtn);
  sidebar.appendChild(footer);

  return sidebar;
}

// 初始化側邊欄
function initSidebar(currentPage) {
  // 確保在 DOM 載入後執行
  function init() {
    const body = document.body;

    // 創建 app-layout 容器
    const appLayout = document.createElement('div');
    appLayout.className = 'app-layout';

    // 創建側邊欄
    const sidebar = createSidebar(currentPage);
    appLayout.appendChild(sidebar);

    // 創建主內容容器
    const mainContent = document.createElement('div');
    mainContent.className = 'main-content';

    // 將 body 的所有子元素移到 mainContent
    while (body.firstChild) {
      mainContent.appendChild(body.firstChild);
    }

    appLayout.appendChild(mainContent);
    body.appendChild(appLayout);

    // 取得按鈕元素
    const toggleBtn = sidebar.querySelector('.sidebar-toggle');
    const lockBtn = sidebar.querySelector('.sidebar-lock');

    // 從 localStorage 讀取狀態
    const isCollapsed = localStorage.getItem('sidebar-collapsed') === 'true';
    const isLocked = localStorage.getItem('sidebar-locked') === 'true';

    // 恢復狀態
    if (isCollapsed) {
      sidebar.classList.add('collapsed');
      toggleBtn.innerHTML = '▶';
      toggleBtn.setAttribute('aria-label', '展開導覽列');
    }

    if (isLocked) {
      sidebar.classList.add('locked');
      lockBtn.classList.add('locked');
      lockBtn.innerHTML = '🔒';
      lockBtn.setAttribute('aria-label', '解鎖導覽列');
    }

    // 收合/展開功能
    toggleBtn.addEventListener('click', () => {
      const collapsed = sidebar.classList.toggle('collapsed');
      localStorage.setItem('sidebar-collapsed', collapsed);

      if (collapsed) {
        toggleBtn.innerHTML = '▶';
        toggleBtn.setAttribute('aria-label', '展開導覽列');
      } else {
        toggleBtn.innerHTML = '◀';
        toggleBtn.setAttribute('aria-label', '收合導覽列');
      }
    });

    // 鎖定/解鎖功能
    lockBtn.addEventListener('click', () => {
      const locked = sidebar.classList.toggle('locked');
      lockBtn.classList.toggle('locked');
      localStorage.setItem('sidebar-locked', locked);

      if (locked) {
        lockBtn.innerHTML = '🔒';
        lockBtn.setAttribute('aria-label', '解鎖導覽列');
      } else {
        lockBtn.innerHTML = '🔓';
        lockBtn.setAttribute('aria-label', '鎖定導覽列');
      }
    });
  }

  // 如果 DOM 已載入，立即執行；否則等待
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}
