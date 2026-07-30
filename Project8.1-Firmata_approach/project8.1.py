"""
LED timer controller GUI using Telemetrix (FirmataExpress).

Talks to an Arduino running FirmataExpress:
- Listens for button pin changes via asynchronous callbacks.
- Controls the LED digital pin directly and runs the off-timer in Python.
- Pushes state codes (0, 1, 2) into the GUI message queue.
"""

import queue
import threading
import time
from datetime import datetime

import FreeSimpleGUI as sg
import serial.tools.list_ports
from telemetrix import telemetrix

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BUTTON_PIN = 2          # Pin connected to push button (Internal Pullup)
LED_PIN = 4            # Pin connected to LED
GUI_POLL_MS = 100       # How often the GUI loop drains the queue

STATE_MESSAGES = {
    "0": "LED off (timer expired)",
    "1": "Button pressed - LED on",
    "2": "Button released",
}

# --- look & feel ----------------------------------------------------------- #
THEME = "DarkGrey13"
FONT        = ("Segoe UI", 10)
FONT_BOLD   = ("Segoe UI", 10, "bold")
FONT_TITLE  = ("Segoe UI", 15, "bold")
FONT_LABEL  = ("Segoe UI", 9)

LED_ON  = ("#ff1e1e", "#ff5a5a", "#990000", "#4d0000", "#ffd2d2")
LED_OFF = ("#3a0f0f", "#521515", "#4a1414")
BTN_BASE   = "#0f1116"
BTN_SIDE   = "#1f2d3d"
BTN_TOP    = "#34495e"
BTN_HILITE = "#405973"
BTN_TOP_DN = "#2b3d51"
BTN_HL_DN  = "#324a63"


# --------------------------------------------------------------------------- #
# Telemetrix Backend Worker
# --------------------------------------------------------------------------- #

class TelemetrixWorker:
    """Manages Telemetrix connection, pin callbacks, and off-timer thread."""

    def __init__(self, message_queue):
        self._queue = message_queue
        self._board = None
        self._timer_duration_ms = 5000  # Default 5 seconds
        self._off_timer = None

    @property
    def is_connected(self):
        return self._board is not None

    def connect(self, com_port):
        """Initialize Telemetrix connection and pin modes."""
        if self.is_connected:
            return False, "Already connected."

        try:
            # Connect to Arduino running FirmataExpress
            self._board = telemetrix.Telemetrix(com_port=com_port)

            # Configure LED pin
            self._board.set_pin_mode_digital_output(LED_PIN)
            self._board.digital_write(LED_PIN, 0)

            # Configure Button pin with Pullup & callback
            self._board.set_pin_mode_digital_input_pullup(
                BUTTON_PIN, callback=self._button_callback
            )

            return True, f"Connected to {com_port} via Telemetrix."

        except Exception as exc:
            self.disconnect()
            return False, f"Could not open {com_port}: {exc}"

    def disconnect(self):
        """Cancel timers and shutdown Telemetrix connection safely."""
        self._cancel_timer()
        if self._board is not None:
            try:
                self._board.digital_write(LED_PIN, 0)
                self._board.shutdown()
            except Exception:
                pass
            self._board = None

    def set_duration(self, milliseconds):
        """Update the active timer duration."""
        self._timer_duration_ms = milliseconds
        return True, f"Set timer duration to: {milliseconds} ms"

    def _cancel_timer(self):
        if self._off_timer is not None:
            self._off_timer.cancel()
            self._off_timer = None

    def _button_callback(self, data):
        """Triggered asynchronously by Telemetrix on pin level change."""
        # data structure: [pin_type, pin_number, pin_value, timestamp]
        pin_number, pin_value = data[1], data[2]

        if pin_number == BUTTON_PIN:
            # Active-low with input_pullDOWN: 1 = Pressed, 0 = Released
            if pin_value == 1:
                self._cancel_timer()
                if self._board:
                    self._board.digital_write(LED_PIN, 1)  # Turn LED ON
                
                # Report state '1' to GUI
                self._queue.put(("device", "1"))

                # Schedule turning off after duration expires
                delay_seconds = self._timer_duration_ms / 1000.0
                self._off_timer = threading.Timer(delay_seconds, self._handle_timer_expired)
                self._off_timer.start()

            elif pin_value == 0:
                # Report state '2' to GUI (LED stays ON until timer completes)
                self._queue.put(("device", "2"))

    def _handle_timer_expired(self):
        """Called when duration timer finishes."""
        if self._board:
            self._board.digital_write(LED_PIN, 0)  # Turn LED OFF
        # Report state '0' to GUI
        self._queue.put(("device", "0"))


# --------------------------------------------------------------------------- #
# Graphical indicators
# --------------------------------------------------------------------------- #

def draw_led(graph, on):
    graph.erase()
    cx, cy = 70, 70
    if on:
        core, inner, mid, glow, spec = LED_ON
        graph.draw_circle((cx, cy), 55, fill_color=glow,  line_color=glow)
        graph.draw_circle((cx, cy), 46, fill_color=mid,   line_color=mid)
        graph.draw_circle((cx, cy), 36, fill_color=core,  line_color=core)
        graph.draw_circle((cx, cy), 25, fill_color=inner, line_color=inner)
        graph.draw_circle((cx - 9, cy + 9), 8, fill_color=spec, line_color=spec)
    else:
        body, rim, spec = LED_OFF
        graph.draw_circle((cx, cy), 36, fill_color=body, line_color=rim)
        graph.draw_circle((cx - 9, cy + 9), 7, fill_color=spec, line_color=spec)


def draw_button(graph, pressed):
    graph.erase()
    cx = 70
    graph.draw_circle((cx, 66), 50, fill_color=BTN_BASE, line_color=BTN_BASE)
    if pressed:
        graph.draw_circle((cx, 67), 42, fill_color=BTN_TOP_DN, line_color=BTN_SIDE)
        graph.draw_circle((cx, 68), 30, fill_color=BTN_HL_DN,  line_color=BTN_HL_DN)
    else:
        graph.draw_circle((cx, 62), 42, fill_color=BTN_SIDE, line_color=BTN_SIDE)
        graph.draw_circle((cx, 72), 42, fill_color=BTN_TOP,  line_color=BTN_TOP)
        graph.draw_circle((cx, 76), 30, fill_color=BTN_HILITE, line_color=BTN_HILITE)


def set_visual_state(window, *, led=None, pressed=None):
    if led is not None:
        draw_led(window["-LED-"], led)
    if pressed is not None:
        draw_button(window["-BTN-"], pressed)


# --------------------------------------------------------------------------- #
# GUI Setup & Event Loop
# --------------------------------------------------------------------------- #

def list_serial_ports():
    try:
        return [port.device for port in serial.tools.list_ports.comports()]
    except Exception:
        return []


def build_window():
    sg.theme(THEME)
    bg = sg.theme_background_color()

    header = [sg.Text("Arduino LED Timer (Telemetrix)", font=FONT_TITLE, pad=((0, 0), (4, 10)))]

    connection_row = [
        sg.Text("Port:", font=FONT),
        sg.Combo(list_serial_ports(), size=(24, 1), key="-PORT-", readonly=False, font=FONT),
        sg.Button("Refresh", key="-REFRESH-"),
        sg.Button("Connect", key="-CONNECT-", button_color=("#ffffff", "#2d6a4f")),
        sg.Button("Disconnect", key="-DISCONNECT-", disabled=True, button_color=("#ffffff", "#7f1d1d")),
    ]

    btn_col = sg.Column(
        [[sg.Graph((140, 140), (0, 0), (140, 140), key="-BTN-", background_color=bg, pad=(0, 0))],
         [sg.Text("BUTTON", font=FONT_LABEL, text_color="#8b95a5")]],
        element_justification="center", background_color=bg,
    )
    led_col = sg.Column(
        [[sg.Graph((140, 140), (0, 0), (140, 140), key="-LED-", background_color=bg, pad=(0, 0))],
         [sg.Text("LED", font=FONT_LABEL, text_color="#8b95a5")]],
        element_justification="center", background_color=bg,
    )

    visual_frame = [
        sg.Frame(
            "",
            [[sg.Push(background_color=bg), btn_col,
              sg.Text("", size=(4, 1), background_color=bg),
              led_col, sg.Push(background_color=bg)]],
            expand_x=True, relief=sg.RELIEF_FLAT, background_color=bg,
            pad=((0, 0), (4, 8)),
        )
    ]

    timer_row = [
        sg.Text("LED on-time (ms):", font=FONT),
        sg.Input("5000", size=(12, 1), key="-DURATION-", font=FONT),
        sg.Button("Set Timer", key="-SEND-", bind_return_key=True, button_color=("#0b0f14", "#4da3ff")),
    ]

    response_row = [
        sg.Multiline(
            size=(62, 14), key="-RESPONSE-", autoscroll=True, disabled=True,
            reroute_stdout=False, font=("Consolas", 9), background_color="#15171c",
            text_color="#cfd6e0", border_width=0,
        )
    ]

    layout = [
        header,
        connection_row,
        [sg.HorizontalSeparator()],
        visual_frame,
        timer_row,
        [sg.Text("Device responses:", font=FONT_LABEL, pad=((0, 0), (6, 0)))],
        response_row,
        [
            sg.Text("Disconnected", key="-STATUS-", size=(46, 1), font=FONT),
            sg.Push(),
            sg.Button("Clear", key="-CLEAR-"),
            sg.Button("Exit", key="-EXIT-"),
        ],
    ]

    window = sg.Window("Arduino LED Timer", layout, finalize=True, element_justification="left")
    draw_button(window["-BTN-"], pressed=False)
    draw_led(window["-LED-"], on=False)
    return window


def log(window, text):
    window["-RESPONSE-"].print(f"[{datetime.now():%H:%M:%S}] {text}")


def parse_duration(raw_value):
    text = raw_value.strip()
    if not text:
        return None, "Please enter a timer value in milliseconds."
    try:
        value = int(float(text))
    except ValueError:
        return None, f"'{text}' is not a number."
    if value <= 0:
        return None, "The timer value must be greater than 0 ms."
    return value, None


def set_connected_state(window, connected, status_text):
    window["-CONNECT-"].update(disabled=connected)
    window["-DISCONNECT-"].update(disabled=not connected)
    window["-PORT-"].update(disabled=connected)
    window["-REFRESH-"].update(disabled=connected)
    window["-STATUS-"].update(status_text)


def handle_device_message(window, line):
    if line == "1":      # Pressed -> LED on
        set_visual_state(window, led=True, pressed=True)
    elif line == "2":    # Released -> LED remains on until timer expires
        set_visual_state(window, pressed=False)
    elif line == "0":    # Timer expired -> LED off
        set_visual_state(window, led=False)

    if line in STATE_MESSAGES:
        log(window, f"State {line}: {STATE_MESSAGES[line]}")


def main():
    message_queue = queue.Queue()
    worker = TelemetrixWorker(message_queue)
    window = build_window()

    log(window, "Select a serial port and press Connect.")

    try:
        while True:
            event, values = window.read(timeout=GUI_POLL_MS)

            if event in (sg.WIN_CLOSED, "-EXIT-"):
                break

            elif event == "-REFRESH-":
                ports = list_serial_ports()
                window["-PORT-"].update(values=ports, value=ports[0] if ports else "")
                log(window, f"Found {len(ports)} serial port(s).")

            elif event == "-CONNECT-":
                port_name = (values["-PORT-"] or "").strip()
                if not port_name:
                    log(window, "No port selected.")
                else:
                    ok, message = worker.connect(port_name)
                    log(window, message)
                    if ok:
                        set_connected_state(window, True, f"Connected: {port_name}")
                        set_visual_state(window, led=False, pressed=False)

            elif event == "-DISCONNECT-":
                worker.disconnect()
                set_connected_state(window, False, "Disconnected")
                set_visual_state(window, led=False, pressed=False)
                log(window, "Disconnected.")

            elif event == "-SEND-":
                duration, error = parse_duration(values["-DURATION-"])
                if error:
                    log(window, error)
                else:
                    ok, message = worker.set_duration(duration)
                    log(window, message)

            elif event == "-CLEAR-":
                window["-RESPONSE-"].update("")

            # Drain queue populated by Telemetrix callbacks
            while True:
                try:
                    kind, payload = message_queue.get_nowait()
                except queue.Empty:
                    break

                if kind == "device":
                    handle_device_message(window, payload)
                else:
                    log(window, payload)
                    worker.disconnect()
                    set_connected_state(window, False, "Disconnected (error)")
                    set_visual_state(window, led=False, pressed=False)

    except Exception as exc:
        sg.popup_error(f"Unexpected error: {exc}")

    finally:
        worker.disconnect()
        window.close()


if __name__ == "__main__":
    main()