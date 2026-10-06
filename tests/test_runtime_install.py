"""使用真实 Windows 文件句柄验证准备目录重试与失败回滚。"""

import ctypes
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Timer
from unittest import TestCase, main, skipUnless
from unittest.mock import patch

from prepare_runtime import install_runtime


@contextmanager
def locked_directory(path: Path, release_after: float | None = None):
    """打开不允许删除共享的目录句柄，模拟其他程序阻止目录改名。"""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())

    def release():
        """释放占用句柄，确保关闭只执行一次。"""
        nonlocal handle
        if handle is not None:
            if not kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())
            handle = None

    timer = Timer(release_after, release) if release_after is not None else None
    if timer is not None:
        timer.start()
    try:
        yield
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        release()


@skipUnless(os.name == 'nt', '验证 Windows 目录共享锁')
class RuntimeInstallTests(TestCase):
    """发布必须保留可用依赖，允许短暂锁解除后继续。"""

    def test_transient_lock(self):
        """首次准备遇到真实目录锁，锁解除后应成功完成安装。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staging, runtime = root / 'staging', root / 'runtime'
            staging.mkdir()
            (staging / 'marker.txt').write_text('new', encoding='utf-8')
            with locked_directory(staging, release_after=0.35):
                install_runtime(staging, runtime)
            self.assertEqual((runtime / 'marker.txt').read_text(encoding='utf-8'), 'new')
            self.assertFalse(staging.exists())

    def test_locked_staging_restores_existing_runtime(self):
        """新目录持续占用时发布失败，旧目录与准备结果都必须保留。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staging, runtime = root / 'staging', root / 'runtime'
            staging.mkdir()
            runtime.mkdir()
            (staging / 'marker.txt').write_text('new', encoding='utf-8')
            (runtime / 'marker.txt').write_text('old', encoding='utf-8')
            with locked_directory(staging), patch('prepare_runtime.time.sleep'):
                with self.assertRaises(PermissionError):
                    install_runtime(staging, runtime)
            self.assertEqual((runtime / 'marker.txt').read_text(encoding='utf-8'), 'old')
            self.assertEqual((staging / 'marker.txt').read_text(encoding='utf-8'), 'new')

    def test_locked_existing_runtime_stays_in_place(self):
        """旧目录持续占用时不移动旧依赖，也不修改本次准备结果。"""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staging, runtime = root / 'staging', root / 'runtime'
            staging.mkdir()
            runtime.mkdir()
            (runtime / 'marker.txt').write_text('old', encoding='utf-8')
            with locked_directory(runtime), patch('prepare_runtime.time.sleep'):
                with self.assertRaises(PermissionError):
                    install_runtime(staging, runtime)
            self.assertTrue(staging.exists())
            self.assertEqual((runtime / 'marker.txt').read_text(encoding='utf-8'), 'old')


if __name__ == '__main__':
    main()
