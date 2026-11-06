/* agent.c - the art98 guest agent.
 *
 * Runs inside Windows 98 and answers requests from the host over COM1. It is
 * deliberately thin: the host owns all timing and choreography, and the agent
 * is a remote Win32 call proxy plus the few things that cannot be proxied
 * because they need callbacks or a real local loop.
 *
 * Wire format, one frame per line, both directions:
 *
 *     <payload> *<crc16 hex>\n
 *
 * Requests:   <id> <VERB> <args...>
 * Replies:    <id> OK <values...>  |  <id> ERR <code> "<text>"
 * Row:        <id> + <values...>   (zero or more, before the final OK)
 * Events:     ! <NAME> <values...>
 *
 * Arguments are 123 or 0x7b (dword), "text" (C escapes, pointer to a string),
 * #deadbeef (in/out buffer) or &32 (zeroed out buffer of 32 bytes). Buffers
 * are handed back in the reply in argument order, which is how structs like
 * RECT reach the host.
 */

#define WIN32_LEAN_AND_MEAN
#define WINVER 0x0400
#define _WIN32_WINDOWS 0x0410
#include <windows.h>
#include <tlhelp32.h>

#define PROTOCOL_VERSION 1
#define MAX_LINE 16384
#define MAX_ARGS 16
#define MAX_BLOB 8192
#define WM_REQUEST (WM_APP + 1)
#define READ_POLL_MS 2
#define HELLO_TIMER 1
#define HELLO_INTERVAL_MS 3000

typedef struct {
    char kind; /* 'i' number, 's' string, 'b' buffer */
    DWORD num; /* number, or buffer length */
    char *ptr;
} Arg;

typedef struct {
    char *line;
    DWORD id;
    char *verb;
    int argc;
    Arg args[MAX_ARGS];
} Job;

typedef struct {
    char *data;
    DWORD len, cap;
} Buf;

static HANDLE com = INVALID_HANDLE_VALUE;
static HANDLE heap;
static HWND request_window;
static CRITICAL_SECTION tx_lock;
static volatile int seen_request;

/* The compiler may emit these even with -fno-builtin. */
void *memset(void *dst, int c, size_t n)
{
    char *d = dst;
    while (n--)
        *d++ = (char)c;
    return dst;
}

void *memcpy(void *dst, const void *src, size_t n)
{
    char *d = dst;
    const char *s = src;
    while (n--)
        *d++ = *s++;
    return dst;
}

static void *mem_alloc(DWORD n)
{
    return HeapAlloc(heap, HEAP_ZERO_MEMORY, n ? n : 1);
}

static void mem_free(void *p)
{
    if (p)
        HeapFree(heap, 0, p);
}

static WORD crc16(const char *p, DWORD n)
{
    WORD crc = 0xffff;
    while (n--) {
        int i;
        crc ^= (WORD)((BYTE)*p++) << 8;
        for (i = 0; i < 8; i++)
            crc = (crc & 0x8000) ? (WORD)((crc << 1) ^ 0x1021) : (WORD)(crc << 1);
    }
    return crc;
}

/* ---- output ---- */

static void buf_reserve(Buf *b, DWORD extra)
{
    DWORD need = b->len + extra;
    char *grown;
    if (need <= b->cap)
        return;
    b->cap = need * 2 + 64;
    grown = mem_alloc(b->cap);
    if (b->data) {
        memcpy(grown, b->data, b->len);
        mem_free(b->data);
    }
    b->data = grown;
}

static void buf_char(Buf *b, char c)
{
    buf_reserve(b, 1);
    b->data[b->len++] = c;
}

static void buf_str(Buf *b, const char *s)
{
    while (*s)
        buf_char(b, *s++);
}

static void buf_uint(Buf *b, DWORD v)
{
    char tmp[12];
    int i = 0;
    do {
        tmp[i++] = (char)('0' + v % 10);
        v /= 10;
    } while (v);
    while (i)
        buf_char(b, tmp[--i]);
}

static void buf_hex_digits(Buf *b, DWORD v, int digits)
{
    static const char hex[] = "0123456789abcdef";
    while (digits--)
        buf_char(b, hex[(v >> (digits * 4)) & 15]);
}

static void buf_num(Buf *b, DWORD v)
{
    buf_char(b, ' ');
    buf_uint(b, v);
}

static void buf_blob(Buf *b, const char *p, DWORD n)
{
    DWORD i;
    buf_str(b, " #");
    for (i = 0; i < n; i++)
        buf_hex_digits(b, (BYTE)p[i], 2);
}

static void buf_quoted(Buf *b, const char *s)
{
    buf_str(b, " \"");
    for (; *s; s++) {
        BYTE c = (BYTE)*s;
        if (c == '"' || c == '\\') {
            buf_char(b, '\\');
            buf_char(b, (char)c);
        } else if (c < 0x20) {
            buf_str(b, "\\x");
            buf_hex_digits(b, c, 2);
        } else {
            buf_char(b, (char)c);
        }
    }
    buf_char(b, '"');
}

/* Serial writes block the caller until the bytes have left. Overlapped I/O
 * keeps them from serialising against the reader thread's pending read. */
static void com_write(const char *p, DWORD n)
{
    OVERLAPPED ov;
    DWORD done = 0;
    memset(&ov, 0, sizeof ov);
    ov.hEvent = CreateEventA(NULL, TRUE, FALSE, NULL);
    if (!WriteFile(com, p, n, &done, &ov) && GetLastError() == ERROR_IO_PENDING)
        GetOverlappedResult(com, &ov, &done, TRUE);
    CloseHandle(ov.hEvent);
}

static void send_buf(Buf *b)
{
    WORD crc = crc16(b->data, b->len);
    buf_str(b, " *");
    buf_hex_digits(b, crc, 4);
    buf_char(b, '\n');
    EnterCriticalSection(&tx_lock);
    com_write(b->data, b->len);
    LeaveCriticalSection(&tx_lock);
    mem_free(b->data);
    b->data = NULL;
    b->len = b->cap = 0;
}

static void reply_start(Buf *b, DWORD id, const char *tag)
{
    memset(b, 0, sizeof *b);
    buf_uint(b, id);
    buf_char(b, ' ');
    buf_str(b, tag);
}

static void reply_error(DWORD id, const char *code, const char *text)
{
    Buf b;
    reply_start(&b, id, "ERR ");
    buf_str(&b, code);
    buf_quoted(&b, text);
    send_buf(&b);
}

static void reply_ok(DWORD id, DWORD value)
{
    Buf b;
    reply_start(&b, id, "OK");
    buf_num(&b, value);
    send_buf(&b);
}

static void send_event_hello(void)
{
    Buf b;
    memset(&b, 0, sizeof b);
    buf_str(&b, "! HELLO");
    buf_num(&b, PROTOCOL_VERSION);
    buf_num(&b, GetTickCount());
    send_buf(&b);
}

/* ---- input parsing ---- */

static int hex_value(char c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

static DWORD parse_number(char **pp)
{
    char *p = *pp;
    DWORD v = 0;
    if (p[0] == '0' && p[1] == 'x') {
        p += 2;
        while (hex_value(*p) >= 0)
            v = v * 16 + hex_value(*p++);
    } else {
        while (*p >= '0' && *p <= '9')
            v = v * 10 + (DWORD)(*p++ - '0');
    }
    *pp = p;
    return v;
}

static char *skip_spaces(char *p)
{
    while (*p == ' ')
        p++;
    return p;
}

static char *cut_token(char *p)
{
    while (*p && *p != ' ')
        p++;
    if (*p)
        *p++ = 0;
    return p;
}

/* Unescapes in place; the output never outgrows the input. */
static char *parse_string(char *p, Arg *arg)
{
    char *out = ++p;
    arg->kind = 's';
    arg->ptr = out;
    while (*p && *p != '"') {
        if (*p != '\\') {
            *out++ = *p++;
            continue;
        }
        p++;
        switch (*p) {
        case 'n': *out++ = '\n'; p++; break;
        case 'r': *out++ = '\r'; p++; break;
        case 't': *out++ = '\t'; p++; break;
        case 'x':
            if (hex_value(p[1]) >= 0 && hex_value(p[2]) >= 0) {
                *out++ = (char)(hex_value(p[1]) * 16 + hex_value(p[2]));
                p += 3;
                break;
            }
            return NULL;
        case 0:
            return NULL;
        default:
            *out++ = *p++;
            break;
        }
    }
    if (*p != '"')
        return NULL;
    *out = 0;
    return p + 1;
}

static char *parse_blob(char *p, Arg *arg)
{
    DWORD n = 0, i;
    char *start = ++p;
    while (hex_value(p[n * 2]) >= 0 && hex_value(p[n * 2 + 1]) >= 0)
        n++;
    if (n > MAX_BLOB)
        return NULL;
    arg->kind = 'b';
    arg->num = n;
    arg->ptr = mem_alloc(n);
    for (i = 0; i < n; i++)
        arg->ptr[i] = (char)(hex_value(start[i * 2]) * 16 + hex_value(start[i * 2 + 1]));
    return start + n * 2;
}

static char *parse_outbuf(char *p, Arg *arg)
{
    p++;
    arg->kind = 'b';
    arg->num = parse_number(&p);
    if (arg->num > MAX_BLOB)
        return NULL;
    arg->ptr = mem_alloc(arg->num);
    return p;
}

static void job_free(Job *job)
{
    int i;
    for (i = 0; i < job->argc; i++)
        if (job->args[i].kind == 'b')
            mem_free(job->args[i].ptr);
    mem_free(job->line);
    mem_free(job);
}

/* Takes ownership of line whether it succeeds or not. */
static Job *job_parse(char *line)
{
    Job *job = mem_alloc(sizeof *job);
    char *p = line;
    job->line = line;
    job->id = parse_number(&p);
    p = skip_spaces(p);
    job->verb = p;
    p = skip_spaces(cut_token(p));
    while (*p) {
        Arg *arg;
        if (job->argc == MAX_ARGS) {
            reply_error(job->id, "BADARG", "too many arguments");
            job_free(job);
            return NULL;
        }
        arg = &job->args[job->argc++];
        if (*p == '"') {
            p = parse_string(p, arg);
        } else if (*p == '#') {
            p = parse_blob(p, arg);
        } else if (*p == '&') {
            p = parse_outbuf(p, arg);
        } else {
            arg->kind = 'i';
            arg->num = parse_number(&p);
        }
        if (!p || (*p && *p != ' ')) {
            reply_error(job->id, "BADARG", "malformed argument");
            job_free(job);
            return NULL;
        }
        p = skip_spaces(p);
    }
    return job;
}

static DWORD arg_num(Job *job, int i, DWORD fallback)
{
    return i < job->argc && job->args[i].kind == 'i' ? job->args[i].num : fallback;
}

static int arg_is(Job *job, int i, char kind)
{
    return i < job->argc && job->args[i].kind == kind;
}

/* ---- CALL ---- */

/* Pushes args right to left and calls. Restoring ESP afterwards means the same
 * path works for stdcall and for cdecl functions like wsprintfA. */
static DWORD invoke(FARPROC fn, int n, const DWORD *a)
{
    DWORD result, ecx, edx;
    __asm__ volatile(
        "movl %%esp, %%esi\n"
        "1:\n"
        "testl %%ecx, %%ecx\n"
        "jz 2f\n"
        "decl %%ecx\n"
        "pushl (%%edx, %%ecx, 4)\n"
        "jmp 1b\n"
        "2:\n"
        "calll *%%eax\n"
        "movl %%esi, %%esp\n"
        : "=a"(result), "=c"(ecx), "=d"(edx)
        : "a"(fn), "c"(n), "d"(a)
        : "esi", "memory", "cc");
    (void)ecx;
    (void)edx;
    return result;
}

static void perform_call(Job *job, const char *head)
{
    DWORD values[MAX_ARGS];
    HMODULE module;
    FARPROC fn;
    DWORD result, last_error;
    Buf b;
    int i, n = job->argc - 2;

    if (n < 0 || !arg_is(job, 0, 's') || !arg_is(job, 1, 's')) {
        reply_error(job->id, "BADARG", "CALL needs dll and function names");
        return;
    }
    module = LoadLibraryA(job->args[0].ptr);
    if (!module) {
        reply_error(job->id, "NODLL", job->args[0].ptr);
        return;
    }
    fn = GetProcAddress(module, job->args[1].ptr);
    if (!fn) {
        reply_error(job->id, "NOFUNC", job->args[1].ptr);
        return;
    }
    for (i = 0; i < n; i++) {
        Arg *arg = &job->args[i + 2];
        values[i] = arg->kind == 'i' ? arg->num : (DWORD)arg->ptr;
    }
    SetLastError(0);
    result = invoke(fn, n, values);
    last_error = GetLastError();

    memset(&b, 0, sizeof b);
    if (head) {
        buf_str(&b, head);
        buf_num(&b, job->id);
    } else {
        reply_start(&b, job->id, "OK");
    }
    buf_num(&b, result);
    buf_num(&b, last_error);
    for (i = 2; i < job->argc; i++)
        if (job->args[i].kind == 'b')
            buf_blob(&b, job->args[i].ptr, job->args[i].num);
    send_buf(&b);
}

/* Anything that may block, such as a modal dialog, goes through ACALL. */
static DWORD WINAPI async_call_thread(LPVOID param)
{
    Job *job = param;
    perform_call(job, "! DONE");
    job_free(job);
    return 0;
}

/* ---- verbs that cannot be proxied ---- */

typedef struct {
    DWORD id;
    int count;
} EnumState;

static BOOL CALLBACK emit_window(HWND hwnd, LPARAM param)
{
    EnumState *state = (EnumState *)param;
    char title[256], cls[128];
    RECT r;
    DWORD pid = 0;
    Buf b;

    if (hwnd == request_window)
        return TRUE;
    title[0] = cls[0] = 0;
    GetWindowTextA(hwnd, title, sizeof title);
    GetClassNameA(hwnd, cls, sizeof cls);
    GetWindowRect(hwnd, &r);
    GetWindowThreadProcessId(hwnd, &pid);

    reply_start(&b, state->id, "+");
    buf_num(&b, (DWORD)hwnd);
    buf_num(&b, pid);
    buf_num(&b, IsWindowVisible(hwnd) ? 1 : 0);
    buf_num(&b, (DWORD)r.left);
    buf_num(&b, (DWORD)r.top);
    buf_num(&b, (DWORD)r.right);
    buf_num(&b, (DWORD)r.bottom);
    buf_quoted(&b, cls);
    buf_quoted(&b, title);
    send_buf(&b);
    state->count++;
    return TRUE;
}

static void verb_windows(Job *job)
{
    EnumState state;
    HWND parent = (HWND)arg_num(job, 0, 0);
    state.id = job->id;
    state.count = 0;
    if (parent)
        EnumChildWindows(parent, emit_window, (LPARAM)&state);
    else
        EnumWindows(emit_window, (LPARAM)&state);
    reply_ok(job->id, (DWORD)state.count);
}

static void verb_procs(Job *job)
{
    PROCESSENTRY32 entry;
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    DWORD count = 0;
    BOOL more;

    if (snap == INVALID_HANDLE_VALUE) {
        reply_error(job->id, "SYS", "CreateToolhelp32Snapshot failed");
        return;
    }
    entry.dwSize = sizeof entry;
    for (more = Process32First(snap, &entry); more; more = Process32Next(snap, &entry)) {
        Buf b;
        reply_start(&b, job->id, "+");
        buf_num(&b, entry.th32ProcessID);
        buf_quoted(&b, entry.szExeFile);
        send_buf(&b);
        count++;
    }
    CloseHandle(snap);
    reply_ok(job->id, count);
}

static void verb_spawn(Job *job)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    Buf b;

    if (!arg_is(job, 0, 's')) {
        reply_error(job->id, "BADARG", "SPAWN needs a command line");
        return;
    }
    memset(&si, 0, sizeof si);
    si.cb = sizeof si;
    if (!CreateProcessA(NULL, job->args[0].ptr, NULL, NULL, FALSE, 0, NULL,
                        arg_is(job, 1, 's') ? job->args[1].ptr : NULL, &si, &pi)) {
        reply_error(job->id, "SPAWN", job->args[0].ptr);
        return;
    }
    reply_start(&b, job->id, "OK");
    buf_num(&b, pi.dwProcessId);
    buf_num(&b, pi.dwThreadId);
    send_buf(&b);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
}

/* Returns once a window has repainted and drained its queue, so a capture
 * taken afterwards shows the frame the host just asked for. Painting another
 * process's window happens in that process, hence the WM_NULL round trip. */
static void settle_window(HWND hwnd, DWORD timeout_ms)
{
    DWORD unused;
    RedrawWindow(hwnd, NULL, NULL, RDW_UPDATENOW | RDW_ALLCHILDREN);
    SendMessageTimeoutA(hwnd, WM_NULL, 0, 0, SMTO_ABORTIFHUNG, timeout_ms, &unused);
}

static BOOL CALLBACK settle_each(HWND hwnd, LPARAM timeout_ms)
{
    if (IsWindowVisible(hwnd))
        settle_window(hwnd, (DWORD)timeout_ms);
    return TRUE;
}

static void verb_sync(Job *job)
{
    HWND hwnd = (HWND)arg_num(job, 0, 0);
    DWORD timeout_ms = arg_num(job, 1, 500);
    if (hwnd)
        settle_window(hwnd, timeout_ms);
    else
        EnumWindows(settle_each, (LPARAM)timeout_ms);
    GdiFlush();
    reply_ok(job->id, GetTickCount());
}

static void verb_put(Job *job)
{
    HANDLE file;
    DWORD offset = arg_num(job, 1, 0), written = 0;

    if (!arg_is(job, 0, 's') || !arg_is(job, 2, 'b')) {
        reply_error(job->id, "BADARG", "PUT needs path, offset and data");
        return;
    }
    file = CreateFileA(job->args[0].ptr, GENERIC_WRITE, 0, NULL,
                       offset ? OPEN_EXISTING : CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        reply_error(job->id, "FILE", job->args[0].ptr);
        return;
    }
    SetFilePointer(file, (LONG)offset, NULL, FILE_BEGIN);
    WriteFile(file, job->args[2].ptr, job->args[2].num, &written, NULL);
    CloseHandle(file);
    reply_ok(job->id, written);
}

static void verb_get(Job *job)
{
    HANDLE file;
    DWORD offset = arg_num(job, 1, 0), want = arg_num(job, 2, MAX_BLOB), got = 0;
    char *data;
    Buf b;

    if (!arg_is(job, 0, 's') || want > MAX_BLOB) {
        reply_error(job->id, "BADARG", "GET needs path, offset and a sane length");
        return;
    }
    file = CreateFileA(job->args[0].ptr, GENERIC_READ, FILE_SHARE_READ, NULL,
                       OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        reply_error(job->id, "FILE", job->args[0].ptr);
        return;
    }
    data = mem_alloc(want);
    SetFilePointer(file, (LONG)offset, NULL, FILE_BEGIN);
    ReadFile(file, data, want, &got, NULL);
    reply_start(&b, job->id, "OK");
    buf_num(&b, GetFileSize(file, NULL));
    buf_blob(&b, data, got);
    send_buf(&b);
    mem_free(data);
    CloseHandle(file);
}

static int verb_is(Job *job, const char *name)
{
    return lstrcmpA(job->verb, name) == 0;
}

static void handle_line(char *line)
{
    Job *job = job_parse(line);
    if (!job)
        return;

    if (verb_is(job, "ACALL")) {
        DWORD tid;
        reply_ok(job->id, job->id);
        if (CreateThread(NULL, 0, async_call_thread, job, 0, &tid))
            return; /* the thread owns the job now */
    } else if (verb_is(job, "PING")) {
        Buf b;
        reply_start(&b, job->id, "OK");
        buf_num(&b, GetTickCount());
        buf_num(&b, PROTOCOL_VERSION);
        send_buf(&b);
    } else if (verb_is(job, "CALL")) {
        perform_call(job, NULL);
    } else if (verb_is(job, "WINDOWS")) {
        verb_windows(job);
    } else if (verb_is(job, "PROCS")) {
        verb_procs(job);
    } else if (verb_is(job, "SPAWN")) {
        verb_spawn(job);
    } else if (verb_is(job, "SYNC")) {
        verb_sync(job);
    } else if (verb_is(job, "PUT")) {
        verb_put(job);
    } else if (verb_is(job, "GET")) {
        verb_get(job);
    } else if (verb_is(job, "QUIT")) {
        reply_ok(job->id, 0);
        ExitProcess(0);
    } else {
        reply_error(job->id, "BADVERB", job->verb);
    }
    job_free(job);
}

/* ---- serial input ---- */

static int frame_valid(char *line, DWORD *len)
{
    DWORD n = *len;
    WORD want = 0;
    int i;

    if (n < 6 || line[n - 6] != ' ' || line[n - 5] != '*')
        return 0;
    for (i = 4; i > 0; i--) {
        int digit = hex_value(line[n - i]);
        if (digit < 0)
            return 0;
        want = (WORD)(want * 16 + digit);
    }
    if (crc16(line, n - 6) != want)
        return 0;
    line[n - 6] = 0;
    *len = n - 6;
    return 1;
}

/* Hands a complete line to the window thread, which owns it from then on. */
static void deliver_line(const char *data, DWORD len)
{
    char *line = mem_alloc(len + 1);
    Buf b;

    memcpy(line, data, len);
    if (!frame_valid(line, &len)) {
        mem_free(line);
        memset(&b, 0, sizeof b);
        buf_str(&b, "! BADFRAME");
        send_buf(&b);
        return;
    }
    seen_request = 1;
    PostMessageA(request_window, WM_REQUEST, 0, (LPARAM)line);
}

static DWORD WINAPI reader_thread(LPVOID unused)
{
    static char line[MAX_LINE];
    char chunk[512];
    DWORD fill = 0;
    int overflowed = 0;
    OVERLAPPED ov;

    (void)unused;
    memset(&ov, 0, sizeof ov);
    ov.hEvent = CreateEventA(NULL, TRUE, FALSE, NULL);
    for (;;) {
        DWORD got = 0, i;
        ResetEvent(ov.hEvent);
        if (!ReadFile(com, chunk, sizeof chunk, &got, &ov)) {
            if (GetLastError() != ERROR_IO_PENDING) {
                Sleep(100);
                continue;
            }
            GetOverlappedResult(com, &ov, &got, TRUE);
        }
        if (!got)
            Sleep(READ_POLL_MS);
        for (i = 0; i < got; i++) {
            if (chunk[i] == '\n') {
                if (!overflowed)
                    deliver_line(line, fill);
                fill = 0;
                overflowed = 0;
            } else if (fill == MAX_LINE) {
                overflowed = 1;
            } else {
                line[fill++] = chunk[i];
            }
        }
    }
    return 0;
}

static LRESULT CALLBACK request_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_REQUEST) {
        handle_line((char *)lp);
        return 0;
    }
    if (msg == WM_TIMER) {
        /* Keep announcing until the host has actually spoken to us. */
        if (seen_request)
            KillTimer(hwnd, HELLO_TIMER);
        else
            send_event_hello();
        return 0;
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

/* ---- startup ---- */

static int open_com(const char *name)
{
    COMMTIMEOUTS timeouts;
    DCB dcb;
    int attempt;

    /* The port stays busy briefly when we are restarted after a crash. */
    for (attempt = 0; attempt < 100; attempt++) {
        com = CreateFileA(name, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING,
                          FILE_FLAG_OVERLAPPED, NULL);
        if (com != INVALID_HANDLE_VALUE)
            break;
        Sleep(100);
    }
    if (com == INVALID_HANDLE_VALUE)
        return 0;

    SetupComm(com, MAX_LINE, MAX_LINE);
    memset(&dcb, 0, sizeof dcb);
    dcb.DCBlength = sizeof dcb;
    GetCommState(com, &dcb);
    dcb.BaudRate = CBR_115200;
    dcb.ByteSize = 8;
    dcb.Parity = NOPARITY;
    dcb.StopBits = ONESTOPBIT;
    dcb.fBinary = TRUE;
    dcb.fParity = FALSE;
    dcb.fOutxCtsFlow = FALSE;
    dcb.fOutxDsrFlow = FALSE;
    dcb.fDtrControl = DTR_CONTROL_ENABLE;
    dcb.fRtsControl = RTS_CONTROL_ENABLE;
    dcb.fOutX = FALSE;
    dcb.fInX = FALSE;
    SetCommState(com, &dcb);

    /* Reads return at once with whatever has arrived; the reader polls. */
    timeouts.ReadIntervalTimeout = MAXDWORD;
    timeouts.ReadTotalTimeoutMultiplier = 0;
    timeouts.ReadTotalTimeoutConstant = 0;
    timeouts.WriteTotalTimeoutMultiplier = 0;
    timeouts.WriteTotalTimeoutConstant = 0;
    SetCommTimeouts(com, &timeouts);
    return 1;
}

/* A proxied call is free to crash, and sometimes that is the performance.
 * Report it and come back rather than leaving the host talking to nobody. */
static LONG WINAPI on_crash(EXCEPTION_POINTERS *info)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    char self[MAX_PATH];
    Buf b;

    memset(&b, 0, sizeof b);
    buf_str(&b, "! CRASH");
    buf_num(&b, info->ExceptionRecord->ExceptionCode);
    buf_num(&b, (DWORD)info->ExceptionRecord->ExceptionAddress);
    send_buf(&b);

    CloseHandle(com);
    memset(&si, 0, sizeof si);
    si.cb = sizeof si;
    GetModuleFileNameA(NULL, self, sizeof self);
    if (CreateProcessA(self, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
    ExitProcess(1);
    return EXCEPTION_EXECUTE_HANDLER;
}

void entry(void)
{
    WNDCLASSA wc;
    MSG msg;
    DWORD tid;

    heap = GetProcessHeap();
    InitializeCriticalSection(&tx_lock);
    SetUnhandledExceptionFilter(on_crash);

    memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = request_proc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "Art98Agent";
    RegisterClassA(&wc);
    request_window = CreateWindowExA(0, "Art98Agent", "", WS_POPUP, 0, 0, 0, 0, NULL, NULL,
                                     wc.hInstance, NULL);

    if (!open_com("COM1"))
        ExitProcess(2);

    send_event_hello();
    SetTimer(request_window, HELLO_TIMER, HELLO_INTERVAL_MS, NULL);
    CreateThread(NULL, 0, reader_thread, NULL, 0, &tid);

    while (GetMessageA(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
    ExitProcess(0);
}
