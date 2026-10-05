'use strict';
const byId = id => document.getElementById(id);
let state = { users: [], announcements: [], audit: [] };
let itemPage = 0;
let itemQuery = '';

/** 在状态栏显示操作结果。 */
function status(message, result = '') {
  byId('status').textContent = message;
  byId('status').dataset.result = result;
}

/** 请求同源后台，并把错误显示为中文消息。 */
async function api(path, values) {
  const response = await fetch(`/gm/api/${path}`, values === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

/** 获取当前选中的账号。 */
function currentUser() {
  return state.users.find(user => user.uid === Number(byId('account').value));
}

/** 创建文本单元格，所有服务端文本均作为文本显示。 */
function cell(row, value) {
  const td = document.createElement('td');
  td.textContent = String(value ?? '');
  row.append(td);
}

/** 按所选类别展示存档，不提供任意 JSON 覆盖功能。 */
function renderAccount() {
  const user = currentUser();
  if (!user) return;
  const c = user.counts;
  byId('summary').textContent = `${user.online ? '在线' : '离线'} · ${c.heroes} 个角色 · ${c.skins} 款皮肤 · ${c.servants} 种钥从`;
  const field = byId('data-field').value;
  let value = user[field] ?? {};
  if (field === 'currencies') value = user.currency_rows;
  if (field === 'teams') value = Object.fromEntries(Object.entries(user).filter(([key]) => /reserve|team/.test(key)));
  if (field === 'decorations') value = { profile: user.profile, frames: user.unlocked_frames, decorations: user.unlocked_decorations };
  byId('account-data').textContent = JSON.stringify(value, null, 2);
  byId('mail-data').textContent = JSON.stringify(user.mails ?? [], null, 2);
}

/** 重读存档、公告和管理记录，保留当前账号选择。 */
async function refresh() {
  const selected = byId('account').value;
  state = await api('state');
  byId('account').replaceChildren(...state.users.map(user => {
    const option = document.createElement('option');
    option.value = user.uid;
    option.textContent = `${user.uid} · ${user.nick || user.account}`;
    return option;
  }));
  if (state.users.some(user => String(user.uid) === selected)) byId('account').value = selected;
  renderAccount();
  renderNotices();
  byId('audit-rows').replaceChildren(...[...state.audit].reverse().map(record => {
    const row = document.createElement('tr');
    const labels = { command: 'GM 指令', mail: '发送邮件', announcement: '保存公告', delete_announcement: '删除公告', unlock: '补齐解锁' };
    [new Date(record.time * 1000).toLocaleString('zh-CN'), labels[record.action] || record.action, record.uid, record.details].forEach(v => cell(row, v));
    return row;
  }));
}

/** 执行管理动作，完成后重新读取最新数据。 */
async function action(values) {
  const data = await api('action', { uid: currentUser()?.uid, ...values });
  await refresh();
  status(data.message, 'success');
}

/** 查询当前页物品并显示总数及翻页状态。 */
async function loadItems() {
  const data = await api(`items?q=${encodeURIComponent(itemQuery)}&page=${itemPage}`);
  byId('item-total').textContent = `共 ${data.total} 条匹配记录`;
  byId('page').textContent = `第 ${itemPage + 1} 页`;
  byId('prev').disabled = itemPage === 0;
  byId('next').disabled = (itemPage + 1) * 100 >= data.total;
  byId('item-rows').replaceChildren(...data.items.map(item => {
    const row = document.createElement('tr');
    [item.id, item.name, item.type_name, item.description].forEach(v => cell(row, v));
    return row;
  }));
}

/** 转换时间戳为浏览器当前时区的日期输入值。 */
function localTime(timestamp) {
  const date = new Date(timestamp * 1000);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

/** 将指定公告填入编辑表单。 */
function editNotice(notice) {
  const form = byId('notice-form');
  const values = notice || { id: 0, type: 101, title: '', content: '', start: Math.floor(Date.now() / 1000), end: Math.floor(Date.now() / 1000) + 86400 * 30 };
  for (const key of ['id', 'type', 'title', 'content']) form.elements[key].value = values[key];
  for (const key of ['start', 'end']) form.elements[key].value = localTime(values[key]);
}

/** 展示公告排期并提供编辑与删除。 */
function renderNotices() {
  byId('notice-list').replaceChildren(...state.announcements.map(notice => {
    const row = document.createElement('div'); row.className = 'notice-row';
    const title = document.createElement('h3'); title.textContent = notice.title;
    const time = document.createElement('p'); time.textContent = `${new Date(notice.start * 1000).toLocaleString('zh-CN')} 至 ${new Date(notice.end * 1000).toLocaleString('zh-CN')}`;
    const actions = document.createElement('div'); actions.className = 'actions';
    const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'secondary'; edit.textContent = '编辑'; edit.addEventListener('click', () => editNotice(notice));
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'secondary'; remove.textContent = '删除';
    remove.addEventListener('click', () => run(async () => { if (confirm(`删除公告“${notice.title}”？`)) await action({ action: 'delete_announcement', id: notice.id }); }));
    actions.append(edit, remove); row.append(title, time, actions); return row;
  }));
}

/** 捕获交互错误，并在执行期间禁止重复提交。 */
async function run(task, button) {
  if (button) button.disabled = true;
  try { await task(); } catch (error) { status(error.message, 'error'); }
  finally { if (button) button.disabled = false; }
}

/** 绑定表单提交，交由统一错误处理器执行。 */
function submit(id, handler) {
  byId(id).addEventListener('submit', event => {
    event.preventDefault();
    run(() => handler(new FormData(event.currentTarget)), event.currentTarget.querySelector('button[type="submit"]'));
  });
}

document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-tab]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
  document.querySelectorAll('.panel').forEach(panel => { panel.hidden = panel.id !== button.dataset.tab; });
  if (button.dataset.tab === 'items') run(loadItems);
}));
byId('account').addEventListener('change', renderAccount);
byId('data-field').addEventListener('change', renderAccount);
byId('refresh').addEventListener('click', event => run(async () => { await refresh(); status('数据已刷新', 'success'); }, event.currentTarget));
byId('unlock').addEventListener('click', event => run(() => action({ action: 'unlock' }), event.currentTarget));
submit('command-form', form => action({ action: 'command', command: form.get('command') }));
submit('search-form', async () => { itemPage = 0; itemQuery = byId('item-search').value.trim(); await loadItems(); });
byId('prev').addEventListener('click', () => run(async () => { itemPage--; await loadItems(); }));
byId('next').addEventListener('click', () => run(async () => { itemPage++; await loadItems(); }));
submit('mail-form', form => {
  const rewards = form.get('rewards').trim().split(/\r?\n/).filter(Boolean).map(line => {
    const values = line.trim().split(/\s+/);
    if (values.length !== 2 || values.some(v => !/^\d+$/.test(v))) throw new Error('附件格式：每行填写物品ID 数量');
    return { id: Number(values[0]), num: Number(values[1]) };
  });
  return action({ action: 'mail', uid: form.get('scope') === 'all' ? 0 : currentUser().uid, title: form.get('title'), content: form.get('content'), sender: form.get('sender'), days: Number(form.get('days')), rewards });
});
submit('notice-form', form => action({ action: 'announcement', id: Number(form.get('id')), type: Number(form.get('type')), title: form.get('title'), content: form.get('content'), start: Math.floor(new Date(form.get('start')).getTime() / 1000), end: Math.floor(new Date(form.get('end')).getTime() / 1000) }));
byId('new-notice').addEventListener('click', () => editNotice());
editNotice();
run(async () => { await refresh(); status('数据已加载', 'success'); });
