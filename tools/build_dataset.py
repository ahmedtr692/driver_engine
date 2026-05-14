#!/usr/bin/env python3
"""Build JSONL dataset of kernel driver functions with rule labels.

This script scans selected driver directories under src/linux and src/rpi_kernel,
extracts target function types, labels them with matching rules, and emits
original + minimal + expanded (+ bus-swapped when applicable) variants.
"""

import argparse
import json
import os
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Directories to scan and base rules to apply per directory.
DIR_RULES: Dict[str, List[str]] = {
    "drivers/iio/temperature": ["TEMP_SENSOR"],
    "drivers/iio/humidity": ["HUMIDITY_SENSOR"],
    "drivers/iio/pressure": ["PRESSURE_SENSOR"],
    "drivers/iio/accel": ["ACCELEROMETER"],
    "drivers/iio/adc": ["ADC_DEVICE"],
    "drivers/iio/light": ["LIGHT_SENSOR"],
    "drivers/input/keyboard": ["BUTTON_DEVICE"],
    "drivers/input/misc": ["INPUT_DEVICE"],
    "drivers/gpio": ["GPIO_EXPANDER", "GPIO_BUS"],
    "drivers/rtc": ["RTC_DEVICE"],
    "drivers/watchdog": ["WATCHDOG_DEVICE"],
    "drivers/pwm": ["PWM_DEVICE"],
    "drivers/mtd/spi-nor": ["FLASH_DEVICE"],
    "drivers/mtd/nand": ["FLASH_DEVICE"],
    "drivers/net/ethernet": ["NETWORK_DEVICE"],
    "drivers/net/can": ["CAN_BUS"],
    "drivers/net/phy": ["NETWORK_DEVICE"],
    "drivers/usb/serial": ["SERIAL_DEVICE"],
    "drivers/video/fbdev": ["DISPLAY_DEVICE"],
    "drivers/nvmem": ["EEPROM_DEVICE"],
    "drivers/char": ["CHAR_DEV"],
    "drivers/leds": ["LED_DEVICE"],
    "drivers/power/supply": ["POWER_SUPPLY"],
    "drivers/thermal": ["TEMP_SENSOR"],
    "sound/soc/codecs": ["CODEC_DEVICE"],
}

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
    "read": re.compile(r"(^|_)read($|_)", re.IGNORECASE),
    "write": re.compile(r"(^|_)write($|_)", re.IGNORECASE),
    "ioctl": re.compile(r"ioctl", re.IGNORECASE),
    "show": re.compile(r"(^|_)show($|_)", re.IGNORECASE),
    "store": re.compile(r"(^|_)store($|_)", re.IGNORECASE),
    "suspend": re.compile(r"(^|_)suspend($|_)", re.IGNORECASE),
    "resume": re.compile(r"(^|_)resume($|_)", re.IGNORECASE),
}

DEVICE_TYPE_PATTERNS = {
    "TEMP_SENSOR": ["temperature", "temp", "thermal"],
    "HUMIDITY_SENSOR": ["humidity", "humid", "rh"],
    "PRESSURE_SENSOR": ["pressure", "baro", "bmp"],
    "ACCELEROMETER": ["accel", "accelerometer"],
    "GYROSCOPE": ["gyro", "gyroscope"],
    "MAGNETOMETER": ["magnet", "magnetometer"],
    "LIGHT_SENSOR": ["light", "lux", "als"],
    "ADC_DEVICE": ["adc", "analog"],
    "DAC_DEVICE": ["dac"],
    "LED_DEVICE": ["led", "brightness"],
    "BUTTON_DEVICE": ["button", "key", "gpio_keys"],
    "SWITCH_DEVICE": ["switch"],
    "RELAY_DEVICE": ["relay"],
    "DISPLAY_DEVICE": ["display", "lcd", "oled", "fb"],
    "EEPROM_DEVICE": ["eeprom", "at24", "at25"],
    "FLASH_DEVICE": ["flash", "mtd", "nor", "nand"],
    "RTC_DEVICE": ["rtc", "ds1307", "ds3232"],
    "WATCHDOG_DEVICE": ["watchdog", "wdt"],
    "PWM_DEVICE": ["pwm", "pwmchip"],
    "GPIO_EXPANDER": ["expander", "pca955", "mcp23"],
    "SERIAL_DEVICE": ["serial", "uart", "ftdi", "cp210"],
    "NETWORK_DEVICE": ["ethernet", "net", "nic"],
    "INPUT_DEVICE": ["input", "keyboard", "mouse", "hid"],
    "MOTOR_DEVICE": ["motor"],
    "SERVO_DEVICE": ["servo"],
    "FAN_DEVICE": ["fan"],
    "POWER_SUPPLY": ["power", "battery", "charger"],
    "CODEC_DEVICE": ["codec", "audio", "sound"],
    "CAMERA_DEVICE": ["camera", "csi"],
}

BUS_RULES = {
    "GPIO_BUS": ["gpio_desc", "gpiod_", "gpiochip_"],
    "I2C_BUS": ["i2c_client", "i2c_driver"],
    "SPI_BUS": ["spi_device", "spi_driver"],
    "USB_BUS": ["usb_device", "usb_driver"],
    "PCI_BUS": ["pci_dev", "pci_driver"],
    "PLATFORM_BUS": ["platform_device", "platform_driver"],
    "UART_BUS": ["uart_driver", "tty_"],
    "CAN_BUS": ["can_driver", "can_frame"],
}

SUBSYSTEM_RULES = {
    "IIO_REGISTER": ["iio_device_register", "devm_iio_device_register"],
    "IIO_CHANNELS": ["iio_chan_spec"],
    "IIO_BUFFER": ["iio_buffer", "iio_triggered_buffer"],
    "IIO_READ": ["_read_raw"],
    "INPUT_REGISTER": ["input_register_device"],
    "INPUT_EVENT": ["input_report_key", "input_sync"],
    "INPUT_POLL": ["input_poll_dev"],
    "RTC_REGISTER": ["devm_rtc_device_register"],
    "RTC_READ": ["rtc_read_time"],
    "RTC_WRITE": ["rtc_set_time"],
    "NVMEM_REGISTER": ["devm_nvmem_register"],
    "NVMEM_READ": ["nvmem_reg_read"],
    "NVMEM_WRITE": ["nvmem_reg_write"],
    "FB_REGISTER": ["register_framebuffer"],
    "FB_WRITE": ["fb_write"],
    "WATCHDOG_REGISTER": ["devm_watchdog_register_device"],
    "WATCHDOG_PING": ["watchdog_ping"],
    "PWM_REGISTER": ["devm_pwmchip_add"],
    "PWM_CONFIG": ["pwm_config"],
    "TTY_REGISTER": ["tty_port_register_device"],
    "MTD_REGISTER": ["mtd_device_register"],
    "MTD_READ": ["mtd_read"],
    "MTD_WRITE": ["mtd_write"],
    "MTD_ERASE": ["mtd_erase"],
    "NET_REGISTER": ["register_netdev"],
    "CHAR_DEV_INIT": ["cdev_init", "register_chrdev"],
    "CHAR_DEV_CREATE": ["device_create", "class_create"],
    "CHAR_DEV_READ": ["copy_to_user"],
    "CHAR_DEV_WRITE": ["copy_from_user"],
    "CHAR_DEV_IOCTL": ["unlocked_ioctl"],
}

INTERRUPT_RULES = {
    "IRQ_REQUEST": ["request_irq", "request_threaded_irq", "devm_request_irq"],
    "IRQ_HANDLER": ["irq_handler", "IRQ_HANDLED"],
    "IRQ_THREADED": ["request_threaded_irq"],
    "IRQF_TRIGGER_RISING": ["IRQF_TRIGGER_RISING"],
    "IRQF_TRIGGER_FALLING": ["IRQF_TRIGGER_FALLING"],
    "IRQF_TRIGGER_LOW": ["IRQF_TRIGGER_LOW"],
    "IRQF_TRIGGER_HIGH": ["IRQF_TRIGGER_HIGH"],
}

MEMORY_RULES = {
    "KMALLOC": ["kmalloc"],
    "KZALLOC": ["kzalloc"],
    "KFREE": ["kfree"],
    "DEVM_KZALLOC": ["devm_kzalloc"],
    "DEVM_KMALLOC": ["devm_kmalloc"],
    "DMA_ALLOC_COHERENT": ["dma_alloc_coherent"],
    "DMA_MAP_SINGLE": ["dma_map_single"],
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
    "POLL_FEATURE": ["poll", "poll_wait", "wait_queue"],
    "DEBOUNCE_FEATURE": ["debounce", "gpiod_set_debounce"],
    "FIFO_FEATURE": ["fifo", "buffer", "circular"],
    "SYSFS_FEATURE": ["sysfs_create", "DEVICE_ATTR"],
    "POWER_MGMT_FEATURE": ["suspend", "resume", "pm_", "PM_"],
    "CALIBRATION_FEATURE": ["calibrate", "calibration"],
}

DT_RULES = {
    "OF_MATCH_TABLE": ["of_match_table"],
    "OF_COMPATIBLE": [".compatible"],
}

MODULE_RULES = {
    "MODULE_INIT": ["module_init"],
    "MODULE_EXIT": ["module_exit"],
    "MODULE_LICENSE": ["MODULE_LICENSE"],
    "MODULE_AUTHOR": ["MODULE_AUTHOR"],
    "MODULE_DESCRIPTION": ["MODULE_DESCRIPTION"],
    "MODULE_DEVICE_TABLE": ["MODULE_DEVICE_TABLE"],
}

ERROR_RETURN_RE = re.compile(r"\breturn\s*-\s*E", re.IGNORECASE)
GOTO_CLEANUP_RE = re.compile(r"\bgoto\s+(err|out|fail)\b")


class FunctionDef:
    def __init__(self, name: str, code: str, args: str) -> None:
        self.name = name
        self.code = code
        self.args = args


class FileContext:
    def __init__(self, module_inits: Set[str], module_exits: Set[str], module_flags: Set[str]) -> None:
        self.module_inits = module_inits
        self.module_exits = module_exits
        self.module_flags = module_flags


def strip_comments_strings(code: str) -> str:
    """Return code with comments and strings replaced by spaces (preserve length)."""
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


def find_module_macros(cleaned: str) -> FileContext:
    module_inits = set(re.findall(r"\bmodule_init\s*\(\s*([A-Za-z_]\w*)\s*\)", cleaned))
    module_exits = set(re.findall(r"\bmodule_exit\s*\(\s*([A-Za-z_]\w*)\s*\)", cleaned))
    module_flags = {rule for rule, patterns in MODULE_RULES.items() if any(p in cleaned for p in patterns)}
    return FileContext(module_inits, module_exits, module_flags)


def matches_target_type(func: FunctionDef, ctx: FileContext) -> bool:
    name = func.name
    lname = name.lower()
    if name in ctx.module_inits or name in ctx.module_exits:
        return True
    if TARGET_NAME_PATTERNS["probe"].search(name):
        return True
    if TARGET_NAME_PATTERNS["remove"].search(name):
        return True
    if TARGET_NAME_PATTERNS["ioctl"].search(name):
        return True
    if TARGET_NAME_PATTERNS["show"].search(name) or TARGET_NAME_PATTERNS["store"].search(name):
        return True
    if TARGET_NAME_PATTERNS["suspend"].search(name) or TARGET_NAME_PATTERNS["resume"].search(name):
        return True
    if TARGET_NAME_PATTERNS["read"].search(name) or TARGET_NAME_PATTERNS["write"].search(name):
        return True
    if "irqreturn_t" in func.code or "IRQ_HANDLED" in func.code:
        return True
    if "interrupt" in lname or "irq" in lname:
        return True
    return False


def collect_rules(code: str, base_rules: Iterable[str]) -> List[str]:
    rules: Set[str] = set(base_rules)

    def add_rules(rule_map: Dict[str, List[str]], case_insensitive: bool = False) -> None:
        search_text = code.lower() if case_insensitive else code
        for rule, patterns in rule_map.items():
            for pat in patterns:
                needle = pat.lower() if case_insensitive else pat
                if needle in search_text:
                    rules.add(rule)
                    break

    add_rules(BUS_RULES)
    add_rules(SUBSYSTEM_RULES)
    add_rules(INTERRUPT_RULES)
    add_rules(MEMORY_RULES)
    add_rules(SYNC_RULES)
    add_rules(ERROR_RULES)
    add_rules(FEATURE_RULES, case_insensitive=True)
    add_rules(DT_RULES)
    add_rules(DEVICE_TYPE_PATTERNS, case_insensitive=True)

    if ERROR_RETURN_RE.search(code):
        rules.add("ERROR_RETURN")
    if GOTO_CLEANUP_RE.search(code):
        rules.add("GOTO_CLEANUP")

    # INTERRUPT_FEATURE if any IRQ rule matched
    if any(rule.startswith("IRQ") for rule in rules):
        rules.add("INTERRUPT_FEATURE")

    # DMA_FEATURE if any DMA rule matched
    if "DMA_ALLOC_COHERENT" in rules or "DMA_MAP_SINGLE" in rules:
        rules.add("DMA_FEATURE")

    return sorted(rules)


def detect_device_expr(args: str) -> Optional[str]:
    matches = re.findall(r"struct\s+([A-Za-z_][\w]*)\s*\*\s*([A-Za-z_]\w*)", args)
    for type_name, var in matches:
        if type_name == "device":
            return var
        if type_name in {"i2c_client", "spi_device", "platform_device", "usb_interface", "pci_dev"}:
            return f"&{var}->dev"
    return None


def detect_indent(body: str) -> str:
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped:
            return line[: len(line) - len(stripped)]
    return "\t"


def add_mutex_feature(code: str) -> str:
    brace_idx = code.find('{')
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
    if tail.rstrip().endswith('}'):
        body = tail[:-1]
        end_insert = f"\n{indent}mutex_unlock(&lock);\n"
        return head + insert + body + end_insert + "}\n"
    return head + insert + tail


def add_dev_err_feature(code: str, args: str) -> str:
    dev_expr = detect_device_expr(args)
    if not dev_expr:
        return code
    brace_idx = code.find('{')
    if brace_idx == -1:
        return code
    head = code[:brace_idx + 1]
    tail = code[brace_idx + 1:]
    indent = detect_indent(tail)
    insert = f"\n{indent}dev_err({dev_expr}, \"expanded: injected error log\\n\");\n"
    return head + insert + tail


def add_devm_kzalloc_feature(code: str, args: str) -> str:
    dev_expr = detect_device_expr(args)
    if not dev_expr:
        return code
    brace_idx = code.find('{')
    if brace_idx == -1:
        return code
    head = code[:brace_idx + 1]
    tail = code[brace_idx + 1:]
    indent = detect_indent(tail)
    insert = (
        f"\n{indent}void *tmp = devm_kzalloc({dev_expr}, 16, GFP_KERNEL);\n"
        f"{indent}(void)tmp;\n"
    )
    return head + insert + tail


def remove_lines(code: str, predicates: Iterable[re.Pattern]) -> str:
    lines = code.splitlines()
    kept = []
    for line in lines:
        if any(p.search(line) for p in predicates):
            continue
        kept.append(line)
    return "\n".join(kept) + ("\n" if code.endswith("\n") else "")


def make_minimal(code: str, rules: List[str]) -> str:
    if any(r.startswith("MUTEX") for r in rules):
        return remove_lines(code, [re.compile(r"\bmutex_(init|lock|unlock)\b")])
    if any(r.startswith("IRQ") for r in rules):
        return remove_lines(code, [
            re.compile(r"\brequest_irq\b"),
            re.compile(r"\brequest_threaded_irq\b"),
            re.compile(r"\bdevm_request_irq\b"),
            re.compile(r"\bIRQF_TRIGGER_\w+\b"),
            re.compile(r"\bIRQ_HANDLED\b"),
        ])
    if "DMA_ALLOC_COHERENT" in rules or "DMA_MAP_SINGLE" in rules:
        return remove_lines(code, [re.compile(r"\bdma_alloc_coherent\b"), re.compile(r"\bdma_map_single\b")])
    if "SYSFS_FEATURE" in rules:
        return remove_lines(code, [re.compile(r"sysfs_"), re.compile(r"DEVICE_ATTR")])
    return code


def make_expanded(code: str, args: str, rules: List[str]) -> str:
    if not any(r.startswith("MUTEX") for r in rules):
        return add_mutex_feature(code)
    if "DEV_ERR" not in rules:
        with_dev_err = add_dev_err_feature(code, args)
        if with_dev_err != code:
            return with_dev_err
    if "DEVM_KZALLOC" not in rules:
        with_alloc = add_devm_kzalloc_feature(code, args)
        if with_alloc != code:
            return with_alloc
    return code


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


def build_samples(func: FunctionDef, base_rules: List[str]) -> List[Tuple[str, List[str]]]:
    original_rules = collect_rules(func.code, base_rules)
    samples: List[Tuple[str, List[str]]] = [(func.code, original_rules)]

    minimal_code = make_minimal(func.code, original_rules)
    minimal_rules = collect_rules(minimal_code, base_rules)
    samples.append((minimal_code, minimal_rules))

    expanded_code = make_expanded(func.code, func.args, original_rules)
    expanded_rules = collect_rules(expanded_code, base_rules)
    samples.append((expanded_code, expanded_rules))

    swapped_code = bus_swap(func.code, original_rules)
    if swapped_code and swapped_code != func.code:
        swapped_rules = collect_rules(swapped_code, base_rules)
        samples.append((swapped_code, swapped_rules))

    return samples


def iter_c_files(base_dir: str) -> Iterable[str]:
    for root, _, files in os.walk(base_dir):
        for fname in files:
            if fname.endswith(".c"):
                yield os.path.join(root, fname)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def write_jsonl(out_path: str, entries: Iterable[Tuple[str, List[str]]]) -> None:
    with open(out_path, "w", encoding="utf-8") as out:
        for code, rules in entries:
            payload = {
                "source": code,
                "input": ", ".join(rules),
            }
            out.write(json.dumps(payload, ensure_ascii=True))
            out.write("\n")


def collect_entries(root: str) -> List[Tuple[str, List[str]]]:
    entries: List[Tuple[str, List[str]]] = []
    for rel_dir, base_rules in DIR_RULES.items():
        abs_dir = os.path.join(root, rel_dir)
        if not os.path.isdir(abs_dir):
            continue
        for path in iter_c_files(abs_dir):
            code = read_file(path)
            cleaned = strip_comments_strings(code)
            ctx = find_module_macros(cleaned)
            funcs = extract_functions(code)
            for func in funcs:
                if not matches_target_type(func, ctx):
                    continue
                samples = build_samples(func, base_rules)
                entries.extend(samples)
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(ROOT, "dataset", "code_dataset.json"))
    args = parser.parse_args()

    roots = [os.path.join(ROOT, "src", "linux"), os.path.join(ROOT, "src", "rpi_kernel")]
    all_entries: List[Tuple[str, List[str]]] = []
    for root in roots:
        all_entries.extend(collect_entries(root))

    write_jsonl(args.out, all_entries)
    print(f"Wrote {len(all_entries)} samples to {args.out}")


if __name__ == "__main__":
    main()
