# Device Test Debugging Guide

This guide helps you troubleshoot issues with the ESP32 device testing system that now uses **continuous monitoring** to eliminate timing issues.

## Key Architecture Changes

The system now uses **continuous monitoring** that starts immediately upon connection:
- ✅ **No more timing issues** - monitoring starts instantly when you connect
- ✅ **No missed data** - logs are captured from the moment of connection
- ✅ **True continuous logging** - reset does NOT clear buffer, captures all boot messages
- ✅ **Always ready** - no need to manually start/stop monitoring

## Quick Debugging Workflow

1. **Connect and check status**: `connect` → `monitor_status`
2. **Check immediate data**: `check_immediate_data 2.0`
3. **Test search functionality**: `add_test_data "test line"` → `test_search "test"`
4. **Run your actual test**: `run_test`
5. **Clear buffer if needed**: `clear_log_buffer` (only when you want to start completely fresh)

## Common Debugging Scenarios

### 1. "all_data is empty" - No Data Received

**Symptoms:**
- `get_data` returns empty list
- `monitor_status` shows 0 lines received
- Tests fail with "pattern not found"

**Debug Steps:**
```bash
monitor_status          # Check if monitoring is active
check_immediate_data 3  # Check if data comes in immediately
reset                   # Try resetting ESP32
get_data 5             # Check if data appears after reset
```

**Common Causes:**
- ESP32 not sending data (check power, program)
- Wrong baud rate (try 9600, 38400, 230400)
- ESP32 in deep sleep mode
- Hardware connection issues

### 2. "Pattern not found but data exists"

**Symptoms:**
- `get_data` shows data
- Search patterns fail to match
- Tests timeout on log searches

**Debug Steps:**
```bash
get_data 10                    # See what data is actually received
add_test_data "ESP32 ready"   # Add known test data
test_search "ready"           # Test if search works on known data
test_search "ESP32"           # Test with actual pattern from logs
```

**Common Causes:**
- Case sensitivity (searches are case-insensitive)
- Pattern doesn't exactly match log output
- Special characters in pattern
- Data corruption or encoding issues

### 3. "Monitoring not working"

**Symptoms:**
- `monitor_status` shows thread not alive
- Connection appears successful but no data
- Errors in monitoring thread

**Debug Steps:**
```bash
disconnect              # Clean disconnect
connect                 # Reconnect (auto-starts monitoring)
monitor_status         # Verify thread is running
check_immediate_data 1 # Test data reception
```

## Debugging Commands Reference

### Connection & Monitoring
- `connect [PORT] [BAUDRATE]` - Connect and start continuous monitoring
- `disconnect` - Stop monitoring and disconnect
- `reset` - Reset ESP32 (keeps log buffer for continuous capture)
- `monitor_status` - Detailed monitoring thread status

### Data Inspection
- `get_data [SECONDS]` - Get recent data (default: 10 seconds)
- `check_immediate_data [SECONDS]` - Monitor data reception in real-time
- `get_stats` - Connection statistics and troubleshooting hints

### Testing & Debugging
- `add_test_data "LINE1" "LINE2"` - Add test data to buffer
- `test_search "PATTERN" [TIMEOUT]` - Test pattern matching
- `test_log "PATTERN" [TIMEOUT]` - Quick log pattern test
- `clear_log_buffer` - Manually clear log buffer (when you want fresh start)

### Step-Based Testing
- `run_test` - Interactive test sequence builder
- Available steps:
  - `reset [wait_seconds]` - Reset and optionally wait (keeps logging)
  - `delay seconds` - Wait for specified time
  - `search log "pattern" [timeout]` - Search for pattern

## Example Debugging Session

```bash
# 1. Connect and verify monitoring
Device-Test> connect
✓ Auto-connected to /dev/cu.usbserial-0001

# 2. Check monitoring status
Device-Test> monitor_status
Basic Stats:
  Is Monitoring: True
  Port: /dev/cu.usbserial-0001
  Total Lines: 0
  Bytes Received: 0

# 3. Check for immediate data
Device-Test> check_immediate_data 2.0
⚠ No data received in 2.0 seconds
Monitoring active: True, Thread alive: True

# 4. Try reset to trigger ESP32 output
Device-Test> reset
✓ ESP32 reset completed successfully

# 5. Check data after reset
Device-Test> check_immediate_data 1.0
✓ Data received: 5 lines, 234 bytes
First data received at 0.3s
Sample data received:
  ESP32 starting up...
  WiFi connecting...
  System ready

# 6. Test search functionality
Device-Test> test_search "ready"
✓ Pattern found: Found expected log pattern: ready
Matched line: System ready

# 7. Run actual test
Device-Test> run_test
Step 1> reset 2
Step 2> search log "System ready" 10
Step 3> done
✓ Test sequence completed: 2/2 steps passed
```

## Log Interpretation

### Monitor Status Output
```bash
Basic Stats:
  Is Monitoring: True          # ✓ Monitoring thread active
  Port: /dev/cu.usbserial-0001 # ✓ Connected to port
  Total Lines: 15              # ✓ Data being received
  Bytes Received: 1024         # ✓ Raw data flowing

Thread Info:
  Monitor Thread Exists: True  # ✓ Thread created
  Monitor Thread Alive: True   # ✓ Thread running
  Stop Event Set: False        # ✓ Not stopping

Serial Connection:
  Is Open: True                # ✓ Hardware connection active
  Bytes Waiting: 0             # Current buffer state
```

### Immediate Data Check Output
```bash
✓ Data received: 5 lines, 234 bytes
First data received at 0.3s    # ESP32 boot time
Sample data received:          # Actual log content
  ESP32 starting up...
  WiFi connecting...
  System ready
```

## Troubleshooting Tips

### Fast-Booting Devices (like yours - 300ms)
- ✅ **No longer an issue** - continuous monitoring captures everything
- ✅ **Reset preserves logging** - all boot messages captured from moment of reset
- ✅ **Immediate capture** - data captured from moment of connection
- ✅ **Complete boot sequence** - see everything from reset to main loop

### Timing-Sensitive Tests
- Use `reset` before time-sensitive sequences (logging continues)
- Use `delay` steps for precise timing
- Search patterns check all data since connection (or manual buffer clear)
- Use `clear_log_buffer` only when you need a completely fresh start

### UART Communication (Future)
- Continuous monitoring provides foundation for UART sync
- Timestamp-based searches enable precise timing correlation
- Buffer management handles high-frequency data

### Performance Optimization
- Buffer automatically manages size (10,000 lines max)
- Old data automatically pruned when buffer full
- Debug logging reduced to avoid performance impact

## When to Use Each Command

| Scenario | Command | Purpose |
|----------|---------|---------|
| Initial connection | `connect` | Auto-starts continuous monitoring |
| Check if working | `monitor_status` | Verify monitoring thread status |
| No data received | `check_immediate_data` | Real-time data reception test |
| Pattern not found | `test_search` | Test search logic with known data |
| Before important test | `reset` | Reset ESP32 (keeps all logs) |
| Need fresh start | `clear_log_buffer` | Manually clear buffer |
| Debug test sequence | `run_test` | Interactive step-by-step testing |

The new continuous monitoring architecture eliminates the timing issues you experienced and provides a robust foundation for all types of device testing, including future UART communication features. **Most importantly, reset no longer clears the buffer, so you'll capture the complete boot sequence including early messages.**
