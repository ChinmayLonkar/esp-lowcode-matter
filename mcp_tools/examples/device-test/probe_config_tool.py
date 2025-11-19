#!/usr/bin/env python3
# Copyright 2025 Espressif Systems (Shanghai) PTE LTD
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import json
import os
import subprocess
import sys
from types import SimpleNamespace

# Import nvs_partition_gen from ESP-IDF (same as mfg_gen.py)
try:
    import esp_idf_nvs_partition_gen.nvs_partition_gen as nvs_partition_gen
except ImportError:
    print("Error: esp_idf_nvs_partition_gen not found. Please install ESP-IDF and activate the environment.", file=sys.stderr)
    sys.exit(1)

def eprint(*a):
    print(*a, file=sys.stderr)

def validate(cfg_path):
    """Validate the probe configuration JSON"""
    with open(cfg_path, 'r') as f:
        data = json.load(f)
    errs = []
    
    # Minimal checks
    if 'probes' not in data or not isinstance(data['probes'], list):
        errs.append('probes must be a list')
    
    used_pins = {}
    board = data.get('device', {}).get('board', 'esp32')
    
    def pin_ok(pin):
        return isinstance(pin, int) and 0 <= pin <= 39
    
    for p in data.get('probes', []):
        t = p.get('type')
        if t == 'UART':
            for ch in p.get('channels', []):
                rx = ch.get('rx_gpio')
                if not pin_ok(rx):
                    errs.append(f'UART RX invalid: {rx}')
                used_pins.setdefault(rx, []).append('UART')
        elif t == 'I2C':
            for k in ['scl_gpio', 'sda_gpio']:
                v = p.get(k)
                if not pin_ok(v):
                    errs.append(f'I2C {k} invalid: {v}')
                used_pins.setdefault(v, []).append('I2C')
        elif t == 'PWM':
            v = p.get('gpio')
            if not pin_ok(v):
                errs.append(f'PWM gpio invalid: {v}')
            used_pins.setdefault(v, []).append('PWM')
        elif t == 'SPI':
            for k in ['clk_gpio', 'mosi_gpio', 'miso_gpio', 'cs_gpio']:
                v = p.get(k)
                if not pin_ok(v):
                    errs.append(f'SPI {k} invalid: {v}')
                used_pins.setdefault(v, []).append('SPI')
        elif t == 'RMT':
            v = p.get('gpio')
            if not pin_ok(v):
                errs.append(f'RMT gpio invalid: {v}')
            used_pins.setdefault(v, []).append('RMT')
        elif t == 'GPIO':
            for v in p.get('pins', []):
                if not pin_ok(v):
                    errs.append(f'GPIO pin invalid: {v}')
                used_pins.setdefault(v, []).append('GPIO')
    
    # Check for conflicts
    for pin, users in used_pins.items():
        if len(users) > 1:
            errs.append(f'Pin {pin} used by multiple: {",".join(users)}')
    
    if errs:
        eprint("Validation errors:")
        for e in errs:
            eprint(" -", e)
        return 1
    
    print("OK: validation passed")
    return 0

def create_config_info_file(filedir, cfg_path):
    """Create minified .info file from JSON (same as matter-one temp_copy_files)"""
    # Read the JSON config file
    with open(cfg_path, 'r') as f:
        lines = f.readlines()
    
    # Minify: strip whitespace and newlines (same as matter-one lines 84-90)
    combined_lines = ""
    for line in lines:
        combined_lines += line.strip().replace(' ', '')
    
    # Write to .info file
    info_path = os.path.join(filedir, 'config.info')
    with open(info_path, 'w') as f:
        f.writelines(combined_lines)
    
    return 'config.info'

def create_nvs_csv(filedir, info_full_path):
    """Create NVS CSV file (same workflow as mfg_gen.py create_mfg_config_file)"""
    csv_path = os.path.join(filedir, 'nvs.csv')
    with open(csv_path, 'w') as f:
        f.write('key,type,encoding,value\n')
        f.write('probe,namespace,,\n')
        # Use absolute path for the config.info file
        f.write(f'config_json,file,binary,{info_full_path}\n')
    return csv_path

def gen_nvs_partition_bin(filedir, output_bin_filename, csv_filename='nvs.csv'):
    """Generate NVS partition binary (same workflow as mfg_gen.py gen_nvs_partition_bin)"""
    # Use absolute paths
    csv_abs = os.path.join(filedir, csv_filename)
    output_abs = os.path.join(filedir, output_bin_filename)
    nvs_args = SimpleNamespace(
        input=csv_abs,
        output=output_abs,
        size='0x3000',
        outdir=filedir,
        version=2
    )
    print("Generating NVS Partition Binary: " + output_abs)
    nvs_partition_gen.generate(nvs_args)
    print(f"Success! NVS binary created at: {output_abs}")

def nvs_gen(cfg_path, out_bin):
    """Main NVS generation function"""
    # Get absolute paths
    cfg_abs = os.path.abspath(cfg_path)
    out_abs = os.path.abspath(out_bin)
    
    # Determine output directory
    out_dir = os.path.dirname(out_abs)
    if not out_dir:
        out_dir = '.'
    
    # Get output filename
    out_filename = os.path.basename(out_abs)
    
    # Create minified .info file from JSON (same as matter-one workflow)
    print(f"Creating minified config.info from: {cfg_path}")
    info_filename = create_config_info_file(out_dir, cfg_abs)
    info_full_path = os.path.join(out_dir, info_filename)
    
    # Create CSV file with full path to config.info
    create_nvs_csv(out_dir, info_full_path)
    
    # Generate NVS partition binary
    try:
        gen_nvs_partition_bin(out_dir, out_filename, 'nvs.csv')
        return 0
    except Exception as e:
        eprint(f"Error generating NVS partition: {e}")
        import traceback
        traceback.print_exc()
        return 1

def flash(port, nvs_bin, offset):
    """Flash NVS binary to device"""
    cmd = ['esptool.py', '--port', port, 'write_flash', hex(offset), nvs_bin]
    print('Running:', ' '.join(cmd))
    return subprocess.call(cmd)

def configure_probe(cfg_path, port, offset):
    """Validate, generate NVS binary, and flash in one go"""
    print("=" * 60)
    print("Step 1/3: Validating configuration...")
    print("=" * 60)
    ret = validate(cfg_path)
    if ret != 0:
        eprint("Validation failed. Aborting.")
        return ret
    
    print("\n" + "=" * 60)
    print("Step 2/3: Generating NVS binary...")
    print("=" * 60)
    # Generate binary in same directory as config
    cfg_dir = os.path.dirname(os.path.abspath(cfg_path))
    if not cfg_dir:
        cfg_dir = '.'
    out_bin = os.path.join(cfg_dir, 'config.bin')
    ret = nvs_gen(cfg_path, out_bin)
    if ret != 0:
        eprint("NVS generation failed. Aborting.")
        return ret
    
    print("\n" + "=" * 60)
    print("Step 3/3: Flashing to device...")
    print("=" * 60)
    ret = flash(port, out_bin, offset)
    if ret != 0:
        eprint("Flash failed.")
        return ret
    
    print("\n" + "=" * 60)
    print("SUCCESS! Configuration validated, generated, and flashed.")
    print("=" * 60)
    return 0

def main():
    ap = argparse.ArgumentParser(description='Probe Configuration Tool')
    sub = ap.add_subparsers(dest='cmd', required=True)
    
    # All-in-one command
    a = sub.add_parser('all', help='Validate, generate, and flash in one go')
    a.add_argument('config', help='Path to config.json')
    a.add_argument('port', help='Serial port (e.g., /dev/ttyUSB0)')
    a.add_argument('--offset', type=lambda x: int(x, 0), default=0x9000,
                   help='Flash offset (default: 0x9000)')
    
    # Validate command
    v = sub.add_parser('validate', help='Validate probe configuration JSON')
    v.add_argument('config', help='Path to config.json')
    
    # NVS generation command
    g = sub.add_parser('nvs-gen', help='Generate NVS partition binary')
    g.add_argument('config', help='Path to config.json')
    g.add_argument('-o', '--out', required=True, help='Output binary file path')
    
    # Flash command
    f = sub.add_parser('flash', help='Flash NVS binary to device')
    f.add_argument('port', help='Serial port (e.g., /dev/ttyUSB0)')
    f.add_argument('bin', help='NVS binary file to flash')
    f.add_argument('--offset', type=lambda x: int(x, 0), required=True, 
                   help='Flash offset (e.g., 0x9000)')
    
    args = ap.parse_args()
    
    if args.cmd == 'all':
        sys.exit(configure_probe(args.config, args.port, args.offset))
    elif args.cmd == 'validate':
        sys.exit(validate(args.config))
    elif args.cmd == 'nvs-gen':
        sys.exit(nvs_gen(args.config, args.out))
    elif args.cmd == 'flash':
        sys.exit(flash(args.port, args.bin, args.offset))

if __name__ == '__main__':
    main()
