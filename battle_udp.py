"""本地单人战斗使用的 XServer 握手与 KCP 消息传输。"""

import asyncio
import struct
import time
from itertools import count


class BattleUDP(asyncio.DatagramProtocol):
    """处理 KCP 握手、确认、重传和有序分片。"""

    def __init__(self, handler):
        """接收业务回调；每个连接独立维护收发序号。"""
        self.handler = handler
        self.channels = {}
        self.connections = count(1)
        self.transport = None
        self.timer = None

    def connection_made(self, transport):
        """启动短周期重传，避免客户端丢包后永久等待。"""
        self.transport = transport
        self.tick()

    def connection_lost(self, error):
        """关闭端点时清理定时器。"""
        if self.timer:
            self.timer.cancel()

    def tick(self):
        """重传未确认的段并回收长时间无数据的连接。"""
        now = time.monotonic()
        for address, channel in list(self.channels.items()):
            if now - channel['seen'] > 120:
                del self.channels[address]
                continue
            for sn, (packet, sent) in list(channel['pending'].items()):
                if now - sent > 0.2:
                    self.transport.sendto(packet, address)
                    channel['pending'][sn] = (packet, now)
        self.timer = asyncio.get_running_loop().call_later(0.03, self.tick)

    def datagram_received(self, data, address):
        """解析 XServer 的五字节消息头及标准 KCP 段。"""
        try:
            if len(data) < 5:
                return
            kind = data[0]
            if kind == 1 and len(data) == 9:
                remote, local = struct.unpack_from('<II', data, 1)
                channel = self.channels.get(address)
                if not channel or channel['remote'] != remote:
                    channel = {'remote': remote, 'local': next(self.connections), 'recv': 0, 'send': 0,
                               'buffer': {}, 'parts': [], 'pending': {}, 'seen': time.monotonic(), 'context': {}}
                    self.channels[address] = channel
                    print(f'[战斗 UDP] 已连接 {address}')
                self.transport.sendto(struct.pack('<BII', 2, channel['local'], remote), address)
                return
            channel = self.channels.get(address)
            if not channel:
                return
            channel['seen'] = time.monotonic()
            if kind == 3:
                self.channels.pop(address, None)
                return
            if kind != 4:
                return
            offset = 5
            while offset + 24 <= len(data):
                conv, cmd, frg, wnd, ts, sn, una, size = struct.unpack_from('<IBBHIIII', data, offset)
                offset += 24
                if offset + size > len(data):
                    return
                body = data[offset:offset+size]
                offset += size
                for pending_sn in list(channel['pending']):
                    if pending_sn < una:
                        channel['pending'].pop(pending_sn)
                if cmd == 82:
                    channel['pending'].pop(sn, None)
                elif cmd == 81:
                    if sn >= channel['recv']:
                        channel['buffer'][sn] = (frg, body)
                    self.segment(address, channel, 82, 0, ts, sn, b'')
                    while channel['recv'] in channel['buffer']:
                        fragment, payload = channel['buffer'].pop(channel['recv'])
                        channel['recv'] += 1
                        channel['parts'].append(payload)
                        if fragment == 0:
                            packet = b''.join(channel['parts'])
                            channel['parts'] = []
                            for response in self.handler(packet, channel['context']):
                                self.send_message(address, channel, response)
                elif cmd == 83:
                    self.segment(address, channel, 84, 0, ts, 0, b'')
        except (ValueError, struct.error) as error:
            print(f'[战斗 UDP 拒绝] {error}')

    def segment(self, address, channel, cmd, frg, ts, sn, payload):
        """编码确认或数据段，数据段保留到对端确认。"""
        remote = channel['remote']
        packet = struct.pack('<BI', 4, remote) + struct.pack(
            '<IBBHIIII', remote, cmd, frg, 256, ts, sn, channel['recv'], len(payload)) + payload
        self.transport.sendto(packet, address)
        if cmd == 81:
            channel['pending'][sn] = (packet, time.monotonic())

    def send_message(self, address, channel, packet):
        """将 native 消息分片发送，与客户端 446 字节 MSS 保持兼容。"""
        parts = [packet[i:i+446] for i in range(0, len(packet), 446)] or [b'']
        for index, payload in enumerate(parts):
            sn = channel['send']
            channel['send'] += 1
            self.segment(address, channel, 81, len(parts)-index-1,
                         int(time.monotonic()*1000) & 0xffffffff, sn, payload)
