#!/usr/bin/env python3
"""Build two JSONL datasets from kernel driver sources.

Dataset 1 (atomic rules): one rule -> one minimal snippet.
Dataset 2 (combinations): probe function variants with combined rules.
"""

import argparse
import json
import os
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DIRS = [
    "drivers/iio/temperature",
    "drivers/iio/humidity",
    "drivers/iio/pressure",
    "drivers/iio/accel",
    "drivers/iio/adc",
    "drivers/iio/light",
    "drivers/input/keyboard",
    "drivers/input/misc",
    "drivers/gpio",
    "drivers/rtc",
    "drivers/watchdog",
    "drivers/pwm",
    "drivers/mtd/spi-nor",
    "drivers/mtd/nand",
    "drivers/net/ethernet",
    "drivers/net/can",
    "drivers/usb/serial",
    "drivers/video/fbdev",
    "drivers/nvmem",
    "drivers/char",
    "drivers/leds",
    "drivers/power/supply",
    "drivers/thermal",
    "sound/soc/codecs",
]

KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "do",
    "else",
    "case",
    "break",
    "continue",
    "goto",
    "typedef",
    "struct",
    "union",
    "enum",
    "static",
    "inline",
    "__inline__",
    "__attribute__",
}

TARGET_NAME_PATTERNS = {
    "probe": re.compile(r"(^|_)probe($|_)", re.IGNORECASE),
    "remove": re.compile(r"(^|_)remove($|_)", re.IGNORECASE),
    "ioctl": re.compile(r"ioctl", re.IGNORECASE),
}

BUS_RULES = {
    "I2C_BUS": ["i2c_client", "i2c_driver"],
    "SPI_BUS": ["spi_device", "spi_driver"],
    "USB_BUS": ["usb_interface", "usb_driver", "usb_device"],
    "PCI_BUS": ["pci_dev", "pci_driver"],
    "PLATFORM_BUS": ["platform_device", "platform_driver"],
    "UART_BUS": ["uart_driver", "tty_"],
    "CAN_BUS": ["can_driver", "can_frame"],
    "GPIO_BUS": ["gpio_desc", "gpiod_", "gpiochip_"],
}

DEVICE_TYPE_RULES = {
    "TEMP_SENSOR": ["temperature", "temp", "thermal"],
    "HUMIDITY_SENSOR": ["humidity", "humid", "rh"],
    "PRESSURE_SENSOR": ["pressure", "baro", "bmp"],
    "ACCELEROMETER": ["accel", "accelerometer"],
    "GYROSCOPE": ["gyro", "gyroscope"],
    "LIGHT_SENSOR": ["light", "lux", "als"],
    "ADC_DEVICE": ["adc", "analog"],
    "LED_DEVICE": ["led", "brightness"],
    "GPIO_EXPANDER": ["expander", "pca955", "mcp23"],
    "RTC_DEVICE": ["rtc", "ds1307", "ds3232"],
    "WATCHDOG_DEVICE": ["watchdog", "wdt"],
    "PWM_DEVICE": ["pwm", "pwmchip"],
    "FLASH_DEVICE": ["flash", "mtd", "nor", "nand"],
    "NETWORK_DEVICE": ["ethernet", "net", "nic"],
    "SERIAL_DEVICE": ["serial", "uart", "ftdi", "cp210"],
    "DISPLAY_DEVICE": ["display", "lcd", "oled", "fb"],
    "EEPROM_DEVICE": ["eeprom", "at24", "at25"],
    "INPUT_DEVICE": ["input", "keyboard", "mouse", "hid"],
    "BUTTON_DEVICE": ["button", "key", "gpio_keys"],
    "POWER_SUPPLY": ["power", "battery", "charger"],
    "CODEC_DEVICE": ["codec", "audio", "sound"],
}

SUBSYSTEM_RULES = {
    "IIO_REGISTER": ["devm_iio_device_register", "iio_device_register"],
    "IIO_CHANNELS": ["iio_chan_spec"],
    "IIO_BUFFER": ["iio_triggered_buffer_setup"],
    "IIO_READ": ["_read_raw"],
    "IIO_WRITE": ["_write_raw"],
    "INPUT_REGISTER": ["input_register_device"],
    "INPUT_EVENT": ["input_report_key", "input_sync"],
    "INPUT_POLL": ["input_poll_dev"],
    "RTC_REGISTER": ["devm_rtc_device_register"],
    "RTC_READ": ["rtc_read_time"],
    "RTC_WRITE": ["rtc_set_time"],
    "NVMEM_REGISTER": ["devm_nvmem_register"],
    "NVMEM_READ": ["nvmem"],
    "NVMEM_WRITE": ["nvmem"],
    "FB_REGISTER": ["register_framebuffer"],
    "FB_WRITE": ["fb_write", "fb_sys_write"],
    "WATCHDOG_REGISTER": ["devm_watchdog_register_device"],
    "WATCHDOG_PING": ["watchdog_ping"],
    "WATCHDOG_START": ["start"],
    "WATCHDOG_STOP": ["stop"],
    "WATCHDOG_SET_TIMEOUT": ["set_timeout"],
    "PWM_REGISTER": ["devm_pwmchip_add"],
    "PWM_CONFIG": ["pwm_apply_state", "pwm_config"],
    "PWM_ENABLE": ["pwm_enable"],
    "PWM_SET_DUTY": ["duty"],
    "TTY_REGISTER": ["tty_port_register_device"],
    "MTD_REGISTER": ["mtd_device_register"],
    "MTD_READ": ["mtd_read"],
    "MTD_WRITE": ["mtd_write"],
    "MTD_ERASE": ["mtd_erase"],
    "NET_REGISTER": ["register_netdev"],
    "NET_TX": ["ndo_start_xmit"],
    "CHAR_DEV_INIT": ["cdev_init", "register_chrdev"],
    "CHAR_DEV_CREATE": ["device_create", "class_create"],
}

MEMORY_RULES = {
    "KMALLOC": ["kmalloc"],
    "KZALLOC": ["kzalloc"],
    "KFREE": ["kfree"],
    "DEVM_KZALLOC": ["devm_kzalloc"],
    "DEVM_KMALLOC": ["devm_kmalloc"],
    "DMA_ALLOC_COHERENT": ["dma_alloc_coherent"],
    "DMA_MAP_SINGLE": ["dma_map_single"],
    "DMA_UNMAP_SINGLE": ["dma_unmap_single"],
    "DMA_FREE_COHERENT": ["dma_free_coherent"],
}

SYNC_RULES = {
    "MUTEX_INIT": ["mutex_init"],
    "MUTEX_LOCK": ["mutex_lock"],
    "MUTEX_UNLOCK": ["mutex_unlock"],
    "SPINLOCK_INIT": ["spin_lock_init"],
    "SPIN_LOCK": ["spin_lock"],
    "SPIN_UNLOCK": ["spin_unlock"],
    "SPIN_LOCK_IRQ": ["spin_lock_irq"],
    "SPIN_LOCK_IRQSAVE": ["spin_lock_irqsave"],
    "SPIN_UNLOCK_IRQRESTORE": ["spin_unlock_irqrestore"],
}

ERROR_RULES = {
    "IS_ERR": ["IS_ERR"],
    "PTR_ERR": ["PTR_ERR"],
    "DEV_ERR": ["dev_err"],
    "DEV_WARN": ["dev_warn"],
    "DEV_INFO": ["dev_info"],
}

FEATURE_RULES = {
    "THRESHOLD_FEATURE": ["threshold", "limit", "alarm", "overtemp"],
    "POLL_FEATURE": ["poll_wait", "wait_event_interruptible"],
    "DEBOUNCE_FEATURE": ["debounce", "gpiod_set_debounce"],
    "FIFO_FEATURE": ["fifo", "circular"],
    "SYSFS_ATTR_RO": ["DEVICE_ATTR_RO"],
    "SYSFS_ATTR_WO": ["DEVICE_ATTR_WO"],
    "SYSFS_ATTR_RW": ["DEVICE_ATTR_RW"],
    "SYSFS_SHOW": ["_show"],
    "SYSFS_STORE": ["_store"],
    "POWER_MGMT_FEATURE": ["SIMPLE_DEV_PM_OPS", "SET_SYSTEM_SLEEP_PM_OPS"],
    "PM_SUSPEND": ["suspend"],
    "PM_RESUME": ["resume"],
    "CALIBRATION_FEATURE": ["calibration", "calibrate"],
}

IRQ_RULES = {
    "IRQ_REQUEST": ["request_irq", "request_threaded_irq", "devm_request_irq"],
    "IRQ_FREE": ["free_irq"],
    "IRQ_HANDLER": ["irqreturn_t"],
    "IRQ_THREADED": ["request_threaded_irq"],
    "IRQ_ONESHOT": ["IRQF_ONESHOT"],
    "IRQ_SHARED": ["IRQF_SHARED"],
    "IRQF_TRIGGER_RISING": ["IRQF_TRIGGER_RISING"],
    "IRQF_TRIGGER_FALLING": ["IRQF_TRIGGER_FALLING"],
    "IRQF_TRIGGER_LOW": ["IRQF_TRIGGER_LOW"],
    "IRQF_TRIGGER_HIGH": ["IRQF_TRIGGER_HIGH"],
    "ENABLE_IRQ": ["enable_irq"],
    "DISABLE_IRQ": ["disable_irq"],
}

DT_RULES = {
    "OF_MATCH_TABLE": ["of_device_id"],
    "OF_COMPATIBLE": [".compatible"],
    "OF_PROPERTY_READ": ["of_property_read_u32"],
    "OF_GPIO_GET": ["of_get_gpio"],
    "OF_IRQ_GET": ["of_irq_get"],
}

MODULE_RULES = {
    "MODULE_INIT": ["module_init"],
    "MODULE_EXIT": ["module_exit"],
    "MODULE_LICENSE": ["MODULE_LICENSE"],
    "MODULE_AUTHOR": ["MODULE_AUTHOR"],
    "MODULE_DESCRIPTION": ["MODULE_DESCRIPTION"],
    "MODULE_DEVICE_TABLE": ["MODULE_DEVICE_TABLE"],
}

IOCTL_RULES = {
    "IOCTL_IMPLEMENTATION": ["unlocked_ioctl"],
    "IOCTL_SWITCH_CASE": ["switch"],
    "IOCTL_CMD_READ": ["copy_to_user"],
    "IOCTL_CMD_WRITE": ["copy_from_user"],
    "IOCTL_COPY_FROM_USER": ["copy_from_user"],
    "IOCTL_COPY_TO_USER": ["copy_to_user"],
}

USERCOPY_RULES = {
    "COPY_TO_USER": ["copy_to_user"],
    "COPY_FROM_USER": ["copy_from_user"],
    "ACCESS_OK": ["access_ok"],
}

TIMER_RULES = {
    "TIMER_SETUP": ["timer_setup"],
    "TIMER_ADD": ["add_timer", "mod_timer"],
    "TIMER_DEL": ["del_timer"],
    "HRTIMER_INIT": ["hrtimer_init"],
    "HRTIMER_START": ["hrtimer_start"],
}

WORK_RULES = {
    "INIT_WORK": ["INIT_WORK"],
    "SCHEDULE_WORK": ["schedule_work"],
    "SCHEDULE_DELAYED_WORK": ["schedule_delayed_work"],
    "CANCEL_WORK_SYNC": ["cancel_work_sync"],
}

DRIVER_RULES = {
    "DEVICE_REGISTER": ["device_register"],
    "DEVICE_UNREGISTER": ["device_unregister"],
    "DRIVER_REGISTER": ["driver_register"],
    "DRIVER_UNREGISTER": ["driver_unregister"],
}

COMBO_RULE_MAPS = [
    BUS_RULES,
    DEVICE_TYPE_RULES,
    SUBSYSTEM_RULES,
    MEMORY_RULES,
    SYNC_RULES,
    ERROR_RULES,
    FEATURE_RULES,
    IRQ_RULES,
    DT_RULES,
    MODULE_RULES,
    IOCTL_RULES,
    USERCOPY_RULES,
    TIMER_RULES,
    WORK_RULES,
    DRIVER_RULES,
]

ERROR_RETURN_RE = re.compile(r"\breturn\s*-\s*E\w+")
GOTO_CLEANUP_RE = re.compile(r"\bgoto\s+(err|out|fail)\b")


class FunctionDef:
    def __init__(self, name: str, code: str, args: str) -> None:
        self.name = name
        self.code = code
        self.args = args


def strip_comments_strings(code: str) -> str:
    out = list(code)
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        if ch == '"' or ch == "'":
            quote = ch
            out[i] = ' '
            i += 1
            while i < n:
                out[i] = ' '
                if code[i] == '\\':
                    i += 2
                    continue
                if code[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == '/' and i + 1 < n:
            nxt = code[i + 1]
            if nxt == '/':
                out[i] = out[i + 1] = ' '
                i += 2
                while i < n and code[i] != '\n':
                    out[i] = ' '
                    i += 1
                continue
            if nxt == '*':
                out[i] = out[i + 1] = ' '
                i += 2
                while i + 1 < n:
                    out[i] = ' '
                    if code[i] == '*' and code[i + 1] == '/':
                        out[i + 1] = ' '
                        i += 2
                        break
                    i += 1
                continue
        i += 1
    return "".join(out)


def is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == '_'


def is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch == '_'


def skip_ws(text: str, idx: int) -> int:
    n = len(text)
    while idx < n and text[idx].isspace():
        idx += 1
    return idx


def match_paren(text: str, idx: int) -> Optional[int]:
    depth = 0
    n = len(text)
    i = idx
    while i < n:
        ch = text[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def skip_attributes(text: str, idx: int) -> int:
    n = len(text)
    i = idx
    while True:
        i = skip_ws(text, i)
        if i >= n:
            return i
        if text.startswith("__attribute__", i):
            i = skip_ws(text, i + len("__attribute__"))
            if i < n and text[i] == '(':
                end = match_paren(text, i)
                if end is None:
                    return i
                i = end + 1
            continue
        if text.startswith("__", i):
            j = i + 2
            while j < n and is_ident_part(text[j]):
                j += 1
            i = j
            continue
        return i


def find_signature_start(code: str, ident_start: int) -> int:
    start = ident_start
    j = ident_start
    while j > 0:
        line_start = code.rfind('\n', 0, j) + 1
        prev_end = line_start - 1
        if prev_end < 0:
            return 0
        prev_line_start = code.rfind('\n', 0, prev_end) + 1
        prev_line = code[prev_line_start:line_start]
        stripped = prev_line.strip()
        if not stripped:
            start = line_start
            j = prev_line_start
            continue
        if stripped.startswith('#'):
            break
        if ';' in stripped or '{' in stripped or '}' in stripped:
            break
        start = prev_line_start
        j = prev_line_start
    return start


def find_matching_brace(text: str, idx: int) -> Optional[int]:
    depth = 0
    n = len(text)
    i = idx
    while i < n:
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def extract_functions(code: str) -> List[FunctionDef]:
    cleaned = strip_comments_strings(code)
    funcs: List[FunctionDef] = []
    n = len(cleaned)
    i = 0
    brace_depth = 0
    while i < n:
        ch = cleaned[i]
        if ch == '{':
            brace_depth += 1
            i += 1
            continue
        if ch == '}':
            brace_depth = max(0, brace_depth - 1)
            i += 1
            continue
        if brace_depth != 0:
            i += 1
            continue
        if not is_ident_start(ch):
            i += 1
            continue
        ident_start = i
        j = i + 1
        while j < n and is_ident_part(cleaned[j]):
            j += 1
        ident = cleaned[ident_start:j]
        if ident in KEYWORDS:
            i = j
            continue
        k = skip_ws(cleaned, j)
        if k >= n or cleaned[k] != '(':
            i = j
            continue
        paren_end = match_paren(cleaned, k)
        if paren_end is None:
            i = j
            continue
        m = skip_attributes(cleaned, paren_end + 1)
        m = skip_ws(cleaned, m)
        if m < n and cleaned[m] == '{':
            start = find_signature_start(code, ident_start)
            end = find_matching_brace(cleaned, m)
            if end is None:
                i = j
                continue
            func_code = code[start:end + 1]
            args = code[k + 1:paren_end]
            funcs.append(FunctionDef(ident, func_code, args))
            i = end + 1
            continue
        i = j
    return funcs


def iter_c_files(base_dir: str) -> Iterable[str]:
    for root, _, files in os.walk(base_dir):
        for fname in files:
            if fname.endswith(".c"):
                yield os.path.join(root, fname)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def to_lines(text: str) -> List[str]:
    return text.splitlines()


def join_lines(lines: List[str]) -> str:
    return "\n".join(lines)


def first_line_of_signature(func: FunctionDef) -> str:
    head = func.code.split("{", 1)[0].rstrip()
    return head


def find_array_block(text: str, start_re: re.Pattern) -> Optional[str]:
    match = start_re.search(text)
    if not match:
        return None
    start = match.start()
    end = text.find("};", start)
    if end == -1:
        return None
    return text[start:end + 2]


def find_line(lines: List[str], pattern: str) -> Optional[int]:
    for idx, line in enumerate(lines):
        if pattern in line:
            return idx
    return None


def find_line_re(lines: List[str], regex: re.Pattern) -> Optional[int]:
    for idx, line in enumerate(lines):
        if regex.search(line):
            return idx
    return None


def snippet_with_error_check(lines: List[str], idx: int) -> str:
    snippet = [lines[idx]]
    for j in range(1, 4):
        if idx + j >= len(lines):
            break
        line = lines[idx + j]
        if re.search(r"\bif\b", line) or re.search(r"return\s*-E", line):
            snippet.append(line)
            if line.rstrip().endswith("{") and idx + j + 1 < len(lines):
                snippet.append(lines[idx + j + 1])
            break
    return join_lines(snippet)


def extract_function_by_predicate(funcs: List[FunctionDef], predicate) -> Optional[FunctionDef]:
    for func in funcs:
        if predicate(func):
            return func
    return None


def extract_switch_block(code: str) -> Optional[str]:
    cleaned = strip_comments_strings(code)
    idx = cleaned.find("switch")
    if idx == -1:
        return None
    brace_idx = cleaned.find("{", idx)
    if brace_idx == -1:
        return None
    end = find_matching_brace(cleaned, brace_idx)
    if end is None:
        return None
    return code[brace_idx - 6:end + 1].strip()


def collect_rules(code: str, func: FunctionDef) -> List[str]:
    rules: Set[str] = set()

    def add_rules(rule_map: Dict[str, List[str]], case_insensitive: bool = False) -> None:
        search_text = code.lower() if case_insensitive else code
        for rule, patterns in rule_map.items():
            for pat in patterns:
                needle = pat.lower() if case_insensitive else pat
                if needle in search_text:
                    rules.add(rule)
                    break

    for rule_map in COMBO_RULE_MAPS:
        add_rules(rule_map, case_insensitive=rule_map in [DEVICE_TYPE_RULES, FEATURE_RULES])

    if ERROR_RETURN_RE.search(code):
        rules.add("ERROR_RETURN")
    if GOTO_CLEANUP_RE.search(code):
        rules.add("GOTO_CLEANUP")

    if TARGET_NAME_PATTERNS["probe"].search(func.name):
        if "i2c_client" in func.args:
            rules.add("I2C_PROBE")
        if "spi_device" in func.args:
            rules.add("SPI_PROBE")
        if "usb_interface" in func.args:
            rules.add("USB_PROBE")
        if "pci_dev" in func.args:
            rules.add("PCI_PROBE")
        if "platform_device" in func.args:
            rules.add("PLATFORM_PROBE")

    if TARGET_NAME_PATTERNS["remove"].search(func.name):
        if "i2c_client" in func.args:
            rules.add("I2C_REMOVE")
        if "spi_device" in func.args:
            rules.add("SPI_REMOVE")

    return sorted(rules)


def remove_lines(code: str, patterns: List[re.Pattern]) -> str:
    out = []
    for line in code.splitlines():
        if any(p.search(line) for p in patterns):
            continue
        out.append(line)
    return "\n".join(out) + ("\n" if code.endswith("\n") else "")


def detect_indent(body: str) -> str:
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped:
            return line[: len(line) - len(stripped)]
    return "\t"


def add_mutex_feature(code: str) -> str:
    brace_idx = code.find("{")
    if brace_idx == -1:
        return code
    head = code[:brace_idx + 1]
    tail = code[brace_idx + 1:]
    indent = detect_indent(tail)
    insert = (
        f"\n{indent}struct mutex lock;\n"
        f"{indent}mutex_init(&lock);\n"
        f"{indent}mutex_lock(&lock);\n"
    )
    if tail.rstrip().endswith("}"):
        body = tail[:-1]
        end_insert = f"\n{indent}mutex_unlock(&lock);\n"
        return head + insert + body + end_insert + "}\n"
    return head + insert + tail


def add_dev_err_feature(code: str, func: FunctionDef) -> str:
    dev_expr = None
    match = re.search(r"struct\s+([A-Za-z_][\w]*)\s*\*\s*([A-Za-z_]\w*)", func.args)
    if match:
        tname, var = match.group(1), match.group(2)
        if tname == "device":
            dev_expr = var
        elif tname in {"i2c_client", "spi_device", "platform_device", "pci_dev", "usb_interface"}:
            dev_expr = f"&{var}->dev"
    if not dev_expr:
        return code
    brace_idx = code.find("{")
    if brace_idx == -1:
        return code
    head = code[:brace_idx + 1]
    tail = code[brace_idx + 1:]
    indent = detect_indent(tail)
    insert = f"\n{indent}dev_err({dev_expr}, \"expanded: injected error log\\n\");\n"
    return head + insert + tail


def bus_swap(code: str, rules: List[str]) -> Optional[str]:
    if "I2C_BUS" in rules:
        swapped = code.replace("i2c_client", "spi_device").replace("i2c_driver", "spi_driver")
        swapped = swapped.replace("i2c_", "spi_")
        return swapped
    if "SPI_BUS" in rules:
        swapped = code.replace("spi_device", "i2c_client").replace("spi_driver", "i2c_driver")
        swapped = swapped.replace("spi_", "i2c_")
        return swapped
    return None


def device_swap(code: str, rules: List[str]) -> Optional[str]:
    if "TEMP_SENSOR" in rules:
        swapped = re.sub(r"\btemperature\b", "humidity", code, flags=re.IGNORECASE)
        swapped = re.sub(r"\btemp\b", "humid", swapped, flags=re.IGNORECASE)
        swapped = re.sub(r"\bthermal\b", "humidity", swapped, flags=re.IGNORECASE)
        return swapped
    if "ACCELEROMETER" in rules:
        swapped = re.sub(r"\baccelerometer\b", "gyroscope", code, flags=re.IGNORECASE)
        swapped = re.sub(r"\baccel\b", "gyro", swapped, flags=re.IGNORECASE)
        return swapped
    return None


def extract_atomic_rules(roots: List[str]) -> Tuple[List[Dict[str, str]], List[str]]:
    missing: Set[str] = set()

    RULES = [
        "I2C_PROBE",
        "I2C_REMOVE",
        "I2C_CLIENT_REGISTER",
        "I2C_SMBUS_READ",
        "I2C_SMBUS_WRITE",
        "I2C_DEVICE_ID",
        "SPI_PROBE",
        "SPI_REMOVE",
        "SPI_SETUP",
        "SPI_TRANSFER",
        "SPI_DMA_SETUP",
        "SPI_FIFO_CONFIG",
        "GPIO_REQUEST",
        "GPIO_FREE",
        "GPIO_INPUT",
        "GPIO_OUTPUT",
        "GPIO_GET_VALUE",
        "GPIO_SET_VALUE",
        "GPIO_DEBOUNCE",
        "GPIO_IRQ_REQUEST",
        "USB_PROBE",
        "USB_ENDPOINT_DETECT",
        "USB_URB_ALLOC",
        "USB_URB_SUBMIT",
        "PCI_PROBE",
        "PCI_BAR_MAP",
        "PCI_MSI_SETUP",
        "PCI_DMA_ALLOC",
        "PLATFORM_PROBE",
        "PLATFORM_GET_RESOURCE",
        "PLATFORM_GET_IRQ",
        "IIO_REGISTER",
        "IIO_CHANNELS",
        "IIO_BUFFER",
        "IIO_READ",
        "IIO_WRITE",
        "INPUT_REGISTER",
        "INPUT_EVENT",
        "INPUT_POLL",
        "INPUT_SYNC",
        "RTC_REGISTER",
        "RTC_READ",
        "RTC_WRITE",
        "RTC_ALARM",
        "NVMEM_REGISTER",
        "NVMEM_READ",
        "NVMEM_WRITE",
        "FB_REGISTER",
        "FB_WRITE",
        "FB_BLANK",
        "WATCHDOG_REGISTER",
        "WATCHDOG_PING",
        "WATCHDOG_START",
        "WATCHDOG_STOP",
        "WATCHDOG_SET_TIMEOUT",
        "PWM_REGISTER",
        "PWM_CONFIG",
        "PWM_ENABLE",
        "PWM_SET_DUTY",
        "TTY_REGISTER",
        "TTY_READ",
        "TTY_WRITE",
        "TTY_SET_BAUD",
        "MTD_REGISTER",
        "MTD_READ",
        "MTD_WRITE",
        "MTD_ERASE",
        "NET_REGISTER",
        "NET_OPEN",
        "NET_STOP",
        "NET_TX",
        "CHAR_DEV_INIT",
        "CHAR_DEV_CREATE",
        "CHAR_DEV_READ",
        "CHAR_DEV_WRITE",
        "CHAR_DEV_IOCTL",
        "CHAR_DEV_POLL",
        "CHAR_DEV_MMAP",
        "CDEV_INIT",
        "CDEV_ADD",
        "CDEV_DEL",
        "DEVICE_CREATE",
        "CLASS_CREATE",
        "REGISTER_CHRDEV",
        "UNREGISTER_CHRDEV",
        "IRQ_REQUEST",
        "IRQ_FREE",
        "IRQ_HANDLER",
        "IRQ_THREADED",
        "IRQ_ONESHOT",
        "IRQ_SHARED",
        "IRQF_TRIGGER_RISING",
        "IRQF_TRIGGER_FALLING",
        "IRQF_TRIGGER_LOW",
        "IRQF_TRIGGER_HIGH",
        "ENABLE_IRQ",
        "DISABLE_IRQ",
        "KMALLOC",
        "KZALLOC",
        "KFREE",
        "DEVM_KZALLOC",
        "DEVM_KMALLOC",
        "DMA_ALLOC_COHERENT",
        "DMA_FREE_COHERENT",
        "DMA_MAP_SINGLE",
        "DMA_UNMAP_SINGLE",
        "MUTEX_INIT",
        "MUTEX_LOCK",
        "MUTEX_UNLOCK",
        "SPINLOCK_INIT",
        "SPIN_LOCK",
        "SPIN_UNLOCK",
        "SPIN_LOCK_IRQ",
        "SPIN_LOCK_IRQSAVE",
        "SPIN_UNLOCK_IRQRESTORE",
        "GOTO_CLEANUP",
        "ERROR_RETURN",
        "IS_ERR",
        "PTR_ERR",
        "DEV_ERR",
        "DEV_WARN",
        "DEV_INFO",
        "THRESHOLD_FEATURE",
        "POLL_FEATURE",
        "DEBOUNCE_FEATURE",
        "FIFO_FEATURE",
        "SYSFS_ATTR_RO",
        "SYSFS_ATTR_WO",
        "SYSFS_ATTR_RW",
        "SYSFS_SHOW",
        "SYSFS_STORE",
        "POWER_MGMT_FEATURE",
        "PM_SUSPEND",
        "PM_RESUME",
        "CALIBRATION_FEATURE",
        "OF_MATCH_TABLE",
        "OF_COMPATIBLE",
        "OF_PROPERTY_READ",
        "OF_GPIO_GET",
        "OF_IRQ_GET",
        "MODULE_INIT",
        "MODULE_EXIT",
        "MODULE_LICENSE",
        "MODULE_AUTHOR",
        "MODULE_DESCRIPTION",
        "MODULE_DEVICE_TABLE",
        "IOCTL_IMPLEMENTATION",
        "IOCTL_SWITCH_CASE",
        "IOCTL_CMD_READ",
        "IOCTL_CMD_WRITE",
        "IOCTL_COPY_FROM_USER",
        "IOCTL_COPY_TO_USER",
        "COPY_TO_USER",
        "COPY_FROM_USER",
        "ACCESS_OK",
        "TIMER_SETUP",
        "TIMER_ADD",
        "TIMER_DEL",
        "HRTIMER_INIT",
        "HRTIMER_START",
        "INIT_WORK",
        "SCHEDULE_WORK",
        "SCHEDULE_DELAYED_WORK",
        "CANCEL_WORK_SYNC",
        "DEVICE_REGISTER",
        "DEVICE_UNREGISTER",
        "DRIVER_REGISTER",
        "DRIVER_UNREGISTER",
    ]

    remaining = set(RULES)
    results: Dict[str, Dict[str, str]] = {}

    for root in roots:
        for rel_dir in DIRS:
            abs_dir = os.path.join(root, rel_dir)
            if not os.path.isdir(abs_dir):
                continue
            for path in iter_c_files(abs_dir):
                if not remaining:
                    break
                text = read_file(path)
                lines = to_lines(text)
                funcs = extract_functions(text)
                rel_path = os.path.relpath(path, root)
                driver = os.path.splitext(os.path.basename(path))[0]

                def record(rule: str, code: Optional[str]) -> None:
                    if code and rule in remaining:
                        results[rule] = {
                            "rule": rule,
                            "code": code.strip(),
                            "source_file": rel_path,
                            "driver": driver,
                        }
                        remaining.remove(rule)

                # Probe/remove signatures
                if "I2C_PROBE" in remaining:
                    func = extract_function_by_predicate(
                        funcs,
                        lambda f: TARGET_NAME_PATTERNS["probe"].search(f.name)
                        and "i2c_client" in f.args,
                    )
                    if func:
                        record("I2C_PROBE", first_line_of_signature(func))

                if "I2C_REMOVE" in remaining:
                    func = extract_function_by_predicate(
                        funcs,
                        lambda f: TARGET_NAME_PATTERNS["remove"].search(f.name)
                        and "i2c_client" in f.args,
                    )
                    if func:
                        record("I2C_REMOVE", first_line_of_signature(func))

                if "SPI_PROBE" in remaining:
                    func = extract_function_by_predicate(
                        funcs,
                        lambda f: TARGET_NAME_PATTERNS["probe"].search(f.name)
                        and "spi_device" in f.args,
                    )
                    if func:
                        record("SPI_PROBE", first_line_of_signature(func))

                if "SPI_REMOVE" in remaining:
                    func = extract_function_by_predicate(
                        funcs,
                        lambda f: TARGET_NAME_PATTERNS["remove"].search(f.name)
                        and "spi_device" in f.args,
                    )
                    if func:
                        record("SPI_REMOVE", first_line_of_signature(func))

                if "USB_PROBE" in remaining:
                    func = extract_function_by_predicate(
                        funcs,
                        lambda f: TARGET_NAME_PATTERNS["probe"].search(f.name)
                        and "usb_interface" in f.args,
                    )
                    if func:
                        record("USB_PROBE", first_line_of_signature(func))

                if "PCI_PROBE" in remaining:
                    func = extract_function_by_predicate(
                        funcs,
                        lambda f: TARGET_NAME_PATTERNS["probe"].search(f.name)
                        and "pci_dev" in f.args,
                    )
                    if func:
                        record("PCI_PROBE", first_line_of_signature(func))

                if "PLATFORM_PROBE" in remaining:
                    func = extract_function_by_predicate(
                        funcs,
                        lambda f: TARGET_NAME_PATTERNS["probe"].search(f.name)
                        and "platform_device" in f.args,
                    )
                    if func:
                        record("PLATFORM_PROBE", first_line_of_signature(func))

                # I2C/SPI lines
                if "I2C_CLIENT_REGISTER" in remaining:
                    idx = find_line(lines, "i2c_set_clientdata")
                    if idx is not None:
                        record("I2C_CLIENT_REGISTER", lines[idx])

                if "I2C_SMBUS_READ" in remaining:
                    idx = find_line(lines, "i2c_smbus_read_byte_data")
                    if idx is not None:
                        record("I2C_SMBUS_READ", snippet_with_error_check(lines, idx))

                if "I2C_SMBUS_WRITE" in remaining:
                    idx = find_line(lines, "i2c_smbus_write_byte_data")
                    if idx is not None:
                        record("I2C_SMBUS_WRITE", snippet_with_error_check(lines, idx))

                if "I2C_DEVICE_ID" in remaining:
                    block = find_array_block(text, re.compile(r"struct\s+i2c_device_id\b"))
                    if block:
                        record("I2C_DEVICE_ID", block)

                if "SPI_SETUP" in remaining:
                    idx = find_line(lines, "spi_setup")
                    if idx is not None:
                        record("SPI_SETUP", lines[idx])

                if "SPI_TRANSFER" in remaining:
                    idx = find_line(lines, "spi_sync_transfer")
                    if idx is None:
                        idx = find_line(lines, "spi_write_then_read")
                    if idx is not None:
                        record("SPI_TRANSFER", lines[idx])

                if "SPI_DMA_SETUP" in remaining:
                    idx = find_line(lines, "dmaengine_slave_config")
                    if idx is not None:
                        record("SPI_DMA_SETUP", lines[idx])

                if "SPI_FIFO_CONFIG" in remaining:
                    idx = find_line_re(lines, re.compile(r"fifo", re.IGNORECASE))
                    if idx is not None:
                        record("SPI_FIFO_CONFIG", lines[idx])

                # GPIO
                if "GPIO_REQUEST" in remaining:
                    idx = find_line_re(lines, re.compile(r"devm_gpiod_get|gpiod_get"))
                    if idx is not None:
                        record("GPIO_REQUEST", snippet_with_error_check(lines, idx))

                if "GPIO_FREE" in remaining:
                    idx = find_line(lines, "gpiod_put")
                    if idx is not None:
                        record("GPIO_FREE", lines[idx])

                if "GPIO_INPUT" in remaining:
                    idx = find_line(lines, "gpiod_direction_input")
                    if idx is not None:
                        record("GPIO_INPUT", lines[idx])

                if "GPIO_OUTPUT" in remaining:
                    idx = find_line(lines, "gpiod_direction_output")
                    if idx is not None:
                        record("GPIO_OUTPUT", lines[idx])

                if "GPIO_GET_VALUE" in remaining:
                    idx = find_line(lines, "gpiod_get_value")
                    if idx is not None:
                        record("GPIO_GET_VALUE", lines[idx])

                if "GPIO_SET_VALUE" in remaining:
                    idx = find_line(lines, "gpiod_set_value")
                    if idx is not None:
                        record("GPIO_SET_VALUE", lines[idx])

                if "GPIO_DEBOUNCE" in remaining:
                    idx = find_line(lines, "gpiod_set_debounce")
                    if idx is not None:
                        record("GPIO_DEBOUNCE", lines[idx])

                if "GPIO_IRQ_REQUEST" in remaining:
                    idx = find_line(lines, "gpiod_to_irq")
                    if idx is not None:
                        record("GPIO_IRQ_REQUEST", lines[idx])

                # USB
                if "USB_ENDPOINT_DETECT" in remaining:
                    idx = find_line_re(lines, re.compile(r"usb_endpoint", re.IGNORECASE))
                    if idx is not None:
                        record("USB_ENDPOINT_DETECT", lines[idx])

                if "USB_URB_ALLOC" in remaining:
                    idx = find_line(lines, "usb_alloc_urb")
                    if idx is not None:
                        record("USB_URB_ALLOC", lines[idx])

                if "USB_URB_SUBMIT" in remaining:
                    idx = find_line(lines, "usb_submit_urb")
                    if idx is not None:
                        record("USB_URB_SUBMIT", lines[idx])

                # PCI
                if "PCI_BAR_MAP" in remaining:
                    idx = find_line(lines, "pci_iomap")
                    if idx is not None:
                        record("PCI_BAR_MAP", lines[idx])

                if "PCI_MSI_SETUP" in remaining:
                    idx = find_line(lines, "pci_alloc_irq_vectors")
                    if idx is not None:
                        record("PCI_MSI_SETUP", lines[idx])

                if "PCI_DMA_ALLOC" in remaining:
                    idx = find_line(lines, "dma_alloc_coherent")
                    if idx is not None:
                        record("PCI_DMA_ALLOC", lines[idx])

                # Platform
                if "PLATFORM_GET_RESOURCE" in remaining:
                    idx = find_line(lines, "platform_get_resource")
                    if idx is not None:
                        record("PLATFORM_GET_RESOURCE", lines[idx])

                if "PLATFORM_GET_IRQ" in remaining:
                    idx = find_line(lines, "platform_get_irq")
                    if idx is not None:
                        record("PLATFORM_GET_IRQ", lines[idx])

                # IIO
                if "IIO_REGISTER" in remaining:
                    idx = find_line(lines, "devm_iio_device_register")
                    if idx is not None:
                        record("IIO_REGISTER", snippet_with_error_check(lines, idx))

                if "IIO_CHANNELS" in remaining:
                    block = find_array_block(text, re.compile(r"iio_chan_spec"))
                    if block:
                        entry_start = block.find("{")
                        entry_end = block.find("},", entry_start)
                        if entry_start != -1 and entry_end != -1:
                            record("IIO_CHANNELS", block[entry_start:entry_end + 2])

                if "IIO_BUFFER" in remaining:
                    idx = find_line(lines, "iio_triggered_buffer_setup")
                    if idx is not None:
                        record("IIO_BUFFER", lines[idx])

                if "IIO_READ" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "_read_raw" in f.name
                    )
                    if func:
                        record("IIO_READ", func.code)

                if "IIO_WRITE" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "_write_raw" in f.name
                    )
                    if func:
                        record("IIO_WRITE", func.code)

                # Input
                if "INPUT_REGISTER" in remaining:
                    idx = find_line(lines, "input_register_device")
                    if idx is not None:
                        record("INPUT_REGISTER", lines[idx])

                if "INPUT_EVENT" in remaining:
                    idx = find_line(lines, "input_report_key")
                    if idx is not None:
                        snippet = lines[idx]
                        next_idx = find_line(lines[idx + 1:], "input_sync")
                        if next_idx is not None:
                            snippet = join_lines([lines[idx], lines[idx + 1 + next_idx]])
                        record("INPUT_EVENT", snippet)

                if "INPUT_POLL" in remaining:
                    idx = find_line(lines, "input_poll_dev")
                    if idx is not None:
                        record("INPUT_POLL", lines[idx])

                if "INPUT_SYNC" in remaining:
                    idx = find_line(lines, "input_sync")
                    if idx is not None:
                        record("INPUT_SYNC", lines[idx])

                # RTC
                if "RTC_REGISTER" in remaining:
                    idx = find_line(lines, "devm_rtc_device_register")
                    if idx is not None:
                        record("RTC_REGISTER", lines[idx])

                if "RTC_READ" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "read_time" in f.name
                    )
                    if func:
                        record("RTC_READ", func.code)

                if "RTC_WRITE" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "set_time" in f.name
                    )
                    if func:
                        record("RTC_WRITE", func.code)

                if "RTC_ALARM" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "alarm" in f.name
                    )
                    if func:
                        record("RTC_ALARM", func.code)

                # NVMEM
                if "NVMEM_REGISTER" in remaining:
                    block = find_array_block(text, re.compile(r"struct\s+nvmem_config\b"))
                    if block:
                        record("NVMEM_REGISTER", block)

                if "NVMEM_READ" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "nvmem" in f.name and "read" in f.name
                    )
                    if func:
                        record("NVMEM_READ", func.code)

                if "NVMEM_WRITE" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "nvmem" in f.name and "write" in f.name
                    )
                    if func:
                        record("NVMEM_WRITE", func.code)

                # FB
                if "FB_REGISTER" in remaining:
                    idx = find_line(lines, "register_framebuffer")
                    if idx is not None:
                        record("FB_REGISTER", lines[idx])

                if "FB_WRITE" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "fb_write" in f.name or "fb_sys_write" in f.name
                    )
                    if func:
                        record("FB_WRITE", func.code)

                if "FB_BLANK" in remaining:
                    func = extract_function_by_predicate(funcs, lambda f: "fb_blank" in f.name)
                    if func:
                        record("FB_BLANK", func.code)

                # Watchdog
                if "WATCHDOG_REGISTER" in remaining:
                    idx = find_line(lines, "devm_watchdog_register_device")
                    if idx is not None:
                        record("WATCHDOG_REGISTER", lines[idx])

                if "WATCHDOG_PING" in remaining:
                    idx = find_line(lines, "watchdog_ping")
                    if idx is not None:
                        record("WATCHDOG_PING", lines[idx])

                if "WATCHDOG_START" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "watchdog" in f.name and "start" in f.name
                    )
                    if func:
                        record("WATCHDOG_START", func.code)

                if "WATCHDOG_STOP" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "watchdog" in f.name and "stop" in f.name
                    )
                    if func:
                        record("WATCHDOG_STOP", func.code)

                if "WATCHDOG_SET_TIMEOUT" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "set_timeout" in f.name
                    )
                    if func:
                        record("WATCHDOG_SET_TIMEOUT", func.code)

                # PWM
                if "PWM_REGISTER" in remaining:
                    idx = find_line(lines, "devm_pwmchip_add")
                    if idx is not None:
                        record("PWM_REGISTER", lines[idx])

                if "PWM_CONFIG" in remaining:
                    idx = find_line_re(lines, re.compile(r"pwm_apply_state|pwm_config"))
                    if idx is not None:
                        record("PWM_CONFIG", lines[idx])

                if "PWM_ENABLE" in remaining:
                    idx = find_line(lines, "pwm_enable")
                    if idx is not None:
                        record("PWM_ENABLE", lines[idx])

                if "PWM_SET_DUTY" in remaining:
                    idx = find_line_re(lines, re.compile(r"duty_cycle|pwm_set_duty"))
                    if idx is not None:
                        record("PWM_SET_DUTY", lines[idx])

                # TTY
                if "TTY_REGISTER" in remaining:
                    idx = find_line(lines, "tty_port_register_device")
                    if idx is not None:
                        record("TTY_REGISTER", lines[idx])

                if "TTY_READ" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "tty" in f.name and "read" in f.name
                    )
                    if func:
                        record("TTY_READ", func.code)

                if "TTY_WRITE" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "tty" in f.name and "write" in f.name
                    )
                    if func:
                        record("TTY_WRITE", func.code)

                if "TTY_SET_BAUD" in remaining:
                    idx = find_line_re(lines, re.compile(r"baud", re.IGNORECASE))
                    if idx is not None:
                        record("TTY_SET_BAUD", lines[idx])

                # MTD
                if "MTD_REGISTER" in remaining:
                    idx = find_line(lines, "mtd_device_register")
                    if idx is not None:
                        record("MTD_REGISTER", lines[idx])

                if "MTD_READ" in remaining:
                    func = extract_function_by_predicate(funcs, lambda f: "mtd_read" in f.name)
                    if func:
                        record("MTD_READ", func.code)

                if "MTD_WRITE" in remaining:
                    func = extract_function_by_predicate(funcs, lambda f: "mtd_write" in f.name)
                    if func:
                        record("MTD_WRITE", func.code)

                if "MTD_ERASE" in remaining:
                    func = extract_function_by_predicate(funcs, lambda f: "mtd_erase" in f.name)
                    if func:
                        record("MTD_ERASE", func.code)

                # Net
                if "NET_REGISTER" in remaining:
                    idx = find_line(lines, "register_netdev")
                    if idx is not None:
                        record("NET_REGISTER", lines[idx])

                if "NET_OPEN" in remaining:
                    idx = find_line_re(lines, re.compile(r"ndo_open\s*=") )
                    if idx is not None:
                        record("NET_OPEN", lines[idx])

                if "NET_STOP" in remaining:
                    idx = find_line_re(lines, re.compile(r"ndo_stop\s*=") )
                    if idx is not None:
                        record("NET_STOP", lines[idx])

                if "NET_TX" in remaining:
                    idx = find_line_re(lines, re.compile(r"ndo_start_xmit\s*=") )
                    if idx is not None:
                        record("NET_TX", lines[idx])

                # Char dev
                if "CHAR_DEV_INIT" in remaining:
                    idx = find_line_re(lines, re.compile(r"cdev_init|register_chrdev"))
                    if idx is not None:
                        record("CHAR_DEV_INIT", lines[idx])

                if "CHAR_DEV_CREATE" in remaining:
                    idx = find_line_re(lines, re.compile(r"device_create|class_create"))
                    if idx is not None:
                        record("CHAR_DEV_CREATE", lines[idx])

                if "CHAR_DEV_READ" in remaining:
                    idx = find_line(lines, "copy_to_user")
                    if idx is not None:
                        record("CHAR_DEV_READ", snippet_with_error_check(lines, idx))

                if "CHAR_DEV_WRITE" in remaining:
                    idx = find_line(lines, "copy_from_user")
                    if idx is not None:
                        record("CHAR_DEV_WRITE", snippet_with_error_check(lines, idx))

                if "CHAR_DEV_IOCTL" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: TARGET_NAME_PATTERNS["ioctl"].search(f.name)
                    )
                    if func:
                        record("CHAR_DEV_IOCTL", func.code)

                if "CHAR_DEV_POLL" in remaining:
                    idx = find_line(lines, "poll_wait")
                    if idx is not None:
                        record("CHAR_DEV_POLL", lines[idx])

                if "CHAR_DEV_MMAP" in remaining:
                    idx = find_line(lines, "remap_pfn_range")
                    if idx is not None:
                        record("CHAR_DEV_MMAP", lines[idx])

                if "CDEV_INIT" in remaining:
                    idx = find_line(lines, "cdev_init")
                    if idx is not None:
                        record("CDEV_INIT", lines[idx])

                if "CDEV_ADD" in remaining:
                    idx = find_line(lines, "cdev_add")
                    if idx is not None:
                        record("CDEV_ADD", lines[idx])

                if "CDEV_DEL" in remaining:
                    idx = find_line(lines, "cdev_del")
                    if idx is not None:
                        record("CDEV_DEL", lines[idx])

                if "DEVICE_CREATE" in remaining:
                    idx = find_line(lines, "device_create")
                    if idx is not None:
                        record("DEVICE_CREATE", lines[idx])

                if "CLASS_CREATE" in remaining:
                    idx = find_line(lines, "class_create")
                    if idx is not None:
                        record("CLASS_CREATE", lines[idx])

                if "REGISTER_CHRDEV" in remaining:
                    idx = find_line(lines, "register_chrdev")
                    if idx is not None:
                        record("REGISTER_CHRDEV", lines[idx])

                if "UNREGISTER_CHRDEV" in remaining:
                    idx = find_line(lines, "unregister_chrdev")
                    if idx is not None:
                        record("UNREGISTER_CHRDEV", lines[idx])

                # IRQ
                if "IRQ_REQUEST" in remaining:
                    idx = find_line_re(lines, re.compile(r"request_irq|request_threaded_irq|devm_request_irq"))
                    if idx is not None:
                        record("IRQ_REQUEST", lines[idx])

                if "IRQ_FREE" in remaining:
                    idx = find_line(lines, "free_irq")
                    if idx is not None:
                        record("IRQ_FREE", lines[idx])

                if "IRQ_HANDLER" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: "irqreturn_t" in f.code
                    )
                    if func:
                        record("IRQ_HANDLER", first_line_of_signature(func))

                if "IRQ_THREADED" in remaining:
                    idx = find_line(lines, "request_threaded_irq")
                    if idx is not None:
                        record("IRQ_THREADED", lines[idx])

                if "IRQ_ONESHOT" in remaining:
                    idx = find_line(lines, "IRQF_ONESHOT")
                    if idx is not None:
                        record("IRQ_ONESHOT", lines[idx])

                if "IRQ_SHARED" in remaining:
                    idx = find_line(lines, "IRQF_SHARED")
                    if idx is not None:
                        record("IRQ_SHARED", lines[idx])

                if "IRQF_TRIGGER_RISING" in remaining:
                    idx = find_line(lines, "IRQF_TRIGGER_RISING")
                    if idx is not None:
                        record("IRQF_TRIGGER_RISING", lines[idx])

                if "IRQF_TRIGGER_FALLING" in remaining:
                    idx = find_line(lines, "IRQF_TRIGGER_FALLING")
                    if idx is not None:
                        record("IRQF_TRIGGER_FALLING", lines[idx])

                if "IRQF_TRIGGER_LOW" in remaining:
                    idx = find_line(lines, "IRQF_TRIGGER_LOW")
                    if idx is not None:
                        record("IRQF_TRIGGER_LOW", lines[idx])

                if "IRQF_TRIGGER_HIGH" in remaining:
                    idx = find_line(lines, "IRQF_TRIGGER_HIGH")
                    if idx is not None:
                        record("IRQF_TRIGGER_HIGH", lines[idx])

                if "ENABLE_IRQ" in remaining:
                    idx = find_line(lines, "enable_irq")
                    if idx is not None:
                        record("ENABLE_IRQ", lines[idx])

                if "DISABLE_IRQ" in remaining:
                    idx = find_line(lines, "disable_irq")
                    if idx is not None:
                        record("DISABLE_IRQ", lines[idx])

                # Memory
                if "KMALLOC" in remaining:
                    idx = find_line(lines, "kmalloc")
                    if idx is not None:
                        record("KMALLOC", snippet_with_error_check(lines, idx))

                if "KZALLOC" in remaining:
                    idx = find_line(lines, "kzalloc")
                    if idx is not None:
                        record("KZALLOC", snippet_with_error_check(lines, idx))

                if "KFREE" in remaining:
                    idx = find_line(lines, "kfree")
                    if idx is not None:
                        record("KFREE", lines[idx])

                if "DEVM_KZALLOC" in remaining:
                    idx = find_line(lines, "devm_kzalloc")
                    if idx is not None:
                        record("DEVM_KZALLOC", snippet_with_error_check(lines, idx))

                if "DEVM_KMALLOC" in remaining:
                    idx = find_line(lines, "devm_kmalloc")
                    if idx is not None:
                        record("DEVM_KMALLOC", snippet_with_error_check(lines, idx))

                if "DMA_ALLOC_COHERENT" in remaining:
                    idx = find_line(lines, "dma_alloc_coherent")
                    if idx is not None:
                        record("DMA_ALLOC_COHERENT", lines[idx])

                if "DMA_FREE_COHERENT" in remaining:
                    idx = find_line(lines, "dma_free_coherent")
                    if idx is not None:
                        record("DMA_FREE_COHERENT", lines[idx])

                if "DMA_MAP_SINGLE" in remaining:
                    idx = find_line(lines, "dma_map_single")
                    if idx is not None:
                        record("DMA_MAP_SINGLE", lines[idx])

                if "DMA_UNMAP_SINGLE" in remaining:
                    idx = find_line(lines, "dma_unmap_single")
                    if idx is not None:
                        record("DMA_UNMAP_SINGLE", lines[idx])

                # Sync
                if "MUTEX_INIT" in remaining:
                    idx = find_line(lines, "mutex_init")
                    if idx is not None:
                        record("MUTEX_INIT", lines[idx])

                if "MUTEX_LOCK" in remaining:
                    idx = find_line(lines, "mutex_lock")
                    if idx is not None:
                        record("MUTEX_LOCK", lines[idx])

                if "MUTEX_UNLOCK" in remaining:
                    idx = find_line(lines, "mutex_unlock")
                    if idx is not None:
                        record("MUTEX_UNLOCK", lines[idx])

                if "SPINLOCK_INIT" in remaining:
                    idx = find_line(lines, "spin_lock_init")
                    if idx is not None:
                        record("SPINLOCK_INIT", lines[idx])

                if "SPIN_LOCK" in remaining:
                    idx = find_line(lines, "spin_lock")
                    if idx is not None:
                        record("SPIN_LOCK", lines[idx])

                if "SPIN_UNLOCK" in remaining:
                    idx = find_line(lines, "spin_unlock")
                    if idx is not None:
                        record("SPIN_UNLOCK", lines[idx])

                if "SPIN_LOCK_IRQ" in remaining:
                    idx = find_line(lines, "spin_lock_irq")
                    if idx is not None:
                        record("SPIN_LOCK_IRQ", lines[idx])

                if "SPIN_LOCK_IRQSAVE" in remaining:
                    idx = find_line(lines, "spin_lock_irqsave")
                    if idx is not None:
                        record("SPIN_LOCK_IRQSAVE", lines[idx])

                if "SPIN_UNLOCK_IRQRESTORE" in remaining:
                    idx = find_line(lines, "spin_unlock_irqrestore")
                    if idx is not None:
                        record("SPIN_UNLOCK_IRQRESTORE", lines[idx])

                # Error handling
                if "GOTO_CLEANUP" in remaining:
                    idx = find_line_re(lines, re.compile(r"goto\s+(err|out|fail)"))
                    if idx is not None:
                        record("GOTO_CLEANUP", lines[idx])

                if "ERROR_RETURN" in remaining:
                    idx = find_line_re(lines, re.compile(r"return\s*-E"))
                    if idx is not None:
                        record("ERROR_RETURN", lines[idx])

                if "IS_ERR" in remaining:
                    idx = find_line(lines, "IS_ERR")
                    if idx is not None:
                        record("IS_ERR", lines[idx])

                if "PTR_ERR" in remaining:
                    idx = find_line(lines, "PTR_ERR")
                    if idx is not None:
                        record("PTR_ERR", lines[idx])

                if "DEV_ERR" in remaining:
                    idx = find_line(lines, "dev_err")
                    if idx is not None:
                        record("DEV_ERR", lines[idx])

                if "DEV_WARN" in remaining:
                    idx = find_line(lines, "dev_warn")
                    if idx is not None:
                        record("DEV_WARN", lines[idx])

                if "DEV_INFO" in remaining:
                    idx = find_line(lines, "dev_info")
                    if idx is not None:
                        record("DEV_INFO", lines[idx])

                # Feature
                if "THRESHOLD_FEATURE" in remaining:
                    idx = find_line_re(lines, re.compile(r"threshold|overtemp|alarm|limit", re.IGNORECASE))
                    if idx is not None:
                        record("THRESHOLD_FEATURE", lines[idx])

                if "POLL_FEATURE" in remaining:
                    idx = find_line_re(lines, re.compile(r"poll_wait|wait_event_interruptible"))
                    if idx is not None:
                        record("POLL_FEATURE", lines[idx])

                if "DEBOUNCE_FEATURE" in remaining:
                    idx = find_line_re(lines, re.compile(r"gpiod_set_debounce|debounce", re.IGNORECASE))
                    if idx is not None:
                        record("DEBOUNCE_FEATURE", lines[idx])

                if "FIFO_FEATURE" in remaining:
                    idx = find_line_re(lines, re.compile(r"fifo|circular", re.IGNORECASE))
                    if idx is not None:
                        record("FIFO_FEATURE", lines[idx])

                if "SYSFS_ATTR_RO" in remaining:
                    idx = find_line(lines, "DEVICE_ATTR_RO")
                    if idx is not None:
                        record("SYSFS_ATTR_RO", lines[idx])

                if "SYSFS_ATTR_WO" in remaining:
                    idx = find_line(lines, "DEVICE_ATTR_WO")
                    if idx is not None:
                        record("SYSFS_ATTR_WO", lines[idx])

                if "SYSFS_ATTR_RW" in remaining:
                    idx = find_line(lines, "DEVICE_ATTR_RW")
                    if idx is not None:
                        record("SYSFS_ATTR_RW", lines[idx])

                if "SYSFS_SHOW" in remaining:
                    func = extract_function_by_predicate(funcs, lambda f: f.name.endswith("_show"))
                    if func:
                        record("SYSFS_SHOW", func.code)

                if "SYSFS_STORE" in remaining:
                    func = extract_function_by_predicate(funcs, lambda f: f.name.endswith("_store"))
                    if func:
                        record("SYSFS_STORE", func.code)

                if "POWER_MGMT_FEATURE" in remaining:
                    idx = find_line_re(lines, re.compile(r"SIMPLE_DEV_PM_OPS|SET_SYSTEM_SLEEP_PM_OPS"))
                    if idx is not None:
                        record("POWER_MGMT_FEATURE", lines[idx])

                if "PM_SUSPEND" in remaining:
                    func = extract_function_by_predicate(funcs, lambda f: "suspend" in f.name)
                    if func:
                        record("PM_SUSPEND", func.code)

                if "PM_RESUME" in remaining:
                    func = extract_function_by_predicate(funcs, lambda f: "resume" in f.name)
                    if func:
                        record("PM_RESUME", func.code)

                if "CALIBRATION_FEATURE" in remaining:
                    idx = find_line_re(lines, re.compile(r"calibration|calibrate", re.IGNORECASE))
                    if idx is not None:
                        record("CALIBRATION_FEATURE", lines[idx])

                # Device tree
                if "OF_MATCH_TABLE" in remaining:
                    block = find_array_block(text, re.compile(r"struct\s+of_device_id\b"))
                    if block:
                        record("OF_MATCH_TABLE", block)

                if "OF_COMPATIBLE" in remaining:
                    idx = find_line(lines, ".compatible")
                    if idx is not None:
                        record("OF_COMPATIBLE", lines[idx])

                if "OF_PROPERTY_READ" in remaining:
                    idx = find_line(lines, "of_property_read_u32")
                    if idx is not None:
                        record("OF_PROPERTY_READ", lines[idx])

                if "OF_GPIO_GET" in remaining:
                    idx = find_line(lines, "of_get_gpio")
                    if idx is not None:
                        record("OF_GPIO_GET", lines[idx])

                if "OF_IRQ_GET" in remaining:
                    idx = find_line(lines, "of_irq_get")
                    if idx is not None:
                        record("OF_IRQ_GET", lines[idx])

                # Module
                if "MODULE_INIT" in remaining:
                    idx = find_line(lines, "module_init")
                    if idx is not None:
                        record("MODULE_INIT", lines[idx])

                if "MODULE_EXIT" in remaining:
                    idx = find_line(lines, "module_exit")
                    if idx is not None:
                        record("MODULE_EXIT", lines[idx])

                if "MODULE_LICENSE" in remaining:
                    idx = find_line(lines, "MODULE_LICENSE")
                    if idx is not None:
                        record("MODULE_LICENSE", lines[idx])

                if "MODULE_AUTHOR" in remaining:
                    idx = find_line(lines, "MODULE_AUTHOR")
                    if idx is not None:
                        record("MODULE_AUTHOR", lines[idx])

                if "MODULE_DESCRIPTION" in remaining:
                    idx = find_line(lines, "MODULE_DESCRIPTION")
                    if idx is not None:
                        record("MODULE_DESCRIPTION", lines[idx])

                if "MODULE_DEVICE_TABLE" in remaining:
                    idx = find_line(lines, "MODULE_DEVICE_TABLE")
                    if idx is not None:
                        record("MODULE_DEVICE_TABLE", lines[idx])

                # IOCTL
                if "IOCTL_IMPLEMENTATION" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: TARGET_NAME_PATTERNS["ioctl"].search(f.name)
                    )
                    if func:
                        record("IOCTL_IMPLEMENTATION", first_line_of_signature(func))

                if "IOCTL_SWITCH_CASE" in remaining:
                    func = extract_function_by_predicate(
                        funcs, lambda f: TARGET_NAME_PATTERNS["ioctl"].search(f.name)
                    )
                    if func:
                        block = extract_switch_block(func.code)
                        if block:
                            record("IOCTL_SWITCH_CASE", block)

                if "IOCTL_CMD_READ" in remaining:
                    idx = find_line(lines, "copy_to_user")
                    if idx is not None:
                        record("IOCTL_CMD_READ", lines[idx])

                if "IOCTL_CMD_WRITE" in remaining:
                    idx = find_line(lines, "copy_from_user")
                    if idx is not None:
                        record("IOCTL_CMD_WRITE", lines[idx])

                if "IOCTL_COPY_FROM_USER" in remaining:
                    idx = find_line(lines, "copy_from_user")
                    if idx is not None:
                        record("IOCTL_COPY_FROM_USER", lines[idx])

                if "IOCTL_COPY_TO_USER" in remaining:
                    idx = find_line(lines, "copy_to_user")
                    if idx is not None:
                        record("IOCTL_COPY_TO_USER", lines[idx])

                # User copy
                if "COPY_TO_USER" in remaining:
                    idx = find_line(lines, "copy_to_user")
                    if idx is not None:
                        record("COPY_TO_USER", lines[idx])

                if "COPY_FROM_USER" in remaining:
                    idx = find_line(lines, "copy_from_user")
                    if idx is not None:
                        record("COPY_FROM_USER", lines[idx])

                if "ACCESS_OK" in remaining:
                    idx = find_line(lines, "access_ok")
                    if idx is not None:
                        record("ACCESS_OK", lines[idx])

                # Timers
                if "TIMER_SETUP" in remaining:
                    idx = find_line(lines, "timer_setup")
                    if idx is not None:
                        record("TIMER_SETUP", lines[idx])

                if "TIMER_ADD" in remaining:
                    idx = find_line_re(lines, re.compile(r"add_timer|mod_timer"))
                    if idx is not None:
                        record("TIMER_ADD", lines[idx])

                if "TIMER_DEL" in remaining:
                    idx = find_line(lines, "del_timer")
                    if idx is not None:
                        record("TIMER_DEL", lines[idx])

                if "HRTIMER_INIT" in remaining:
                    idx = find_line(lines, "hrtimer_init")
                    if idx is not None:
                        record("HRTIMER_INIT", lines[idx])

                if "HRTIMER_START" in remaining:
                    idx = find_line(lines, "hrtimer_start")
                    if idx is not None:
                        record("HRTIMER_START", lines[idx])

                # Work
                if "INIT_WORK" in remaining:
                    idx = find_line(lines, "INIT_WORK")
                    if idx is not None:
                        record("INIT_WORK", lines[idx])

                if "SCHEDULE_WORK" in remaining:
                    idx = find_line(lines, "schedule_work")
                    if idx is not None:
                        record("SCHEDULE_WORK", lines[idx])

                if "SCHEDULE_DELAYED_WORK" in remaining:
                    idx = find_line(lines, "schedule_delayed_work")
                    if idx is not None:
                        record("SCHEDULE_DELAYED_WORK", lines[idx])

                if "CANCEL_WORK_SYNC" in remaining:
                    idx = find_line(lines, "cancel_work_sync")
                    if idx is not None:
                        record("CANCEL_WORK_SYNC", lines[idx])

                # Device/driver register
                if "DEVICE_REGISTER" in remaining:
                    idx = find_line(lines, "device_register")
                    if idx is not None:
                        record("DEVICE_REGISTER", lines[idx])

                if "DEVICE_UNREGISTER" in remaining:
                    idx = find_line(lines, "device_unregister")
                    if idx is not None:
                        record("DEVICE_UNREGISTER", lines[idx])

                if "DRIVER_REGISTER" in remaining:
                    idx = find_line(lines, "driver_register")
                    if idx is not None:
                        record("DRIVER_REGISTER", lines[idx])

                if "DRIVER_UNREGISTER" in remaining:
                    idx = find_line(lines, "driver_unregister")
                    if idx is not None:
                        record("DRIVER_UNREGISTER", lines[idx])

            if not remaining:
                break
        if not remaining:
            break

    missing = sorted(list(remaining))
    return list(results.values()), missing


def collect_probe_combinations(roots: List[str]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    remove_minimal = [
        re.compile(r"request_irq|request_threaded_irq|devm_request_irq"),
        re.compile(r"IRQF_"),
        re.compile(r"sysfs_|DEVICE_ATTR"),
        re.compile(r"dma_alloc_coherent|dma_map_single|dma_unmap_single|dma_free_coherent"),
        re.compile(r"gpiod_set_debounce|debounce", re.IGNORECASE),
    ]
    remove_intermediate = remove_minimal + [
        re.compile(r"mutex_"),
        re.compile(r"poll_wait|wait_event_interruptible"),
        re.compile(r"fifo|circular", re.IGNORECASE),
        re.compile(r"threshold|overtemp|limit|alarm", re.IGNORECASE),
        re.compile(r"calibration|calibrate", re.IGNORECASE),
        re.compile(r"timer_setup|add_timer|mod_timer|del_timer"),
        re.compile(r"hrtimer_"),
        re.compile(r"INIT_WORK|schedule_work|schedule_delayed_work|cancel_work_sync"),
    ]

    for root in roots:
        for rel_dir in DIRS:
            abs_dir = os.path.join(root, rel_dir)
            if not os.path.isdir(abs_dir):
                continue
            for path in iter_c_files(abs_dir):
                text = read_file(path)
                funcs = extract_functions(text)
                probe = extract_function_by_predicate(
                    funcs, lambda f: TARGET_NAME_PATTERNS["probe"].search(f.name)
                )
                if not probe:
                    continue

                rel_path = os.path.relpath(path, root)
                base_driver = os.path.splitext(os.path.basename(path))[0]

                def add_entry(code: str, rules: List[str], variant: str, vtype: str) -> None:
                    entries.append(
                        {
                            "rules": ", ".join(rules),
                            "code": code.strip(),
                            "source_file": rel_path,
                            "driver": variant,
                            "type": vtype,
                        }
                    )

                full_rules = collect_rules(probe.code, probe)
                add_entry(probe.code, full_rules, base_driver, "full")

                minimal_code = remove_lines(probe.code, remove_minimal)
                minimal_rules = collect_rules(minimal_code, probe)
                add_entry(minimal_code, minimal_rules, f"{base_driver}_minimal", "minimal")

                mid_code = remove_lines(probe.code, remove_intermediate)
                mid_rules = collect_rules(mid_code, probe)
                add_entry(mid_code, mid_rules, f"{base_driver}_mid", "intermediate")

                expanded_code = probe.code
                if not any(r.startswith("MUTEX") for r in full_rules):
                    expanded_code = add_mutex_feature(expanded_code)
                else:
                    expanded_code = add_dev_err_feature(expanded_code, probe)
                expanded_rules = collect_rules(expanded_code, probe)
                add_entry(expanded_code, expanded_rules, f"{base_driver}_expanded", "expanded")

                swapped = bus_swap(probe.code, full_rules)
                if swapped and swapped != probe.code:
                    swapped_rules = collect_rules(swapped, probe)
                    suffix = "spi" if "I2C_BUS" in full_rules else "i2c"
                    add_entry(swapped, swapped_rules, f"{base_driver}_{suffix}", "cross_bus")

                devswap = device_swap(probe.code, full_rules)
                if devswap and devswap != probe.code:
                    dev_rules = collect_rules(devswap, probe)
                    suffix = "humidity" if "TEMP_SENSOR" in full_rules else "gyro"
                    add_entry(devswap, dev_rules, f"{base_driver}_{suffix}", "device_swap")

    return entries


def write_jsonl(path: str, rows: Iterable[Dict[str, str]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True))
            f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atomic-out", default=os.path.join(ROOT, "dataset", "atomic_rules.jsonl"))
    parser.add_argument("--combo-out", default=os.path.join(ROOT, "dataset", "combination_rules.jsonl"))
    args = parser.parse_args()

    roots = [os.path.join(ROOT, "src", "linux"), os.path.join(ROOT, "src", "rpi_kernel")]

    atomic, missing = extract_atomic_rules(roots)
    write_jsonl(args.atomic_out, atomic)

    combos = collect_probe_combinations(roots)
    write_jsonl(args.combo_out, combos)

    print(f"Wrote {len(atomic)} atomic rules to {args.atomic_out}")
    print(f"Wrote {len(combos)} combinations to {args.combo_out}")
    if missing:
        print("Missing rules:")
        for rule in missing:
            print(f"- {rule}")


if __name__ == "__main__":
    main()
