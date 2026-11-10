/* view.c - the art98 picture window.
 *
 * A plain Windows 98 window that shows one BMP at 1:1, centred, on grey. It
 * stands in for a real image viewer, which Windows 98 doesn't have. Each
 * window is its own process.
 *
 *     VIEW.EXE <x> <y> <width> <height> "<title>" ["<image.bmp>"]
 *
 * The window opens where it is told, so the host never has to move it off
 * the default position. It exits with code 3, without a window, if the image
 * can't be loaded, and 2 if the command line is wrong.
 *
 * LoadImage on Windows 98 can crash on a cut-short file. The fault happens in
 * 16-bit code, where an unhandled exception filter never sees it, so Windows
 * shows its "illegal operation" dialog and the process stays alive. The host
 * checks every image before copying it, which is what prevents this.
 */

#define WIN32_LEAN_AND_MEAN
#define WINVER 0x0400
#define _WIN32_WINDOWS 0x0410
#include <windows.h>

#define CLASS_NAME "Art98View"
#define MAX_TEXT 260

static HBITMAP picture;
static int picture_w, picture_h;

void *memset(void *dst, int c, size_t n)
{
    unsigned char *d = dst;
    while (n--)
        *d++ = (unsigned char)c;
    return dst;
}

/* Copies the next argument into out, unquoting it, and returns what follows. */
static const char *next_arg(const char *p, char *out, int cap)
{
    int n = 0;
    while (*p == ' ' || *p == '\t')
        p++;
    if (!*p)
        return NULL;
    if (*p == '"') {
        p++;
        while (*p && *p != '"') {
            if (n < cap - 1)
                out[n++] = *p;
            p++;
        }
        if (*p == '"')
            p++;
    } else {
        while (*p && *p != ' ' && *p != '\t') {
            if (n < cap - 1)
                out[n++] = *p;
            p++;
        }
    }
    out[n] = 0;
    return p;
}

static BOOL parse_int(const char *s, int *value)
{
    int sign = 1, v = 0;
    if (*s == '-') {
        sign = -1;
        s++;
    }
    if (!*s)
        return FALSE;
    for (; *s; s++) {
        if (*s < '0' || *s > '9')
            return FALSE;
        v = v * 10 + (*s - '0');
    }
    *value = sign * v;
    return TRUE;
}

static void paint(HWND hwnd)
{
    PAINTSTRUCT ps;
    RECT client;
    HDC dc = BeginPaint(hwnd, &ps);
    if (picture) {
        HDC mem = CreateCompatibleDC(dc);
        HGDIOBJ old = SelectObject(mem, picture);
        GetClientRect(hwnd, &client);
        BitBlt(dc, (client.right - picture_w) / 2, (client.bottom - picture_h) / 2,
               picture_w, picture_h, mem, 0, 0, SRCCOPY);
        SelectObject(mem, old);
        DeleteDC(mem);
    }
    EndPaint(hwnd, &ps);
}

static LRESULT CALLBACK view_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_PAINT:
        paint(hwnd);
        return 0;
    case WM_SIZE:
        /* The picture stays centred, so all of it moves when the size changes. */
        InvalidateRect(hwnd, NULL, TRUE);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

void entry(void)
{
    char arg[MAX_TEXT], title[MAX_TEXT], image[MAX_TEXT];
    int geometry[4], i;
    const char *p = GetCommandLineA();
    WNDCLASSA wc;
    MSG msg;
    HWND hwnd;

    p = next_arg(p, arg, sizeof arg); /* the program itself */
    for (i = 0; i < 4; i++) {
        if (!p || !(p = next_arg(p, arg, sizeof arg)) || !parse_int(arg, &geometry[i]))
            ExitProcess(2);
    }
    if (!(p = next_arg(p, title, sizeof title)))
        ExitProcess(2);
    image[0] = 0;
    next_arg(p, image, sizeof image);

    if (image[0]) {
        BITMAP info;
        picture = (HBITMAP)LoadImageA(NULL, image, IMAGE_BITMAP, 0, 0, LR_LOADFROMFILE);
        if (!picture || !GetObjectA(picture, sizeof info, &info))
            ExitProcess(3);
        picture_w = info.bmWidth;
        picture_h = info.bmHeight;
    }

    memset(&wc, 0, sizeof wc);
    wc.lpfnWndProc = view_proc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.hIcon = LoadIconA(NULL, IDI_APPLICATION);
    wc.hCursor = LoadCursorA(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = CLASS_NAME;
    RegisterClassA(&wc);

    hwnd = CreateWindowExA(0, CLASS_NAME, title, WS_OVERLAPPEDWINDOW,
                           geometry[0], geometry[1], geometry[2], geometry[3],
                           NULL, NULL, wc.hInstance, NULL);
    if (!hwnd)
        ExitProcess(4);
    ShowWindow(hwnd, SW_SHOWNORMAL);
    UpdateWindow(hwnd);

    while (GetMessageA(&msg, NULL, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
    ExitProcess(0);
}
