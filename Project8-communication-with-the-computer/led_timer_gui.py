"""
LED timer controller GUI.

Talks to an Arduino over a serial port:
Sends a timer duration in milliseconds (newline terminated) that sets how
long the LED stays lit after the button is pressed.

The device reports its state as a single digit per line:
    0 -> timer expired  (LED off)
    1 -> button pressed  (LED on)
    2 -> button released
The GUI mirrors those states on a graphical button and LED.
"""

import queue # Used to pass messages from the serial-reading thread to the GUI
import threading # Lets the program run multiple tasks simultaneously (GUI + serial reading).
import time
from datetime import datetime # Used for timestamps in the log window.

import FreeSimpleGUI as sg # Imports the GUI library.
import serial
import serial.tools.list_ports # for Arduino communication and listing available COM ports.

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BAUD_RATE = 9600          # must match Serial.begin() in the sketch
READ_TIMEOUT = 0.5        # seconds; keeps the reader thread responsive
GUI_POLL_MS = 100         # how often the GUI loop wakes up to drain the queue
ARDUINO_RESET_DELAY = 2.0 # the board reboots when the port is opened

# Mapping of the numeric state codes sent by the device to readable text.
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

# Colors used by the graphical LED / button.
LED_ON  = ("#ff1e1e", "#ff5a5a", "#990000", "#4d0000", "#ffd2d2")  # core, inner, mid, glow, spec
LED_OFF = ("#3a0f0f", "#521515", "#4a1414")                         # body, rim, dim spec
BTN_BASE   = "#0f1116"
BTN_SIDE   = "#1f2d3d"
BTN_TOP    = "#34495e"
BTN_HILITE = "#405973"
BTN_TOP_DN = "#2b3d51"
BTN_HL_DN  = "#324a63"


# --------------------------------------------------------------------------- #
# Serial communication  (unchanged backend)
# --------------------------------------------------------------------------- #

class SerialWorker:
    """Owns the serial port and a background thread that reads from it.

    Incoming lines are pushed into a thread-safe queue that the GUI loop
    drains, so reading never blocks the interface.
    """

    def __init__(self, message_queue):
        self._queue = message_queue
        self._port = None
        self._thread = None
        self._stop_event = threading.Event()

    # -- state -------------------------------------------------------------- #

    @property
    def is_connected(self):
        return self._port is not None and self._port.is_open

    # -- connection management ---------------------------------------------- #

    def connect(self, port_name, baud_rate=BAUD_RATE):
        """Open the port and start the reader thread. Returns (ok, message)."""
        if self.is_connected:
            return False, "Already connected."

        try:
            self._port = serial.Serial(port_name, baud_rate, timeout=READ_TIMEOUT)
        except (serial.SerialException, ValueError, OSError) as exc:
            self._port = None
            return False, f"Could not open {port_name}: {exc}"

        # Opening the port resets most Arduino boards; wait for the bootloader
        # and drop whatever noise landed in the buffers during the reset.
        time.sleep(ARDUINO_RESET_DELAY)
        try:
            self._port.reset_input_buffer()
            self._port.reset_output_buffer()
        except (serial.SerialException, OSError):
            pass  # not fatal - the reader thread will report any real problem

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return True, f"Connected to {port_name} at {baud_rate} baud."

    def disconnect(self):
        """Stop the reader thread and close the port."""
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=2 * READ_TIMEOUT + 0.5)
            self._thread = None

        if self._port is not None:
            try:
                self._port.close()
            except (serial.SerialException, OSError):
                pass
            self._port = None

    # -- sending ------------------------------------------------------------ #

    def send_duration(self, milliseconds):
        """Send the timer value, newline terminated as the sketch expects."""
        if not self.is_connected:
            return False, "Not connected - open a port first."

        try:
            self._port.write(f"{milliseconds}\n".encode("ascii"))
            self._port.flush()
        except (serial.SerialException, OSError) as exc:
            return False, f"Send failed: {exc}"

        return True, f"Sent timer value: {milliseconds} ms"

    # -- reader thread ------------------------------------------------------- #

    def _read_loop(self):
        """Read one line at a time until asked to stop or the port dies."""
        while not self._stop_event.is_set():
            try:
                raw = self._port.readline()          # returns b"" on timeout
            except (serial.SerialException, OSError, TypeError) as exc:
                # Cable unplugged or port closed underneath us: report and exit.
                if not self._stop_event.is_set():
                    self._queue.put(("error", f"Connection lost: {exc}"))
                return

            if not raw:
                continue  # timeout, just loop again and re-check the stop flag

            # Ignore undecodable bytes instead of killing the thread over them.
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                self._queue.put(("device", line))


# --------------------------------------------------------------------------- #
# Graphical indicators (LED + button drawn on sg.Graph canvases)
# --------------------------------------------------------------------------- #

def draw_led(graph, on):
    """Draw the round LED. Neon red with a soft glow when on, dark when off."""
    graph.erase()
    cx, cy = 70, 70
    if on:
        core, inner, mid, glow, spec = LED_ON
        graph.draw_circle((cx, cy), 55, fill_color=glow,  line_color=glow)   # outer glow
        graph.draw_circle((cx, cy), 46, fill_color=mid,   line_color=mid)    # halo
        graph.draw_circle((cx, cy), 36, fill_color=core,  line_color=core)   # neon body
        graph.draw_circle((cx, cy), 25, fill_color=inner, line_color=inner)  # hot center
        graph.draw_circle((cx - 9, cy + 9), 8, fill_color=spec, line_color=spec)  # specular
    else:
        body, rim, spec = LED_OFF
        graph.draw_circle((cx, cy), 36, fill_color=body, line_color=rim)     # unlit body
        graph.draw_circle((cx - 9, cy + 9), 7, fill_color=spec, line_color=spec)


def draw_button(graph, pressed):
    """Draw the round push button, raised when idle and sunk when pressed."""
    graph.erase()
    cx = 70
    graph.draw_circle((cx, 66), 50, fill_color=BTN_BASE, line_color=BTN_BASE)  # socket
    if pressed:
        graph.draw_circle((cx, 67), 42, fill_color=BTN_TOP_DN, line_color=BTN_SIDE)  # cap dropped
        graph.draw_circle((cx, 68), 30, fill_color=BTN_HL_DN,  line_color=BTN_HL_DN)
    else:
        graph.draw_circle((cx, 62), 42, fill_color=BTN_SIDE, line_color=BTN_SIDE)    # raised wall
        graph.draw_circle((cx, 72), 42, fill_color=BTN_TOP,  line_color=BTN_TOP)     # top face
        graph.draw_circle((cx, 76), 30, fill_color=BTN_HILITE, line_color=BTN_HILITE)


def set_visual_state(window, *, led=None, pressed=None):
    """Update either indicator; pass only the ones that should change."""
    if led is not None:
        draw_led(window["-LED-"], led)
    if pressed is not None:
        draw_button(window["-BTN-"], pressed)


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #

def list_serial_ports():
    """Return the device names of the currently available serial ports."""
    try:
        return [port.device for port in serial.tools.list_ports.comports()]
    except Exception:
        return []


def build_window():
    """Create the FreeSimpleGUI window and its layout."""
    sg.theme(THEME)
    bg = sg.theme_background_color()

    header = [sg.Text("Arduino LED Timer", font=FONT_TITLE, pad=((0, 0), (4, 10)))]

    connection_row = [
        sg.Text("Port:", font=FONT),
        sg.Combo(list_serial_ports(), size=(24, 1), key="-PORT-",
                 readonly=False, font=FONT),
        sg.Button("Refresh", key="-REFRESH-"),
        sg.Button("Connect", key="-CONNECT-",
                  button_color=("#ffffff", "#2d6a4f")),
        sg.Button("Disconnect", key="-DISCONNECT-", disabled=True,
                  button_color=("#ffffff", "#7f1d1d")),
    ]

    # Graphical button + LED, each with a caption underneath.
    btn_col = sg.Column(
        [[sg.Graph((140, 140), (0, 0), (140, 140),
                   key="-BTN-", background_color=bg, pad=(0, 0))],
         [sg.Text("BUTTON", font=FONT_LABEL, text_color="#8b95a5")]],
        element_justification="center", background_color=bg,
    )
    led_col = sg.Column(
        [[sg.Graph((140, 140), (0, 0), (140, 140),
                   key="-LED-", background_color=bg, pad=(0, 0))],
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
        sg.Button("Send", key="-SEND-", bind_return_key=True,
                  button_color=("#0b0f14", "#4da3ff")),
    ]

    response_row = [
        sg.Multiline(
            size=(62, 14),
            key="-RESPONSE-",
            autoscroll=True,
            disabled=True,           # read-only log area
            reroute_stdout=False,
            font=("Consolas", 9),
            background_color="#15171c",
            text_color="#cfd6e0",
            border_width=0,
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

    window = sg.Window("Arduino LED Timer", layout, finalize=True,
                       element_justification="left")

    # Paint the indicators in their idle state.
    draw_button(window["-BTN-"], pressed=False)
    draw_led(window["-LED-"], on=False)
    return window


def log(window, text):
    """Append a timestamped line to the response area."""
    window["-RESPONSE-"].print(f"[{datetime.now():%H:%M:%S}] {text}")


def parse_duration(raw_value):
    """Validate the user input. Returns (value, error_message)."""
    text = raw_value.strip()
    if not text:
        return None, "Please enter a timer value in milliseconds."

    try:
        value = int(float(text))     # accept "5000" and "5000.0" alike
    except ValueError:
        return None, f"'{text}' is not a number - enter milliseconds, e.g. 5000."

    if value <= 0:
        return None, "The timer value must be greater than 0 ms."

    return value, None


def set_connected_state(window, connected, status_text):
    """Enable/disable the controls that depend on an open connection."""
    window["-CONNECT-"].update(disabled=connected)
    window["-DISCONNECT-"].update(disabled=not connected)
    window["-PORT-"].update(disabled=connected)
    window["-REFRESH-"].update(disabled=connected)
    window["-STATUS-"].update(status_text)


def handle_device_message(window, line):
    """Translate a line coming from the board, drive the visuals, and log it."""
    # Update the graphical indicators to match the reported state.
    if line == "1":                       # button pressed -> LED on
        set_visual_state(window, led=True, pressed=True)
    elif line == "2":                     # released; LED stays on until timer ends
        set_visual_state(window, pressed=False)
    elif line == "0":                     # timer expired -> LED off only
        # Do NOT touch the button here: on a long press the timer can expire
        # while the button is still physically held. Up/down follows 1 and 2.
        set_visual_state(window, led=False)

    if line in STATE_MESSAGES:
        log(window, f"State {line}: {STATE_MESSAGES[line]}")
    else:
        # Acknowledgements and error strings from the sketch pass through.
        log(window, f"Device: {line}")


def main():
    message_queue = queue.Queue()
    worker = SerialWorker(message_queue)
    window = build_window()

    log(window, "Select a serial port and press Connect.")

    try:
        while True:
            # Timeout makes read() return regularly so the queue gets drained
            # while the GUI stays responsive.
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
                    ok, message = worker.send_duration(duration)
                    log(window, message)

            elif event == "-CLEAR-":
                window["-RESPONSE-"].update("")

            # Drain everything the reader thread produced since the last cycle.
            while True:
                try:
                    kind, payload = message_queue.get_nowait()
                except queue.Empty:
                    break

                if kind == "device":
                    handle_device_message(window, payload)
                else:  # "error" - the reader thread stopped
                    log(window, payload)
                    worker.disconnect()
                    set_connected_state(window, False, "Disconnected (error)")
                    set_visual_state(window, led=False, pressed=False)

    except Exception as exc:                     # last-resort safety net
        sg.popup_error(f"Unexpected error: {exc}")

    finally:
        # Always release the port and the thread, whatever happened above.
        worker.disconnect()
        window.close()


if __name__ == "__main__":
    main()