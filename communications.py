"""服务端公告与附件邮件，领取状态和库存同次保存。"""

from copy import deepcopy
import time

import user_storage
from item_catalog import validate_rewards, give_items

MAIL_COMMANDS = {30002, 30004, 30006, 30008, 30014, 30020, 30022}


def active_mails(user):
    """保留未过期普通邮件及已收藏邮件。"""
    now = int(time.time())
    return [m for m in user.get('mails', []) if m.get('collected') or m['expires'] > now]


def mail_brief(user):
    """计算客户端邮件红点和数量。"""
    rows = [m for m in active_mails(user) if not m.get('collected')]
    return {'unread_number': sum(not m['read'] for m in rows), 'total_number': len(rows)}


def attachments(mail):
    """把存档物品数量转换为邮件协议字段。"""
    return [{'id': r['id'], 'number': r['num']} for r in mail['rewards']]


def mail_list(user):
    """返回当前普通邮件列表，标志 1 分别表示未读、未领。"""
    rows = [{'id': m['id'], 'date': m['date'], 'title': m['title'], 'attach_flag': (2 if m['claimed'] else 1) if m['rewards'] else 0,
             'read_flag': 2 if m['read'] else 1, 'attachment_list': attachments(m), 'timeout_timestamp': m['expires'],
             'star_state': 0, 'mail_template_id': 0, 'title_format': [], 'i18n_info': []}
            for m in active_mails(user) if not m.get('collected')]
    return {'mail_list': rows, 'total_num': len(rows)}


def collect_info(mail):
    """编码收藏邮件列表所需的标题与日期。"""
    return {'id': mail['id'], 'collect_date': mail['collected'], 'title': mail['title'],
            'mail_template_id': 0, 'title_format': [], 'i18n_info': [], 'mail_timestamp': mail['date']}


def mail_request(user, command, request):
    """处理列表、阅读、附件领取、删除和收藏；拒绝丢失未领取的附件。"""
    if command == 30002:
        return mail_list(user)
    if command == 30020:
        rows = [collect_info(m) for m in active_mails(user) if m.get('collected')]
        return {'collect_mail_list': rows, 'collect_total_num': len(rows)}
    mail_id = request.get('id', request.get('mail_id', 0))
    rows = active_mails(user)
    mail = next((m for m in rows if m['id'] == mail_id), None)
    if command in (30008, 30022, 30014) and mail is None:
        raise ValueError('邮件不存在或已过期')
    if command in (30008, 30022):
        mail['read'] = True
        return {'result': 0, 'detail_info': {'id': mail_id, 'sender': mail['sender'],
            'content_list': [{'content_type': 2, 'text': mail['content']}], 'attachment_list': attachments(mail),
            'mail_template_id': 0, 'sender_format': [], 'content_format': [], 'i18n_info': [], 'link_param': []}}
    if command == 30004:
        targets = [m for m in rows if (mail_id == 0 or m['id'] == mail_id) and m['rewards'] and not m['claimed']]
        if not targets:
            raise ValueError('没有可领取的附件')
        rewards = give_items(user, [r for m in targets for r in m['rewards']])
        for m in targets:
            m.update(read=True, claimed=True)
        return {'result': 0, 'attachment_list': rewards, 'success_mail_ids': [m['id'] for m in targets]}
    if command == 30006:
        targets = [m for m in rows if (mail_id == 0 or m['id'] == mail_id) and m['read']
                   and (m['claimed'] or not m['rewards']) and not m.get('collected')]
        if mail_id and not targets:
            raise ValueError('请先阅读邮件并领取附件')
        ids = {m['id'] for m in targets}
        user['mails'] = [m for m in user.get('mails', []) if m['id'] not in ids]
        return {'id_list': list(ids), 'no_need_data': []}
    if request['opt'] not in (0, 1):
        raise ValueError('收藏操作无效')
    if request['opt'] and mail['rewards'] and not mail['claimed']:
        raise ValueError('请先领取附件再收藏邮件')
    mail['collected'] = int(time.time()) if request['opt'] else 0
    return {'result': 0, 'collect_mail': collect_info(mail)}


def text_value(value, name, limit):
    """检查管理界面的必填中文文本字段。"""
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name}为空或超出 {limit} 字符')
    return value.strip()


def send_mail(manager, uid, values):
    """为单账号或全部现有账号生成邮件，每个账号独立原子保存。"""
    title = text_value(values.get('title'), '标题', 100)
    content = text_value(values.get('content'), '正文', 20000)
    sender = text_value(values.get('sender', 'GM系统'), '发件人', 100)
    rewards = validate_rewards(values['rewards']) if values.get('rewards') else []
    days = values.get('days', 30)
    if type(days) is not int or not 1 <= days <= 3650:
        raise ValueError('有效期须为 1 至 3650 天')
    with manager._lock:
        ids = [int(p.stem) for p in user_storage.USERS_DIR.glob('*.json') if p.stem.isdigit()] if uid == 0 else [uid]
        users = [manager.get_user_by_uid(i) for i in ids]
        if not users or any(u is None for u in users):
            raise ValueError('账号不存在')
        for user in users:
            if len(active_mails(user)) >= 500:
                raise ValueError(f"账号 {user['uid']} 的邮箱已满")
            if rewards:
                give_items(deepcopy(user), rewards)
        now = int(time.time())
        for user in users:
            mail_id = max(user.get('next_mail_id', 1), max((m['id'] for m in user.get('mails', [])), default=0) + 1)
            user.setdefault('mails', []).append({'id': mail_id, 'date': now, 'title': title, 'content': content,
                'sender': sender, 'rewards': deepcopy(rewards), 'expires': now + days * 86400,
                'read': False, 'claimed': False, 'collected': 0})
            user['next_mail_id'] = mail_id + 1
            manager.save_user(user)
        return ids


def announcement_store(manager):
    """读取本地公告存档，未创建公告时保持空列表。"""
    return manager._load_json(user_storage.DATA_DIR / 'announcements.json', {'next_id': 1, 'items': []})


def announcement_data(manager):
    """仅下发有效排期内的公告，保持真实客户端内容结构。"""
    now = int(time.time())
    return {'announcement_list': [{'id': a['id'], 'type': a['type'], 'title': a['title'],
        'start_timestamp': a['start'], 'end_timestamp': a['end'], 'index': a['id'], 'star': 0,
        'content': [{'content_type': 2, 'text': a['content']}], 'i18n_info': []}
        for a in announcement_store(manager)['items'] if a['start'] <= now < a['end']]}


def save_announcement(manager, values, delete=False):
    """创建、更新或删除公告，标题正文和排期均严格校验。"""
    with manager._lock:
        store = announcement_store(manager)
        item = values.get('id', 0)
        if type(item) is not int or item < 0:
            raise ValueError('公告编号无效')
        previous = next((a for a in store['items'] if a['id'] == item), None)
        if item and previous is None:
            raise ValueError('公告不存在')
        if delete:
            if not previous:
                raise ValueError('请选择待删除的公告')
            store['items'].remove(previous)
        else:
            now = int(time.time())
            kind, start, end = values.get('type', 101), values.get('start', now), values.get('end', now + 30 * 86400)
            if kind not in (101, 102, 104) or type(start) is not int or type(end) is not int or not 0 <= start < end < 2**32:
                raise ValueError('公告类型或排期无效')
            row = {'id': item or store['next_id'], 'type': kind, 'start': start, 'end': end,
                'title': text_value(values.get('title'), '标题', 100), 'content': text_value(values.get('content'), '正文', 20000)}
            if previous:
                store['items'].remove(previous)
            else:
                store['next_id'] += 1
            store['items'].append(row)
        manager._save_json(user_storage.DATA_DIR / 'announcements.json', store)
        return store
