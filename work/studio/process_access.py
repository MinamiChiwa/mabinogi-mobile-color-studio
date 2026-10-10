"""Read-only evidence for a denied process read; never changes privileges."""
import ctypes
import os
from ctypes import wintypes as W


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008


def _base_diagnostic(target_pid, win_error, read_access):
    return dict(operation='OpenProcess', win_error=int(win_error), read_access=int(read_access),
                tool_pid=os.getpid(), target_pid=int(target_pid),
                tool_elevated=None, target_elevated=None,
                tool_integrity=None, target_integrity=None,
                tool_integrity_rid=None, target_integrity_rid=None,
                tool_query_errors=[], target_query_errors=[])


def _query_error(operation, error):
    code = getattr(error, 'winerror', None)
    if code is None:
        code = getattr(error, 'errno', None)
    return dict(operation=operation, win_error=code, error_type=type(error).__name__)


class ProcessReadDenied(OSError):
    """Preserve the original OpenProcess error even if extra queries fail."""
    def __init__(self, target_pid, win_error, *, read_access=0x410, diagnostic=None):
        super().__init__(win_error, 'OpenProcess read-only failed')
        self.winerror = win_error
        self.diagnostic = _base_diagnostic(target_pid, win_error, read_access)
        try:
            details = (collect_process_access_diagnostic(target_pid, win_error, read_access=read_access)
                       if diagnostic is None else diagnostic)
            self.diagnostic.update(details)
        except Exception as error:
            self.diagnostic['diagnostic_query_errors'] = [_query_error('diagnostic_collection', error)]
        # Ancillary diagnostics may not replace the failed request's evidence.
        self.diagnostic.update(operation='OpenProcess', win_error=int(win_error),
                               read_access=int(read_access), target_pid=int(target_pid))


class _SIDAndAttributes(ctypes.Structure):
    _fields_ = [('Sid', ctypes.c_void_p), ('Attributes', W.DWORD)]


class _Win32TokenAPI:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        for dll, name, args, result in (
            (self.kernel, 'GetCurrentProcess', [], W.HANDLE),
            (self.kernel, 'GetCurrentProcessId', [], W.DWORD),
            (self.kernel, 'OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            (self.kernel, 'CloseHandle', [W.HANDLE], W.BOOL),
            (self.advapi, 'OpenProcessToken', [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)], W.BOOL),
            (self.advapi, 'GetTokenInformation', [W.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                               W.DWORD, ctypes.POINTER(W.DWORD)], W.BOOL),
            (self.advapi, 'IsValidSid', [ctypes.c_void_p], W.BOOL),
            (self.advapi, 'GetSidSubAuthorityCount', [ctypes.c_void_p], ctypes.POINTER(ctypes.c_ubyte)),
            (self.advapi, 'GetSidSubAuthority', [ctypes.c_void_p, W.DWORD], ctypes.POINTER(W.DWORD)),
        ):
            function = getattr(dll, name)
            function.argtypes = args
            function.restype = result

    def current_process(self):
        return int(self.kernel.GetCurrentProcessId()), self.kernel.GetCurrentProcess()

    def open_process(self, pid, access):
        handle = self.kernel.OpenProcess(access, False, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), 'OpenProcess limited query failed')
        return handle

    def open_token(self, process, access):
        token = W.HANDLE()
        if not self.advapi.OpenProcessToken(process, access, ctypes.byref(token)):
            raise OSError(ctypes.get_last_error(), 'OpenProcessToken query failed')
        return token.value

    def token_elevated(self, token):
        value, length = W.DWORD(), W.DWORD()
        if not self.advapi.GetTokenInformation(token, 20, ctypes.byref(value),
                                              ctypes.sizeof(value), ctypes.byref(length)):
            raise OSError(ctypes.get_last_error(), 'TokenElevation query failed')
        return bool(value.value)

    def token_integrity(self, token):
        length = W.DWORD()
        self.advapi.GetTokenInformation(token, 25, None, 0, ctypes.byref(length))
        if not ctypes.sizeof(_SIDAndAttributes) <= length.value <= 65536:
            raise OSError(ctypes.get_last_error(), 'TokenIntegrityLevel size unavailable')
        buffer = ctypes.create_string_buffer(length.value)
        if not self.advapi.GetTokenInformation(token, 25, buffer, len(buffer), ctypes.byref(length)):
            raise OSError(ctypes.get_last_error(), 'TokenIntegrityLevel query failed')
        sid = ctypes.cast(buffer, ctypes.POINTER(_SIDAndAttributes)).contents.Sid
        if not sid or not self.advapi.IsValidSid(sid):
            raise ValueError('Token integrity SID unavailable')
        count = self.advapi.GetSidSubAuthorityCount(sid)
        if not count or not count[0]:
            raise ValueError('Token integrity RID unavailable')
        value = self.advapi.GetSidSubAuthority(sid, int(count[0]) - 1)
        if not value:
            raise ValueError('Token integrity RID unavailable')
        rid = int(value[0])
        levels = ((0x1000, 'untrusted'), (0x2000, 'low'), (0x3000, 'medium'),
                  (0x4000, 'high'), (0x5000, 'system'), (0x6000, 'protected_process'))
        return next((name for upper, name in levels if rid < upper), 'unknown'), rid

    def close(self, handle):
        if not self.kernel.CloseHandle(handle):
            raise OSError(ctypes.get_last_error(), 'CloseHandle failed')


def _query_token(api, process, prefix, diagnostic):
    errors = diagnostic[prefix + '_query_errors']
    try:
        token = api.open_token(process, TOKEN_QUERY)
    except Exception as error:
        errors.append(_query_error('OpenProcessToken', error))
        return
    try:
        try:
            diagnostic[prefix + '_elevated'] = api.token_elevated(token)
        except Exception as error:
            errors.append(_query_error('TokenElevation', error))
        try:
            level, rid = api.token_integrity(token)
            diagnostic[prefix + '_integrity'] = level
            diagnostic[prefix + '_integrity_rid'] = rid
        except Exception as error:
            errors.append(_query_error('TokenIntegrityLevel', error))
    finally:
        try:
            api.close(token)
        except Exception as error:
            errors.append(_query_error('CloseToken', error))


def collect_process_access_diagnostic(target_pid, win_error, *, read_access=0x410, api=None):
    """Query only token elevation/integrity; inaccessible values remain unknown."""
    diagnostic = _base_diagnostic(target_pid, win_error, read_access)
    try:
        api = _Win32TokenAPI() if api is None else api
        tool_pid, current_process = api.current_process()
        diagnostic['tool_pid'] = tool_pid
        _query_token(api, current_process, 'tool', diagnostic)
    except Exception as error:
        diagnostic['tool_query_errors'].append(_query_error('CurrentProcessToken', error))
        if api is None:
            return diagnostic
    try:
        process = api.open_process(target_pid, PROCESS_QUERY_LIMITED_INFORMATION)
    except Exception as error:
        diagnostic['target_query_errors'].append(_query_error('OpenProcess', error))
        return diagnostic
    try:
        _query_token(api, process, 'target', diagnostic)
    finally:
        try:
            api.close(process)
        except Exception as error:
            diagnostic['target_query_errors'].append(_query_error('CloseProcess', error))
    return diagnostic
