/* 为每个代码块提供纯文本复制，并处理剪贴板权限与本地 HTTP 预览。 */
function installCodeCopy(hook) {
  hook.doneEach(function enhancePage() {
    const menu = document.querySelector('.sidebar-toggle');
    if (menu) menu.setAttribute('aria-label', '展开或收起导航');

    document.querySelectorAll('.markdown-section pre').forEach(function addCopyButton(pre) {
      const code = pre.querySelector('code');
      if (!code || pre.querySelector('.code-copy')) return;

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'code-copy';
      button.textContent = '复制';
      button.setAttribute('aria-label', '复制此代码块');
      button.setAttribute('aria-live', 'polite');
      button.addEventListener('click', async function copyCode() {
        try {
          await navigator.clipboard.writeText(code.textContent);
          button.textContent = '已复制';
        } catch {
          const selection = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(code);
          selection.removeAllRanges();
          selection.addRange(range);
          button.textContent = '请按 Ctrl+C';
        }
        window.setTimeout(function resetCopyLabel() {
          button.textContent = '复制';
        }, 2000);
      });
      pre.appendChild(button);
    });
  });
}

window.$docsify = {
  name: 'Hoshimi 文档',
  nameLink: '#/',
  homepage: 'README.md',
  loadSidebar: true,
  loadNavbar: true,
  alias: {
    '/.*/_sidebar.md': '/_sidebar.md',
    '/.*/_navbar.md': '/_navbar.md'
  },
  routerMode: 'hash',
  auto2top: true,
  maxLevel: 3,
  subMaxLevel: 2,
  notFoundPage: '_404.md',
  externalLinkTarget: '_blank',
  externalLinkRel: 'noopener noreferrer',
  executeScript: false,
  search: {
    paths: [
      '/', '/quickstart', '/startup', '/features', '/update', '/backup',
      '/switch-official', '/official-import', '/gm', '/remote', '/advanced',
      '/troubleshooting', '/reporting', '/about', '/deployment'
    ],
    placeholder: '搜索文档',
    noData: '没有找到相关内容',
    depth: 3,
    maxAge: 86400000,
    namespace: 'hoshimi-docs-v1'
  },
  plugins: [installCodeCopy]
};
