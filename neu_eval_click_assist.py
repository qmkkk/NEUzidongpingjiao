import ctypes
import json
import sys
import time
from pathlib import Path


VK_F8 = 0x77
VK_MENU = 0x12
VK_LEFT = 0x25
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

LIST_TITLE_HINTS = [
    "学生阶段评价二级页面",
    "学生阶段评价",
    "学生评价",
    "阶段评价",
    "教学质量监控与评价平台",
]
DETAIL_TITLE_HINTS = [
    "阶段评详情",
    "评价详情",
    "详情",
]

CONFIG_PATH = Path(__file__).with_name("neu_eval_click_assist_config.json")
CONFIG_VERSION = 2

user32 = ctypes.windll.user32


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_cursor_pos():
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))


def mouse_left_click(x, y, settle=0.08):
    set_cursor_pos(x, y)
    time.sleep(settle)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def key_tap(vk_code):
    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def alt_left():
    user32.keybd_event(VK_MENU, 0, 0, 0)
    time.sleep(0.03)
    key_tap(VK_LEFT)
    time.sleep(0.03)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def get_foreground_title():
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def title_contains_any(title, hints):
    return any(hint and hint in title for hint in hints)


def wait_for_title_contains_any(hints, timeout=15, interval=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        title = get_foreground_title()
        if title_contains_any(title, hints):
            return True
        time.sleep(interval)
    return False


def wait_until_left_detail_page(timeout=12, interval=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        title = get_foreground_title()
        if title_contains_any(title, LIST_TITLE_HINTS):
            return True
        if not title_contains_any(title, DETAIL_TITLE_HINTS):
            return True
        time.sleep(interval)
    return False


def wait_for_f8(prompt):
    print()
    print(prompt)
    print("Move the mouse to the target, then press F8.")
    last_state = False
    while True:
        pressed = bool(user32.GetAsyncKeyState(VK_F8) & 0x8000)
        if pressed and not last_state:
            x, y = get_cursor_pos()
            print(f"Recorded: ({x}, {y})")
            while bool(user32.GetAsyncKeyState(VK_F8) & 0x8000):
                time.sleep(0.05)
            return {"x": x, "y": y}
        last_state = pressed
        time.sleep(0.05)


def load_config():
    if not CONFIG_PATH.exists():
        return None
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if data.get("config_version") != CONFIG_VERSION:
        return None
    if "score_points" not in data:
        return None
    return data


def save_config(config):
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def calibrate():
    print("Start calibration.")
    print("Keep the browser size the same as later runs, preferably maximized.")
    print("Before running, manually switch the list to pending items only.")

    count_text = input("How many score rows are on the detail page? Default 10: ").strip()
    row_count = int(count_text) if count_text else 10

    config = {
        "config_version": CONFIG_VERSION,
        "score_row_count": row_count,
        "list_eval": wait_for_f8(
            "1. On the list page, move to the first pending row's '评价' button."
        ),
        "score_points": [],
    }

    print()
    print("Open any evaluation detail page manually before the next steps.")
    input("Press Enter when the detail page is visible...")

    for row_index in range(row_count):
        target_score = 5 if row_index == 0 else 6
        point = wait_for_f8(
            f"{row_index + 2}. Move to row {row_index + 1} score {target_score}."
        )
        config["score_points"].append(
            {
                "row": row_index + 1,
                "score": target_score,
                "point": point,
            }
        )

    config["detail_submit"] = wait_for_f8(
        f"{row_count + 2}. Move to the detail page submit button."
    )
    config["detail_confirm"] = wait_for_f8(
        f"{row_count + 3}. If a confirm dialog appears, move to its confirm button."
    )

    save_config(config)

    print()
    print(f"Saved calibration to: {CONFIG_PATH}")
    return config


def countdown(seconds):
    for remaining in range(seconds, 0, -1):
        print(f"{remaining}...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 20, end="\r", flush=True)


def click_point(point):
    mouse_left_click(point["x"], point["y"])


def fill_scores(config):
    score_points = config.get("score_points") or []
    expected_count = int(config["score_row_count"])
    if len(score_points) != expected_count:
        raise RuntimeError("Calibration is incomplete. Please recalibrate all score points.")

    for item in score_points:
        click_point(item["point"])
        time.sleep(0.10)


def submit_detail(config):
    click_point(config["detail_submit"])
    time.sleep(1.0)
    click_point(config["detail_confirm"])
    time.sleep(2.0)


def process_once(config, index, total):
    print()
    print(f"Processing {index}/{total} ...")
    click_point(config["list_eval"])

    if not wait_for_title_contains_any(DETAIL_TITLE_HINTS, timeout=12):
        print("Detail page title not detected. Continue after a fixed wait.")
        time.sleep(2.5)

    time.sleep(1.0)
    fill_scores(config)
    time.sleep(0.4)
    submit_detail(config)

    if wait_until_left_detail_page(timeout=10):
        print("Left detail page and ready for the next course.")
        return

    print("List page not detected. Try Alt+Left.")
    alt_left()
    if not wait_until_left_detail_page(timeout=8):
        raise RuntimeError("Failed to return to the list page. Please check the browser.")


def run():
    config = load_config()
    if config is None:
        print("No usable calibration found. A full recalibration is required.")
        config = calibrate()

    print()
    print("Usage:")
    print("1. Log in manually.")
    print("2. Open the student evaluation list page.")
    print("3. Filter to pending items if possible.")
    print("4. Keep the browser window size the same as calibration.")
    print()

    total_text = input("How many courses should be processed this time? Default 1: ").strip()
    total = int(total_text) if total_text else 1

    reset_text = input("Recalibrate coordinates? Enter y to recalibrate: ").strip().lower()
    if reset_text == "y":
        config = calibrate()

    print()
    print("Bring the browser to the front and stay on the pending list page.")
    print("Starting in 5 seconds.")
    countdown(5)

    for index in range(1, total + 1):
        process_once(config, index, total)
        time.sleep(1.2)

    print()
    print("Done.")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"\nScript failed: {exc}")
        sys.exit(2)
